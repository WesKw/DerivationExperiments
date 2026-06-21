#!/usr/bin/env python3
"""
Analyze multiple Darshan .darshan files to measure I/O latency variation over time.
Optimized for identifying optimal candidates for Client-Side I/O Latency.
Enhanced with pydarshan DXT analysis to detect "Silence is the Signal" brownouts
and capture true Tail Latency (P99).
"""

import sys
import os
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

try:
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import matplotlib.dates as mdates
    from matplotlib.patches import Patch
    import numpy as np
    import darshan
    import pandas as pd
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# --- Configuration ---
BROWNOUT_THRESHOLD_SEC = 5.0

# Filesystems excluded from candidacy (kernel/system paths)
EXCLUDED_MOUNT_PREFIXES = {'/', '/proc', '/sys', '/dev', '/run', '/tmp',
                           '/lib', '/usr', '/bin', '/sbin', '/etc','N/A'}

# Per-filesystem size limit overrides (bytes). Filesystems not listed use --max-size.
# Large-block physics filesystems need a much higher cap (or None = unlimited).
FS_SIZE_OVERRIDES = {
    '/lcrc/project': None,   # no size cap — physics files are large-block by design
    '/lcrc':         None,
}

# In configuration section
FS_MOUNT_ALIASES = {
    '/srv': '/srv (→ /lcrc/project, Apptainer bind)',
}


def _resolve_mount(filename, mount_points):
    """Return the deepest mount point that is a prefix of filename."""
    if not filename:
        return 'N/A'
    for mount_path, fs_type in mount_points:
        if filename.startswith(mount_path):
            return mount_path
    # Heuristic fallback: first two path components
    parts = Path(filename).parts
    if len(parts) >= 3:
        return str(Path(*parts[:3]))
    return 'N/A'


def _effective_max_size(mount_pt, default_max):
    """Return the size cap for a given mount point."""
    for prefix, override in FS_SIZE_OVERRIDES.items():
        if mount_pt.startswith(prefix):
            return override  # None means unlimited
    return default_max

def _temporal_metrics(start_times, end_times, elapsed_job_s):
    """
    Compute how well a file's DXT ops are spread over the job lifetime.
    """
    BURST_GAP_SEC = 10.0   # gaps > 10s separate distinct activity periods

    if len(start_times) < 2 or elapsed_job_s <= 0:
        return {
            'temporal_coverage':   0.0,
            'temporal_uniformity': 0.0,
            'active_periods':      1,
            'ops_per_period':      len(start_times),
        }

    first_start = start_times[0]
    last_end    = end_times[-1]

    # 1. Coverage: what fraction of the job lifetime has I/O activity?
    temporal_coverage = min((last_end - first_start) / elapsed_job_s, 1.0)

    # 2. Uniformity: Compare empirical arrival CDF to uniform CDF
    duration = last_end - first_start
    if duration > 0:
        T_norm = (start_times - first_start) / duration
        U_norm = np.linspace(0.0, 1.0, len(start_times))
        mae = np.mean(np.abs(T_norm - U_norm))
        temporal_uniformity = max(0.0, 1.0 - (2.0 * mae))
    else:
        temporal_uniformity = 0.0

    # 3. Active periods: runs of ops with no gap > BURST_GAP_SEC
    gaps = np.diff(start_times)
    period_breaks = np.where(gaps > BURST_GAP_SEC)[0]
    active_periods = len(period_breaks) + 1
    ops_per_period = len(start_times) / active_periods

    return {
        'temporal_coverage':   float(temporal_coverage),
        'temporal_uniformity': float(temporal_uniformity),
        'active_periods':      int(active_periods),
        'ops_per_period':      float(ops_per_period),
    }

def _temporal_score(c):
    """Composite score for how good a candidate is as a temporal probe."""
    cov     = c.get('temporal_coverage',   0.0)
    unif    = c.get('temporal_uniformity', 0.0)
    periods = c.get('active_periods',      1)
    periods_norm = min((periods - 1) / 9.0, 1.0)
    return 0.60 * cov + 0.30 * unif + 0.10 * periods_norm

def _probe_quality_label(t_score: float, t_cov: float, t_unif: float) -> str:
    """Human-readable quality tier for a probe's temporal spread."""
    if t_score >= 0.75 and t_cov >= 0.80:
        return '★★★ excellent'
    elif t_score >= 0.55 and t_cov >= 0.60:
        return '★★☆ good'
    elif t_score >= 0.35 and t_cov >= 0.40:
        return '★☆☆ marginal — bursty reads, use with caution'
    else:
        return '☆☆☆ poor — ops too clustered, unreliable probe'

# ---------------------------------------------------------------------------
# Worker (must be module-level for pickle)
# ---------------------------------------------------------------------------
def _analyze_log_worker(args_tuple):
    log_path, max_size, min_ops, io_filter, fs_pattern = args_tuple
    return analyze_log(log_path, max_size, min_ops, io_filter, fs_pattern)


def analyze_log(log_path, max_size, min_ops, io_filter=None, fs_pattern=None):
    """
    Analyzes a single Darshan log using pydarshan.
    Extracts POSIX metadata + enriched DXT tail/brownout stats
    plus recommended probe variables for filesystem health monitoring.
    """
    try:
        with darshan.DarshanReport(str(log_path), read_all=True,
                                   filter_patterns=fs_pattern,
                                   filter_mode="exclude") as report:

            # Mount points, longest-first so deepest wins
            mount_points = []
            if 'mounts' in report.data:
                mount_points = sorted(report.data['mounts'],
                                      key=lambda x: len(x[0]), reverse=True)

            # 1. Basic metadata
            metadata = report.metadata
            start_ts    = metadata['job'].get('start_time_sec', 0)
            end_ts      = metadata['job'].get('end_time_sec', start_ts)
            elapsed     = max(end_ts - start_ts, 1)   # seconds; guard /0
            pid         = metadata['job'].get('jobid', 'unknown')

            if 'POSIX' not in report.records:
                return None

            # 2. POSIX counters + fcounters
            posix_dfs    = report.records['POSIX'].to_df()
            df_counters  = posix_dfs['counters'].copy()
            df_fcounters = posix_dfs['fcounters'].copy()
            df_counters['id']  = df_counters['id'].astype('string')
            df_fcounters['id'] = df_fcounters['id'].astype('string')
            posix_data = pd.merge(df_counters, df_fcounters, on=['rank', 'id'])

            candidates = []
            for _, record in posix_data.iterrows():
                record_id = int(record['id'])
                filename  = report.name_records.get(record_id)
                mount_pt  = _resolve_mount(filename, mount_points)

                if mount_pt in EXCLUDED_MOUNT_PREFIXES:
                    continue

                fs_max_size = _effective_max_size(mount_pt, max_size)

                for op_type in ['READ', 'WRITE']:
                    if io_filter and op_type != io_filter:
                        continue

                    count_col = f'POSIX_{op_type}S'
                    time_col  = f'POSIX_F_{op_type}_TIME'
                    bytes_col = ('POSIX_BYTES_READ'
                                 if op_type == 'READ'
                                 else 'POSIX_BYTES_WRITTEN')

                    if count_col not in record or time_col not in record:
                        continue

                    count     = record[count_col]
                    bytes_val = record.get(bytes_col, 0)
                    time_val  = record.get(time_col,  0)

                    if count < min_ops or bytes_val <= 0:
                        continue

                    avg_size = bytes_val / count
                    if fs_max_size is not None and avg_size > fs_max_size:
                        continue

                    # --- Tier 1: core latency ---
                    posix_avg_lat = (time_val / count) * 1000.0  # ms

                    # --- Tier 2: load & contention signals ---
                    meta_time  = record.get('POSIX_F_META_TIME',          0.0)
                    opens      = record.get('POSIX_OPENS',                 0)
                    seeks      = record.get('POSIX_SEEKS',                 0)
                    lock_wait  = record.get('POSIX_F_POSIX_LOCK_WAIT_TIME', 0.0)

                    open_rate        = opens / elapsed
                    meta_lat_ms      = (meta_time / opens * 1000.0
                                        if opens > 0 else 0.0)
                    seeks_per_op     = seeks / count

                    candidates.append({
                        'filename':          filename,
                        'norm_filename':     os.path.basename(filename),
                        'record_id':         record_id,
                        'type':              op_type,
                        'count':             count,
                        'avg_size':          avg_size,
                        'mount_pt':          mount_pt,
                        'elapsed_s':         elapsed,
                        # Tier 1 — latency
                        'posix_avg_latency_ms': posix_avg_lat,
                        # Tier 2 — load & contention
                        'meta_time_s':       meta_time,
                        'meta_lat_ms':       meta_lat_ms,
                        'open_rate_per_s':   open_rate,
                        'seeks':             seeks,
                        'seeks_per_op':      seeks_per_op,
                        'lock_wait_s':       lock_wait,
                    })

            if not candidates:
                return None

            # 3. DXT enrichment — P99, brownouts, coverage ratio
            if 'DXT_POSIX' in report.records:
                dxt_df_dict = report.records['DXT_POSIX'].to_df()
                print(f"Found DXT_POSIX with {len(dxt_df_dict)} records for enrichment")

                for c in candidates:
                    rid_str     = str(c['record_id'])
                    target_type = c['type'].lower()
                    dxt_dfs=next((item for item in dxt_df_dict if item['id'] == c['record_id']), None)
                    seg_frames = []
                    for op_label, seg_key in [('read',  'read_segments'),
                                            ('write', 'write_segments')]:
                        if seg_key in dxt_dfs and dxt_dfs[seg_key] is not None:
                            df_seg = dxt_dfs[seg_key].copy()
                            if not df_seg.empty:
                                df_seg['op_type'] = op_label
                                seg_frames.append(df_seg)

                    traces = (pd.concat(seg_frames, ignore_index=True)
                            if seg_frames else pd.DataFrame()).sort_values('start_time')
                    traces['id'] = dxt_dfs['id']
                    traces['hostname'] = dxt_dfs['hostname']

                    if not traces.empty:
                        traces = traces.sort_values(['rank', 'start_time']) \
                                       if 'rank' in traces.columns \
                                       else traces.sort_values('start_time')

                        latencies     = ((traces['end_time'] - traces['start_time']) * 1000.0)
                        end_times_a   = traces['end_time'].values
                        start_times_a = traces['start_time'].values

                        tmx = _temporal_metrics(
                            start_times_a, end_times_a, c['elapsed_s']
                        )

                        gaps_brown = []
                        if 'rank' in traces.columns:
                            for _, rank_traces in traces.groupby('rank'):
                                st = rank_traces['start_time'].values
                                et = rank_traces['end_time'].values
                                last_end = start_ts
                                for i in range(len(st)):
                                    gap = st[i] - last_end
                                    if BROWNOUT_THRESHOLD_SEC < gap < c['elapsed_s']:
                                        gaps_brown.append(gap)
                                    last_end = max(last_end, et[i])
                        else:
                            last_end = start_ts
                            for i in range(len(start_times_a)):
                                gap = start_times_a[i] - last_end
                                if BROWNOUT_THRESHOLD_SEC < gap < c['elapsed_s']:
                                    gaps_brown.append(gap)
                                last_end = max(last_end, end_times_a[i])

                        dxt_coverage = len(traces) / c['count'] if c['count'] > 0 else 0.0
                        first_op_rel = float(max(start_times_a[0] - start_ts, 0.0))
                        last_op_rel  = float(min(end_times_a[-1]  - start_ts, c['elapsed_s']))

                        if first_op_rel > c['elapsed_s'] or last_op_rel < 0:
                            first_op_rel = 0.0
                            last_op_rel  = c['elapsed_s']

                        c.update({
                            'p99_latency_ms':   float(np.percentile(latencies, 99)),
                            'p95_latency_ms':   float(np.percentile(latencies, 95)),
                            'avg_latency_ms':   float(np.mean(latencies)),
                            'p99_avg_ratio':    (float(np.percentile(latencies, 99))
                                                 / max(float(np.mean(latencies)), 1e-9)),
                            'brownout_count':   len(gaps_brown),
                            'total_silence_s':  sum(gaps_brown),
                            'dxt_coverage':     dxt_coverage,
                            'dxt_active':       True,
                            'first_op_rel': max(first_op_rel, 0.0),
                            'last_op_rel':  min(last_op_rel,  elapsed),
                            **tmx,
                            'temporal_score':   0.0,
                        })
                        c['temporal_score'] = _temporal_score(c)
                    else:
                        c.update({
                            'p99_latency_ms':      c['posix_avg_latency_ms'],
                            'avg_latency_ms':      c['posix_avg_latency_ms'],
                            'p99_avg_ratio':       1.0,
                            'brownout_count':      0,
                            'total_silence_s':     0.0,
                            'dxt_coverage':        0.0,
                            'dxt_active':          False,
                            'first_op_rel': 0.0,
                            'last_op_rel':  0.0,
                            'temporal_coverage':   0.0,
                            'temporal_uniformity': 0.0,
                            'active_periods':      1,
                            'ops_per_period':      c['count'],
                            'temporal_score':      0.0,
                        })

            return {
                'timestamp':  start_ts,
                'elapsed_s':  elapsed,
                'pid':        pid,
                'log_file':   log_path,
                'candidates': candidates,
            }

    except Exception as e:
        print(f"  [ERROR] {log_path}: {e}")
        import traceback; traceback.print_exc()
        return None


def select_best_probes(all_results):
    """
    For each (filesystem, op_type) pair, select the single file whose DXT
    segments are most spread over the job lifetime (highest temporal_score),
    breaking ties by log coverage, then mean P99.
    """
    n_logs = len(all_results)

    counts = defaultdict(list)
    for res in all_results:
        for c in res['candidates']:
            key = (c['mount_pt'], c['norm_filename'], c['type'])
            counts[key].append(c)

    by_fs_op = defaultdict(list)
    for (mount_pt, norm_filename, op_type), occurrences in counts.items():
        by_fs_op[(mount_pt, op_type)].append((norm_filename, occurrences))

    best_probes = {}
    for (mount_pt, op_type), candidates in by_fs_op.items():

        def score(item):
            norm_filename, occs = item
            distinct_logs = len(set(
                res['log_file']
                for res in all_results
                for c in res['candidates']
                if (c['norm_filename'] == norm_filename
                    and c['type']      == op_type
                    and c['mount_pt']  == mount_pt)
            ))
            mean_temporal   = np.mean([c.get('temporal_score',      0.0) for c in occs])
            mean_coverage   = np.mean([c.get('temporal_coverage',   0.0) for c in occs])
            mean_uniformity = np.mean([c.get('temporal_uniformity', 0.0) for c in occs])
            mean_periods    = np.mean([c.get('active_periods',      1)   for c in occs])
            mean_p99        = np.mean([c.get('p99_latency_ms',      0.0) for c in occs])
            return (
                distinct_logs,
                mean_temporal,
                mean_coverage,
                mean_uniformity,
                mean_p99,
            ), distinct_logs, mean_temporal, mean_coverage, mean_uniformity, mean_periods

        scored = [(item, *score(item)) for item in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        (best_filename, best_occs), _, distinct_logs, t_score, t_cov, t_unif, t_periods = scored[0]

        best_probes[(mount_pt, op_type)] = (best_filename, best_occs, distinct_logs,
                                             t_score, t_cov, t_unif, t_periods)
        quality_label = _probe_quality_label(t_score, t_cov, t_unif)
        print(
            f"  FS: {mount_pt:35s}  OP: {op_type:5s}  -> {best_filename}\n"
            f"    logs: {distinct_logs}/{n_logs}  "
            f"temporal_score: {t_score:.2f}  "
            f"coverage: {t_cov:.0%}  "
            f"uniformity: {t_unif:.0%}  "
            f"active_periods: {t_periods:.1f}  "
            f"quality: {quality_label}"
        )

    return [
        {
            'mount_pt':            mount_pt,
            'op_type':             op_type,
            'norm_filename':       norm_filename,
            'occurrences':         occs,
            'n_logs':              distinct_logs,
            'probe_key':           f"{norm_filename}|{op_type}",
            'temporal_score':      t_score,
            'temporal_coverage':   t_cov,
            'temporal_uniformity': t_unif,
            'active_periods':      t_periods,
            'quality_label':       _probe_quality_label(t_score, t_cov, t_unif),
        }
        for (mount_pt, op_type), (norm_filename, occs, distinct_logs,
                                   t_score, t_cov, t_unif, t_periods)
        in sorted(best_probes.items())
    ]


# ---------------------------------------------------------------------------
# NEW: Cross-filesystem summary plot
# ---------------------------------------------------------------------------

def plot_summary(all_results, best_probes, output_dir, tz_offset=0, incident_windows=None, FS_MOUNT_ALIASES=None):
    """
    Streamlined summary figure showing all file system probes side-by-side.
    
    Optimized 3-Row Layout:
      Row 0 — Primary Latency (P99 & Avg lines + Anomaly Outlines for tail ratio)
      Row 1 — Metadata Friction (Bar chart of metadata operation latency)
      Row 2 — System Availability (Bar chart of brownout silences/dead zones)
      
    Features:
      - Probe quality indicators (stars/scores) are promoted to column headers.
      - Total visual footprint scaled down from 22" to 12" height for modern displays.
      - Incident shading spans all three metrics vertically to aid correlation.
      - Embedded diagnostic "Points of Attention" text boxes for easier analysis.
    """
    if FS_MOUNT_ALIASES is None:
        FS_MOUNT_ALIASES = {}

    os.makedirs(output_dir, exist_ok=True)
    if not best_probes:
        return

    MAX_COLS = 6       # Maximum columns per page
    tz_label = f"UTC{'+' if tz_offset >= 0 else ''}{tz_offset}"

    probe_series = []   # Consolidated dataset, sorted per probe
    all_times = set()

    for probe in best_probes:
        mount_pt = probe['mount_pt']
        op_type  = probe['op_type']
        fname    = probe['norm_filename']
        display  = FS_MOUNT_ALIASES.get(mount_pt, mount_pt)
        short_fs = display#.split('/')[-1] or display
        label    = f"{short_fs}\n[{op_type}]"

        rows = []
        for res in all_results:
            for c in res['candidates']:
                if (c['norm_filename'] == fname
                        and c['type']     == op_type
                        and c['mount_pt'] == mount_pt):
                    dt = (datetime.fromtimestamp(res['timestamp'], tz=timezone.utc)
                          + timedelta(hours=tz_offset)).replace(tzinfo=None)
                    rows.append({
                        'time':      dt,
                        'p99':       c.get('p99_latency_ms',  0.0),
                        'avg':       c.get('avg_latency_ms',  0.0),
                        'ratio':     c.get('p99_avg_ratio',   1.0),
                        'meta_lat':  c.get('meta_lat_ms',     0.0),
                        'silence':   c.get('total_silence_s', 0.0),
                        'brownouts': c.get('brownout_count',  0),
                    })
                    all_times.add(dt)

        rows.sort(key=lambda r: r['time'])
        probe_series.append({
            'label':         label,
            'quality_score': probe.get('temporal_score', 0.0),
            'rows':          rows,
        })

    # Sort probes by quality score descending so they are grouped logically by reliability tier
    probe_series.sort(key=lambda x: x['quality_score'], reverse=True)

    if not any(ps['rows'] for ps in probe_series):
        print("  [summary] No data to plot.")
        return

    all_times_sorted = sorted(all_times)
    
    # Global time axis limits
    if all_times_sorted:
        x_min = all_times_sorted[0]  - timedelta(hours=1.5)
        x_max = all_times_sorted[-1] + timedelta(hours=1.5)
    else:
        x_min = x_max = datetime.utcnow()

    groups = {
        "High Quality Tiers (score >= 0.5)": [],
        "Low Quality Tiers (score < 0.5)": []
    }

    for ps in probe_series:
        score = ps['quality_score']
        if score >= 0.5:
            groups["High Quality Tiers (score >= 0.5)"].append(ps)
        else:
            groups["Low Quality Tiers (score < 0.5)"].append(ps)

    # Cohesive color palette for differentiating overlapping file system lines
    colors_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    for group_name, group_probes in groups.items():
        if not group_probes:
            continue  # Skip empty tiers

        # Define 3 rows for consolidated views: Latency, Metadata, and Gaps
        N_ROWS = 3
        fig, axes = plt.subplots(
            N_ROWS, 1, 
            figsize=(13, 9.5), 
            sharex=True, 
            gridspec_kw={'height_ratios': [4, 3, 3]}
        )
        
        fig.suptitle(
            f"Cross-Filesystem Health Summary - {group_name}\n"
            f"{len(all_results)} log(s) aggregated  |  {tz_label}",
            fontsize=13, fontweight='bold', y=0.98
        )

        # Plot each file system in the group onto the shared axis
        for idx, ps in enumerate(group_probes):
            color = colors_palette[idx % len(colors_palette)]
            times     = [r['time']      for r in ps['rows']]
            p99s      = [r['p99']       for r in ps['rows']]
            avgs      = [r['avg']       for r in ps['rows']]
            ratios    = [r['ratio']     for r in ps['rows']]
            meta_lat  = [r['meta_lat']  for r in ps['rows']]
            silences  = [r['silence']   for r in ps['rows']]

            clean_label = ps['label'].replace('\n', ' ')

            # ── Row 0: Latency Timelines (P99 solid, Average dashed) ──
            axes[0].plot(times, p99s, color=color, marker='o', markersize=3.5, 
                         linewidth=1.4, label=f"{clean_label} (P99)", alpha=0.9)
            axes[0].plot(times, avgs, color=color, linestyle='--', marker='s', 
                         markersize=2, linewidth=0.8, label=f"{clean_label} (Avg)", alpha=0.5)

            # Highlight extreme tail blowouts with dark ring markers
            high_ratio_times = [t for t, r in zip(times, ratios) if r >= 3.5]
            high_ratio_p99s  = [p for p, r in zip(p99s, ratios) if r >= 3.5]
            if high_ratio_times:
                axes[0].scatter(high_ratio_times, high_ratio_p99s, s=65, facecolors='none', 
                                edgecolors='#e63946', linewidths=1.2, zorder=5)

            # ── Row 1: Metadata Performance ──
            axes[1].plot(times, meta_lat, color=color, marker='^', markersize=3, 
                         linewidth=1.2, label=clean_label, alpha=0.85)

            # ── Row 2: Availability & Gaps ──
            axes[2].plot(times, silences, color=color, marker='x', markersize=4, 
                         linewidth=1.2, label=clean_label, alpha=0.85)

        # ---------------------------------------------------------
        # Styling & Annotations
        # ---------------------------------------------------------
        
        # Row 0 Styling & Explanations
        axes[0].set_ylabel('I/O Latency (ms)', fontsize=8.5, fontweight='bold')
        axes[0].grid(True, alpha=0.2, linestyle=':')
        axes[0].legend(fontsize=7, loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0)
        axes[0].set_title("Data Path Latency Profiles", fontsize=9, fontweight='bold', loc='left')
        axes[0].text(1.01, 0.0, 
                     "Points of Attention:\n"
                     "• Red circles: Extreme tail blowouts (P99 >> Avg)\n"
                     "• P99/Avg gap: Shows inconsistent, jittery performance\n"
                     "• Shared spikes: Global bottleneck across mounts",
                     transform=axes[0].transAxes, fontsize=8, color='#111',
                     verticalalignment='bottom', 
                     bbox=dict(boxstyle='round,pad=0.5', facecolor='#f8f9fa', edgecolor='#ced4da', alpha=0.85))

        # Row 1 Styling & Explanations
        axes[1].set_ylabel('Meta Latency (ms)', fontsize=8.5, fontweight='bold')
        axes[1].grid(True, alpha=0.2, linestyle=':')
        axes[1].legend(fontsize=7, loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0)
        axes[1].set_title("Metadata Action Friction", fontsize=9, fontweight='bold', loc='left')
        axes[1].text(1.01, 0.0, 
                     "Points of Attention:\n"
                     "• Spikes indicate directory or inode lock contention\n"
                     "• High latency delays file discovery/creation\n"
                     "• Often precedes or predicts full data path hangs",
                     transform=axes[1].transAxes, fontsize=8, color='#111',
                     verticalalignment='bottom', 
                     bbox=dict(boxstyle='round,pad=0.5', facecolor='#f8f9fa', edgecolor='#ced4da', alpha=0.85))

        # Row 2 Styling & Explanations
        axes[2].set_ylabel('Silence Duration (s)', fontsize=8.5, fontweight='bold')
        axes[2].grid(True, alpha=0.2, linestyle=':')
        axes[2].legend(fontsize=7, loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0)
        axes[2].set_title("Unresponsive Brownout Gaps", fontsize=9, fontweight='bold', loc='left')
        axes[2].text(1.01, 0.0, 
                     "Points of Attention:\n"
                     "• Non-zero values = complete application I/O hang\n"
                     "• Critical indicator of system \"dead zones\"\n"
                     "• Look for overlap with shaded incident windows",
                     transform=axes[2].transAxes, fontsize=8, color='#111',
                     verticalalignment='bottom', 
                     bbox=dict(boxstyle='round,pad=0.5', facecolor='#f8f9fa', edgecolor='#ced4da', alpha=0.85))
        
        # Configure global shared time limits and formatting
        for ax in axes:
            ax.set_xlim(x_min, x_max)
            ax.tick_params(axis='both', labelsize=7.5)
            
            # Global vertical Incident Shading
            if incident_windows:
                INCIDENT_COLORS = {'CVE': '#A32D2D', 'brownout': '#185FA5'}
                for label, inc_start, inc_end in incident_windows:
                    color = INCIDENT_COLORS.get(label.split()[0], '#6c757d')
                    ax.axvspan(inc_start, inc_end, color=color, alpha=0.06, zorder=0)

        # Format date ticks cleanly on the shared x-axis (bottom plot only)
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d\n%H:%M'))
        
        # Save a separate summary asset for each quality group
        group_suffix = group_name.split()[0].lower()
        out_path = os.path.join(output_dir, f"summary_grouped_{group_suffix}.png")
        
        # bbox_inches='tight' ensures the generated right-aligned text boxes are captured cleanly
        plt.savefig(out_path, dpi=160, bbox_inches='tight')
        plt.close(fig)
        print(f"  Generated grouped summary plot ({group_name}): {out_path}")

        
def plot_analysis(all_results, best_probes, output_dir, tz_offset=0, incident_windows=None):
    """
    5-panel plot per probe:
      1. P99 vs Avg latency          (masking detector)
      2. P99/Avg ratio               (early warning — divergence before absolute spike)
      3. Metadata latency & opens    (contention leading indicator)
      4. Brownout silence            (stall detector)
      5. I/O size + DXT coverage     (normalisation + sampling quality)
    """
    os.makedirs(output_dir, exist_ok=True)
    tz_label = f"UTC{'+' if tz_offset >= 0 else ''}{tz_offset}"

    for probe in best_probes:
        mount_pt   = probe['mount_pt']
        op_type    = probe['op_type']
        fname      = probe['norm_filename']
        n_logs     = probe['n_logs']
        total_logs = len(all_results)

        data = []
        for res in all_results:
            for c in res['candidates']:
                if (c['norm_filename'] == fname
                        and c['type']     == op_type
                        and c['mount_pt'] == mount_pt):
                    dt = datetime.fromtimestamp(res['timestamp'], tz=timezone.utc) + timedelta(hours=tz_offset)
                    data.append({
                        'time':          dt.replace(tzinfo=None),
                        'p99':           c.get('p99_latency_ms',   0),
                        'avg':           c.get('avg_latency_ms',   0),
                        'p99_avg_ratio': c.get('p99_avg_ratio',    1.0),
                        'silence':       c.get('total_silence_s',  0),
                        'size':          c.get('avg_size',         0),
                        'dxt_coverage':  c.get('dxt_coverage',     0),
                        'meta_lat_ms':   c.get('meta_lat_ms',      0),
                        'open_rate':     c.get('open_rate_per_s',  0),
                        'seeks_per_op':  c.get('seeks_per_op',     0),
                        'lock_wait_s':   c.get('lock_wait_s',      0),
                        'cov_start':     c.get('first_op_rel', 0),
                        'cov_end':       c.get('last_op_rel', 0),
                        'job_len':       c.get('elapsed_s', 1)
                    })

        data.sort(key=lambda x: x['time'])
        if not data:
            continue

        times        = [d['time']          for d in data]
        p99s         = [d['p99']           for d in data]
        avgs         = [d['avg']           for d in data]
        ratios       = [d['p99_avg_ratio'] for d in data]
        silences     = [d['silence']       for d in data]
        sizes        = [d['size']          for d in data]
        coverages    = [d['dxt_coverage']  for d in data]
        meta_lats    = [d['meta_lat_ms']   for d in data]
        open_rates   = [d['open_rate']     for d in data]
        seeks_per_op = [d['seeks_per_op']  for d in data]
        lock_waits   = [d['lock_wait_s']   for d in data]

        mean_coverage = np.mean(coverages) if coverages else 0.0
        dxt_warning   = mean_coverage < 0.5


        fig, axes = plt.subplots(6, 1, figsize=(14, 18), sharex=True)
        display_mount = FS_MOUNT_ALIASES.get(mount_pt, mount_pt)
        quality_label = probe.get('quality_label', '')
        fig.suptitle(
            f"FS: {display_mount}  |  Probe: {fname} [{op_type}]  |  "
            f"Coverage: {n_logs}/{total_logs} logs  |  {quality_label}",
            fontsize=11, fontweight='bold', y=0.99
        )

        # Panel 1 — Tail vs Average latency
        ax = axes[0]
        ax.plot(times, p99s, 'r-o',  label='P99 Latency (Tail)',    alpha=0.8, markersize=4)
        ax.plot(times, avgs, 'b--s', label='Avg Latency (Job Mean)', alpha=0.6, markersize=4)
        ax.set_ylabel('Latency (ms)  |  seeks/op')
        ax.set_title(
            'Tier 1 — Data Latency: P99 vs Average (masking detector)'
            + (' ⚠️  DXT coverage < 0.5 — P99 = POSIX avg, not true tail' if dxt_warning else '')
        )
        ax.legend(); ax.grid(True, alpha=0.3)

        # Panel 2 — P99/Avg ratio with adaptive baseline
        ax = axes[1]
        ax.plot(times, ratios, 'm-D', label='P99 / Avg Ratio', alpha=0.8, markersize=4)

        if len(ratios) >= 3:
            n_baseline = max(len(ratios) // 3, 2)
            baseline_window = sorted(ratios)[:n_baseline]
            baseline_median = float(np.median(baseline_window))
            baseline_std    = float(np.std(baseline_window))
            alert_thresh    = baseline_median + max(2.0 * baseline_std,
                                                    0.3 * baseline_median)
            crit_thresh     = baseline_median + max(4.0 * baseline_std,
                                                    0.6 * baseline_median)
        else:
            baseline_median = float(np.median(ratios)) if ratios else 1.0
            alert_thresh    = 2.0
            crit_thresh     = 5.0

        ax.axhline(y=baseline_median, color='green',  linestyle=':',  alpha=0.5,
                   label=f'Baseline median ({baseline_median:.1f}×)')
        ax.axhline(y=alert_thresh,    color='orange', linestyle='--', alpha=0.6,
                   label=f'Alert threshold ({alert_thresh:.1f}×)')
        ax.axhline(y=crit_thresh,     color='red',    linestyle='--', alpha=0.6,
                   label=f'Critical threshold ({crit_thresh:.1f}×)')
        lower_bound = baseline_median * 0.5
        ax.axhline(y=lower_bound, color='purple', linestyle=':',  alpha=0.6,
                   label=f'Silence alert ({lower_bound:.1f}×)')
        for t, r in zip(times, ratios):
            if r < lower_bound:
                ax.axvspan(t - timedelta(hours=1), t + timedelta(hours=1),
                           color='purple', alpha=0.07, zorder=0)
        ax.set_ylabel('Ratio')
        ax.set_title('Tier 3 — Tail Amplification: P99/Avg ratio (adaptive baseline)')
        ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
        if dxt_warning:
            axes[1].set_facecolor('#fff0f0')
            axes[1].text(
                0.5, 0.5, 'P99/Avg ratio unreliable\n(DXT coverage < 0.5)',
                transform=axes[1].transAxes,
                ha='center', va='center', fontsize=11, color='red', alpha=0.6,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.5)
            )

        # Panel 3 — Metadata latency + open rate
        ax   = axes[2]
        ax2b = ax.twinx()

        ax.plot(times, meta_lats,   'c-^', label='Metadata Lat (ms)', alpha=0.8, markersize=4)
        ax.plot(times, seeks_per_op,'k:x', label='Seeks/op',          alpha=0.6, markersize=4)
        ax2b.plot(times, open_rates,'g--o', label='Open rate (/s)',   alpha=0.5, markersize=3)
        ax2b.plot(times, lock_waits,'r:s',  label='Lock wait (s)',    alpha=0.5, markersize=3)

        valid_meta = [v for v in meta_lats if v > 1e-6]
        if len(valid_meta) >= 3:
            n_base_m        = max(len(valid_meta) // 3, 2)
            meta_base_win   = sorted(valid_meta)[:n_base_m]
            meta_base_med   = float(np.median(meta_base_win))
            meta_base_std   = float(np.std(meta_base_win))
            meta_alert      = meta_base_med + max(2.0 * meta_base_std,
                                                   0.5 * meta_base_med)
            meta_crit       = meta_base_med + max(4.0 * meta_base_std,
                                                   1.0 * meta_base_med)
            ax.axhline(y=meta_base_med, color='green',  linestyle=':',  alpha=0.5,
                       label=f'Meta baseline ({meta_base_med:.3f} ms)')
            ax.axhline(y=meta_alert,    color='orange', linestyle='--', alpha=0.6,
                       label=f'Meta alert ({meta_alert:.3f} ms)')
            ax.axhline(y=meta_crit,     color='red',    linestyle='--', alpha=0.6,
                       label=f'Meta critical ({meta_crit:.3f} ms)')

            for t, ml in zip(times, meta_lats):
                if ml > meta_crit:
                    ax.axvspan(t - timedelta(hours=1), t + timedelta(hours=1),
                               color='red', alpha=0.07, zorder=0)
                elif ml > meta_alert:
                    ax.axvspan(t - timedelta(hours=1), t + timedelta(hours=1),
                               color='orange', alpha=0.07, zorder=0)

        ax.set_ylabel('ms  /  seeks per op')
        ax2b.set_ylabel('opens/s  |  lock wait (s)', color='green')
        ax.set_title('Tier 2 — Contention Indicators: metadata latency (adaptive alert), '
                     'open rate, seeks, lock waits')
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2b.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, fontsize=7, ncol=2)
        ax.grid(True, alpha=0.3)

        # Panel 4 — Brownout silence
        ax = axes[3]
        ax.bar(times, silences, width=0.005, color='orange',
               label='Total Silence (stalls > 5s)', align='center')
        ax.set_ylabel('Silence (s)')
        ax.set_title(f'Tier 1 — Brownout Detection: silence gaps > {BROWNOUT_THRESHOLD_SEC}s')
        ax.legend(); ax.grid(True, alpha=0.3)

        # Panel 5 — I/O size + DXT coverage quality + size change rate
        ax      = axes[4]
        ax_cov  = ax.twinx()
        ax_delta = ax.twinx()
        ax_delta.spines['right'].set_position(('outward', 60))

        ax.plot(times, sizes, 'g-^', label='Avg I/O Size (bytes)', alpha=0.7, markersize=4)
        ax.set_ylabel('Size (Bytes)')
        ax.yaxis.label.set_color('green')

        ax_cov.plot(times, coverages, 'b--o', label='DXT Coverage ratio', alpha=0.6, markersize=3)
        ax_cov.axhline(y=0.5, color='red', linestyle=':', alpha=0.5,
                       label='Coverage < 0.5 (P99 unreliable)')
        ax_cov.set_ylabel('DXT Coverage (0–1)', color='blue')
        ax_cov.set_ylim(0, 1.05)

        if len(sizes) > 1:
            size_change_pct = [0.0] + [
                abs(sizes[i] - sizes[i-1]) / max(sizes[i-1], 1) * 100
                for i in range(1, len(sizes))
            ]
            ax_delta.plot(times, size_change_pct, 'r:v',
                          label='Size Δ% vs prev job', alpha=0.5, markersize=3)
            ax_delta.axhline(y=10.0, color='orange', linestyle='--', alpha=0.4,
                             label='10% size shift alert')
        ax_delta.set_ylabel('Size Change (%)', color='red')
        ax_delta.yaxis.label.set_color('red')

        ax.set_title('Tier 3 — Normalisation: I/O size consistency + DXT sampling quality')

        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax_cov.get_legend_handles_labels()
        lines3, labels3 = ax_delta.get_legend_handles_labels()
        ax.legend(lines1 + lines2 + lines3, labels1 + labels2 + labels3,
                  fontsize=8, loc='upper left')
        ax.grid(True, alpha=0.3)

        # Panel 6 — Temporal spread quality + active I/O window
        ax = axes[5]

        t_covs   = []
        t_unifs  = []
        t_scores = []
        for res in sorted(all_results, key=lambda r: r['timestamp']):
            for c in res['candidates']:
                if (c['norm_filename'] == fname
                        and c['type']     == op_type
                        and c['mount_pt'] == mount_pt):
                    t_covs.append(c.get('temporal_coverage',   0.0))
                    t_unifs.append(c.get('temporal_uniformity', 0.0))
                    t_scores.append(c.get('temporal_score',     0.0))

        ax_score = ax.twinx()

        for i, d in enumerate(data):
            job_start  = d['time']
            job_dur    = timedelta(seconds=d['job_len'])
            ax.broken_barh([(job_start, job_dur)], (0.05, 0.4),
                           facecolors='gray', edgecolor='gray',
                           linewidth=0.8, alpha=0.6)
            active_start = job_start + timedelta(seconds=d['cov_start'])
            active_dur   = timedelta(seconds=max(d['cov_end'] - d['cov_start'], 1))
            ax.broken_barh([(active_start, active_dur)], (0.05, 0.4),
                           facecolors='tab:blue', alpha=0.7)

        if t_scores:
            ax_score.plot(times, t_scores, 'k-o',  label='Temporal score',   alpha=0.9, markersize=4)
            ax_score.plot(times, t_covs,   'b--^', label='Coverage fraction', alpha=0.6, markersize=3)
            ax_score.plot(times, t_unifs,  'g:s',  label='Uniformity',        alpha=0.6, markersize=3)
            ax_score.axhline(y=0.5, color='orange', linestyle='--', alpha=0.5,
                             label='0.5 quality threshold')
            ax_score.set_ylim(0, 1.15)
            ax_score.set_ylabel('Score (0–1)', color='black')

        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.set_xlabel(f"Timeline ({tz_label})")
        ax.set_title('Tier 0 — Probe quality: temporal spread score + active I/O window vs job duration')

        from matplotlib.patches import Patch
        bar_legend = [
            Patch(facecolor='lightgray', alpha=0.5, label='Job duration'),
            Patch(facecolor='tab:blue',  alpha=0.7, label='Active I/O window'),
        ]
        lines_l, labels_l = ax_score.get_legend_handles_labels()
        ax.legend(bar_legend + lines_l, [h.get_label() for h in bar_legend] + labels_l,
                  fontsize=8, loc='upper left')
        ax.grid(True, alpha=0.3)

        if incident_windows:
            INCIDENT_COLORS = {'CVE': '#A32D2D', 'brownout': '#185FA5'}
            for label, inc_start, inc_end in incident_windows:
                color = INCIDENT_COLORS.get(label.split()[0], 'gray')
                for ax in axes:
                    ax.axvspan(inc_start, inc_end,
                            color=color, alpha=0.08, zorder=0,
                            label=f'_nolegend_')
                axes[0].axvspan(inc_start, inc_end,
                                color=color, alpha=0.08, zorder=0,
                                label=f'Incident: {label}')
            axes[0].legend(fontsize=8)
        plt.tight_layout()
        mount_tag = mount_pt.strip('/').replace('/', '_') or 'root'
        out_path  = os.path.join(output_dir,
                                 f"analysis_{mount_tag}_{fname}_{op_type}.png")
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Generated plot: {out_path}")

def generate_summary_report(all_results, best_probes, output_dir, tz_offset=0):
    """
    Analyzes the aggregated data to identify possible issues (metadata contention,
    latency creep, brownouts) and workload shifts (I/O size, seek rates).
    Prints to console and saves to summary_report.txt.
    """
    report_lines = []
    report_lines.append("="*80)
    report_lines.append(f" FILESYSTEM HEALTH & WORKLOAD SHIFT SUMMARY (TZ offset: {tz_offset}h) ")
    report_lines.append("="*80)

    anomalies_timeline = []

    for probe in best_probes:
        mount_pt = probe['mount_pt']
        op_type = probe['op_type']
        fname = probe['norm_filename']

        data = []
        for res in all_results:
            for c in res['candidates']:
                if c['norm_filename'] == fname and c['type'] == op_type and c['mount_pt'] == mount_pt:
                    data.append({
                        'time': res['timestamp'],
                        'p99': c.get('p99_latency_ms', 0),
                        'avg': c.get('avg_latency_ms', 0),
                        'meta_lat': c.get('meta_lat_ms', 0),
                        'size': c.get('avg_size', 0),
                        'seeks': c.get('seeks_per_op', 0),
                        'silence': c.get('total_silence_s', 0)
                    })
        data.sort(key=lambda x: x['time'])

        if len(data) < 4:
            continue

        report_lines.append(f"\n--- FS: {mount_pt} | Probe: {fname} [{op_type}] ---")

        midpoint = len(data) // 2
        early = data[:midpoint]
        late = data[midpoint:]

        issues_found = False

        # 1. Metadata Contention
        meta_baseline = np.median([d['meta_lat'] for d in early if d['meta_lat'] > 1e-6]) if early else 0.0
        meta_std = np.std([d['meta_lat'] for d in early if d['meta_lat'] > 1e-6]) if early else 0.0
        meta_thresh = meta_baseline + max(2.0 * meta_std, 0.5 * meta_baseline) if meta_baseline > 0 else 0.1

        meta_spikes = [d for d in data if d['meta_lat'] > meta_thresh and d['meta_lat'] > 0.5]
        if meta_spikes:
            issues_found = True
            report_lines.append(f"  [!] Metadata Contention: Detected {len(meta_spikes)} significant spike(s).")
            max_spike = max(meta_spikes, key=lambda x: x['meta_lat'])
            dt = datetime.fromtimestamp(max_spike['time'], tz=timezone.utc) + timedelta(hours=tz_offset)
            report_lines.append(f"      - Max spike around {dt.strftime('%m-%d %H:%M')}: {max_spike['meta_lat']:.2f} ms/open (Baseline: ~{meta_baseline:.2f} ms)")
            for s in meta_spikes:
                anomalies_timeline.append((s['time'], mount_pt, 'Metadata Contention'))

        # 2. I/O Size Shift
        early_size = np.mean([d['size'] for d in early])
        late_size = np.mean([d['size'] for d in late])
        if early_size > 0 and abs(late_size - early_size) / early_size > 0.15:
            issues_found = True
            dir_str = "decreased" if late_size < early_size else "increased"
            report_lines.append(f"  [*] I/O Size Shift: Average size {dir_str} from {early_size/1024:.1f} KB to {late_size/1024:.1f} KB.")

        # 3. Seek Load Increase
        early_seeks = np.mean([d['seeks'] for d in early])
        late_seeks = np.mean([d['seeks'] for d in late])
        if late_seeks > early_seeks + 1.0 or (early_seeks > 0 and (late_seeks - early_seeks)/early_seeks > 0.3):
            issues_found = True
            report_lines.append(f"  [*] Seek Load Shift: Average seeks/op increased from ~{early_seeks:.1f} to ~{late_seeks:.1f}.")

        # 4. Latency Creep
        early_avg_lat = np.mean([d['avg'] for d in early])
        late_avg_lat = np.mean([d['avg'] for d in late])
        if early_avg_lat > 0 and late_avg_lat > early_avg_lat * 1.3:
            issues_found = True
            increase_pct = ((late_avg_lat/early_avg_lat)-1)*100
            report_lines.append(f"  [!] Latency Creep: Job mean latency increased by {increase_pct:.0f}% in later jobs.")

        # 5. Brownouts / Stalls
        total_silence_jobs = sum(1 for d in data if d['silence'] > 0)
        if total_silence_jobs > 0:
            issues_found = True
            report_lines.append(f"  [X] Brownouts Detected: {total_silence_jobs} job(s) experienced extended I/O silence/stalls.")

        if not issues_found:
            report_lines.append("  [OK] No significant anomalies or load shifts detected.")

    report_lines.append("\n" + "="*80)
    report_lines.append(" CORRELATED SYSTEM-WIDE EVENTS (Possible Shared FS Load/Outages) ")
    report_lines.append("="*80)

    events_by_hour = defaultdict(set)
    for ts, fs, issue in anomalies_timeline:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(hours=tz_offset)
        hour_bin = dt.replace(minute=0, second=0, microsecond=0)
        events_by_hour[hour_bin].add(fs)

    shared_events = False
    for dt, fses in sorted(events_by_hour.items()):
        if len(fses) > 1:
            shared_events = True
            report_lines.append(f"  - {dt.strftime('%Y-%m-%d %H:%M')}: Correlated issues observed on {len(fses)} filesystems:")
            for fs in sorted(list(fses)):
                report_lines.append(f"      * {fs}")

    if not shared_events:
        report_lines.append("  - No strongly correlated multi-filesystem events detected.")

    report_lines.append("="*80 + "\n")

    report_text = "\n".join(report_lines)
    print(report_text)

    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "summary_report.txt")
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"-> Automated Summary report saved to {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Darshan DXT Brownout & Tail Latency Analyzer')
    parser.add_argument('files',        nargs='*',  help='Darshan log files')
    parser.add_argument('--tz-offset', type=int, default=0, help='UTC offset in hours')
    parser.add_argument('--max-size',   type=int,   default=1048576,
                        help='Max avg I/O size in bytes for general FSes (default: 1 MB). '
                             'Overridden per-FS by FS_SIZE_OVERRIDES.')
    parser.add_argument('--min-ops',    type=int,   default=5,
                        help='Min operations per file record')
    parser.add_argument('--fs-pattern',             help='Regex/glob for FS path filtering')
    parser.add_argument('--output-dir', '-o',       default='plots')
    parser.add_argument('--workers',    type=int,   default=8,
                        help='Parallel worker processes (default: 8)')
    parser.add_argument('--incident', action='append', default=[],
                        metavar='LABEL,START,END',
                        help='Known incident window e.g. "CVE,2024-04-29T16:00,2024-04-29T23:00" '
                             '(local time matching --tz-offset). Repeatable.')
    parser.add_argument('--no-summary-plot', action='store_true',
                        help='Skip the cross-filesystem summary plot.')
    args = parser.parse_args()
 
    if not HAS_DEPS:
        print("Error: Missing dependencies (pydarshan, numpy, matplotlib, pandas).")
        sys.exit(1)
 
    n_files = len(args.files)
    print(f"Scanning {n_files} log(s) with up to {args.workers} worker(s)...")
 
    worker_args = [
        (f, args.max_size, args.min_ops, None, args.fs_pattern)
        for f in args.files
    ]
 
    all_results = []
    pool = ProcessPoolExecutor(max_workers=args.workers)
 
    # Ensure workers are reaped on Ctrl+C or SIGTERM, not left as zombies.
    import signal
 
    def _shutdown(signum, frame):
        print(f"\n[signal {signum}] Shutting down workers…", flush=True)
        pool.shutdown(wait=False, cancel_futures=True)
        sys.exit(1)
 
    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
 
    try:
        futures = {pool.submit(_analyze_log_worker, a): a[0] for a in worker_args}
        for i, future in enumerate(as_completed(futures), 1):
            log_path = futures[future]
            try:
                res = future.result()
            except Exception as e:
                print(f"  [ERROR] {log_path}: {e}")
                res = None
            status = f"{len(res['candidates'])} candidate(s)" if res else "no candidates"
            print(f"  [{i}/{n_files}] {os.path.basename(log_path)} — {status}")
            if res:
                all_results.append(res)
    finally:
        # cancel_futures=True cancels pending work; wait=True reaps all worker
        # processes before we continue — prevents leftover <defunct> entries.
        pool.shutdown(wait=True, cancel_futures=True)
 
    if not all_results:
        print("No candidates found matching the criteria.")
        return
 
    print(f"\nSelecting best probe per filesystem:")
    best = select_best_probes(all_results)
 
    print(f"\nTop Probe Candidates (best per FS × op_type, across {len(all_results)} log(s)):")
    for probe in best:
        print(f"  - FS: {probe['mount_pt']:35s}  OP: {probe['op_type']:5s}  "
              f"file: {probe['norm_filename']}  "
              f"[{probe['n_logs']}/{len(all_results)} logs, "
              f"{len(probe['occurrences'])} record(s)]")
 
    return best
    print("\nGenerating Automated Issue & Load Shift Summary...")
    generate_summary_report(all_results, best, args.output_dir, args.tz_offset)
 
    incident_windows = []
    for inc in args.incident:
        parts = inc.split(',', 2)
        if len(parts) == 3:
            label, start_str, end_str = parts
            fmt = '%Y-%m-%dT%H:%M'
            incident_windows.append((
                label,
                datetime.strptime(start_str, fmt),
                datetime.strptime(end_str,   fmt),
            ))
 
    if not args.no_summary_plot:
        print(f"\nGenerating cross-filesystem summary plot -> {args.output_dir}/")
        plot_summary(all_results, best, args.output_dir,
                     args.tz_offset, incident_windows)
 
    print(f"\nGenerating per-probe plots -> {args.output_dir}/")
    plot_analysis(all_results, best, args.output_dir,
                  args.tz_offset, incident_windows)
 
 
if __name__ == "__main__":
    # Required on Windows / macOS (spawn start method) so that worker
    # processes can import this module without re-executing main().
    import multiprocessing
    multiprocessing.freeze_support()
    main()
