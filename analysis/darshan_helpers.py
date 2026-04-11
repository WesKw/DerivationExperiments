from collections.abc import Callable

import darshan as dardarbinks
import darshan.backend.cffi_backend as backend
import pandas as pd
import dask.dataframe as dd
import re
import json
import sys
sys.path.append("../")

# import generate_file_trace_csv.generate_worker_mapping_via_logdir as generate_worker_mapping_via_logdir

from pathlib import Path
from glob import glob
from dataclasses import dataclass
from generate_file_trace_csv import generate_worker_mapping_via_logdir

METADATA_COLUMNS=["file_name", "id", "process", "basename", "max_events", "nprocs", "container", "limit_cpu", "run"]


@dataclass
class FrameDxt:
    max_events: int
    nthreads: int
    nprocs: int
    container: str
    limit_cpu: bool
    experiment_name: str
    experiment_type: str
    dataframe: dd.DataFrame


# loads data from runargs file and places it in the dataframe
# modifies the dataframe instead of returning a new one.
def get_runargs_data(directory: Path, df: pd.DataFrame, job: str):
    # add config-specific options to df
    with open(directory.joinpath(f"runargs.{job}.py")) as file:
        data = ''.join(file.readlines())
        max_events = -1
        nprocs = 0
        nthreads = 0

        try:
            max_events = next(re.finditer(r"maxEvents = [\d]+", data)).group(0).replace(' ', '').split('=')[1]
        except:
            pass

        try:
            nprocs = next(re.finditer(r"nprocs = [\d]+", data)).group(0).replace(' ', '').split('=')[1]
            nthreads = next(re.finditer(r"threads = [\d]+", data)).group(0).replace(' ', '').split('=')[1]
            # print(nprocs)
        except:
            raise RuntimeError("Could not find nprocs or nthreads in runargs file.")

        df["max_events"] = int(max_events)
        df["nprocs"] = int(nprocs)
        df["nthreads"] = int(nthreads)
        if nprocs == 8:
            print(directory.parents[1].name)
            if directory.parents[1].name == "shifter":
                print("shifter has 8 proc data")
        # print(list(directory.parents))
        df["container"] = directory.parents[1].name
        df["limit_cpu"] = bool(directory.parents[0].name.capitalize())
        df["run"] = directory.name
        # df["experiment_name"] = directory.parents[3].name
        # df["experiment_type"] = directory.parents[4].name


def get_runargs_data_dxt(directory: Path, df: dd.DataFrame, job: str) -> FrameDxt:
    # add config-specific options to df
    with open(directory.joinpath(f"runargs.{job}.py")) as file:
        data = ''.join(file.readlines())
        max_events = -1
        nprocs = 0
        nthreads = 0

        try:
            max_events = next(re.finditer(r"maxEvents = [\d]+", data)).group(0).replace(' ', '').split('=')[1]
        except:
            pass

        try:
            nprocs = next(re.finditer(r"nprocs = [\d]+", data)).group(0).replace(' ', '').split('=')[1]
            nthreads = next(re.finditer(r"threads = [\d]+", data)).group(0).replace(' ', '').split('=')[1]
            # print(nprocs)
        except:
            raise RuntimeError("Could not find nprocs or nthreads in runargs file.")

        dxt_run_data = FrameDxt(int(max_events), int(nthreads), int(nprocs), directory.parents[1].name, bool(directory.parents[0].name), directory.parents[3].name, directory.parents[4].name, df)
        return dxt_run_data
        # df["max_events"] = int(max_events)
        # df["nprocs"] = int(nprocs)
        # df["nthreads"] = int(nthreads)
        # # print(list(directory.parents))
        # df["container"] = directory.parents[1].name
        # df["limit_cpu"] = bool(directory.parents[0].name)
        # df["run"] = directory.name
        # df["experiment_name"] = directory.parents[3].name
        # df["experiment_type"] = directory.parents[4].name


def load_darshan_data_dxt(log_file: str, dxt_operations: list = [], dxt_include=["offset", "length", "start_time", "end_time"]) -> pd.DataFrame:
    report = dardarbinks.DarshanReport(str(log_file), read_all=True)
    # get files that were traced by darshan
    log = backend.log_open(str(log_file))
    # dxt_df = dd.from_pandas(pd.DataFrame(columns=['id', 'file_name', 'hostname', 'operation', 'offset', 'length', 'start_time', 'end_time']))
    # dxt_df = pd.DataFrame(columns=["id", "operation", "offset", "length", "start_time", "end_time"])
    dxt_df = pd.DataFrame(columns=["id", "operation"] + dxt_include)
    to_drop = set("offset", "length", "start_time", "end_time") - set(dxt_include)

    if "DXT_POSIX" in report.records:
        dxt_data = report.records["DXT_POSIX"].to_df() # list not a dict
        for data in dxt_data:
            file_id = data['id']
            host = data['hostname']
            file_names = backend.log_lookup_name_records(log, [file_id])
            
            # pull dxt data into a single dataframe
            if not data['write_segments'].empty and 'write' in dxt_operations:
                data['write_segments'].insert(0, 'operation', 'write')
                data['write_segments'].insert(0, 'id', file_id)
                data['write_segments'] = data['write_segments'].drop(columns=to_drop)
                # data['write_segments'].insert(0, 'file_name', file_names[file_id])
                # data['write_segments'].insert(0, 'hostname', host)
                dxt_df = pd.concat([dxt_df, data['write_segments']], ignore_index=True)

            if not data['read_segments'].empty and 'read' in dxt_operations:
                data['read_segments'].insert(0, 'operation', 'read')
                data['read_segments'].insert(0, 'id', file_id)
                data['read_segments'] = data['read_segments'].drop(columns=to_drop)
                # data['read_segments'].insert(0, 'file_name', file_names[file_id])
                # data['read_segments'].insert(0, 'hostname', host)
                dxt_df = pd.concat([dxt_df, data['read_segments']], ignore_index=True)

    get_runargs_data(Path(log_file).parents[0], dxt_df, job="Derivation")
    return dxt_df


# DXT data is special and requires a different loading function since it's not stored in the same way as the other modules. 
# We also want to be able to toggle whether or not we load it since it can be quite large and we may not always need it.
def load_darshan_data(log_file: str, worker: str, modules: list, analysis_func: Callable=None) -> dd.DataFrame:
    # we just need to load the darshan logs, no need for gathering release data
    # load the release data
    df = dd.from_pandas(pd.DataFrame())

    report = dardarbinks.DarshanReport(str(log_file), read_all=False)
    report.read_all_generic_records()
    # get files that were traced by darshan
    log = backend.log_open(str(log_file))
    # read all data for the given modules
    posix_df = pd.DataFrame()
    stdio_df = pd.DataFrame()

    for item in report.records:
        if item == "POSIX" and item in modules:
            files = report.records[item].to_df()['counters']['id'].to_list()
            rec = pd.DataFrame.from_dict(backend.log_lookup_name_records(log, files), orient='index')
            rec['id'] = rec.index.to_list()

            log_record = backend.log_get_record(log, item, 'pandas')
            counters_df = pd.DataFrame()
            fcounters_df = pd.DataFrame()

            # read each log record and save into dataframes
            while(log_record):
                counters_df = pd.concat([counters_df, log_record['counters']]) # get counters and fcounters
                fcounters_df = pd.concat([fcounters_df, log_record['fcounters']])
                log_record = backend.log_get_record(log, item, 'pandas')
            
            # join the frames with a union
            joined_counters_dfs = pd.merge(counters_df, fcounters_df, left_on="id", right_on="id", how="outer")
            file_data = pd.merge(rec, joined_counters_dfs, how="outer", left_on="id", right_on="id")
            file_data = file_data.drop('rank_x', axis=1)
            file_data = file_data.drop('rank_y', axis=1)
            file_data = file_data.rename(columns={0: "file_name"})
            file_data.insert(2, "process", worker)
            posix_df = pd.concat([posix_df, file_data])

        elif item == "STDIO" and item in modules:
            files = report.records[item].to_df()['counters']['id'].to_list()
            rec = pd.DataFrame.from_dict(backend.log_lookup_name_records(log, files), orient='index')
            rec['id'] = rec.index.to_list()

            log_record = backend.log_get_record(log, item, 'pandas')
            counters_df = pd.DataFrame()
            fcounters_df = pd.DataFrame()

            # read each log record and save into dataframes
            while(log_record):
                counters_df = pd.concat([counters_df, log_record['counters']]) # get counters and fcounters
                fcounters_df = pd.concat([fcounters_df, log_record['fcounters']])
                log_record = backend.log_get_record(log, item, 'pandas')
            
            # join the frames with a union
            joined_counters_dfs = pd.merge(counters_df, fcounters_df, left_on="id", right_on="id", how="outer")
            file_data = pd.merge(rec, joined_counters_dfs, how="outer", left_on="id", right_on="id")
            file_data = file_data.drop('rank_x', axis=1)
            file_data = file_data.drop('rank_y', axis=1)
            file_data = file_data.rename(columns={0: "file_name"})
            file_data.insert(2, "process", worker)
            stdio_df = pd.concat([stdio_df, file_data])

    # df = dd.concat([posix_df, stdio_df, dxt_df])
    df = pd.concat([posix_df, stdio_df])
    time = (report.end_time - report.start_time).total_seconds()
    df["time (s)"] = time

    # get data from runargs file
    get_runargs_data(Path(log_file).parents[0], df, job="Derivation")

    # if we have some analysis function to apply on the data...
    if analysis_func:
        ...

    return df


def load_dataframe_dxt(workdir: str, experiment_type: str, experiment_name: str, limit_cpu: bool, dxt_operations: list=[], analysis_func: Callable=None) -> dd.DataFrame:
    print("Parameters:")
    print("workdir: ", workdir)
    print("experiment_type: ", experiment_type)
    print("experiment_name: ", experiment_name)
    print("limit_cpu: ", limit_cpu)

    data_paths = \
        sorted(glob(str(Path(workdir, experiment_type, experiment_name, "*", "*", str(limit_cpu).lower(), "*", "*.darshan"))))

    df = dd.from_pandas(pd.DataFrame(columns=["id", "operation", "offset", "length", "start_time", "end_time"]))
    data_frames = []
    max_concat = 50
    concat_amt = 0

    for log in data_paths:
        # print(log)
        # we absolutely need the workers so this can't fail
        # also this is slow since we're reloading the json with every log
        # generate the worker mapping if it doesn't exist
        if not Path(log).parents[0].joinpath("worker_mapping.json").exists():
            generate_worker_mapping_via_logdir(Path(log).parents[0])

        worker_log_mapping = json.load(open(Path(log).parents[0].joinpath("worker_mapping.json")))
        id_to_worker = {data["id"]: worker for worker, data in worker_log_mapping.items()}
        job_id = re.findall(r"id[\d]+-[\d]+", Path(log).name)[0] # guaranteed to find in log file name
        pid = job_id.split("-")[1]
        worker = id_to_worker.get(pid, "main") # if it's not in the mapping it's the main process

        frame = load_darshan_data_dxt(log, dxt_operations)
        # df = dd.concat([df, frame.dataframe]) # keep only desired columns
        data_frames.append(frame)

        concat_amt += 1
        if concat_amt >= max_concat:
            print("Concatenating data frames...")
            df = dd.concat([df] + [f for f in data_frames], ignore_index=True)
            data_frames = []
            concat_amt = 0

    # if 'file_name' in df.columns:
    #     df["basename"] = df["file_name"].str.split("/").str[-1]

    print("Logs loaded")
    return df


# load_dxts lets us toggle whether or not we want to load dxt module data.
def load_dataframe(workdir: str, experiment_type: str, experiment_name: str, limit_cpu: bool, modules: list = ["POSIX", "STDIO"], analysis_func: Callable=None) -> dd.DataFrame: 
    print("Parameters:")
    print("workdir: ", workdir)
    print("experiment_type: ", experiment_type)
    print("experiment_name: ", experiment_name)
    print("limit_cpu: ", limit_cpu)
    print("modules: ", modules)

    data_paths = \
        sorted(glob(str(Path(workdir, experiment_type, experiment_name, "*", "*", str(limit_cpu).lower(), "*", "*.darshan"))))

    df = dd.from_pandas(pd.DataFrame())
    sub_df = pd.DataFrame()
    last_configuration = None

    for log in data_paths:
        print(log)
        log_as_path = Path(log)
        configuration = set([log_as_path.parents[1].name, log_as_path.parents[2].name, log_as_path.parents[3].name])
        # we absolutely need the workers so this can't fail
        # also this is slow since we're reloading the json with every log
        # generate the worker mapping if it doesn't exist
        if not Path(log).parents[0].joinpath("worker_mapping.json").exists():
            print("Failed to find worker mapping, generating one instead...")
            generate_worker_mapping_via_logdir(Path(log).parents[0])

        worker_log_mapping = json.load(open(Path(log).parents[0].joinpath("worker_mapping.json")))
        id_to_worker = {data["id"]: worker for worker, data in worker_log_mapping.items()}
        job_id = re.findall(r"id[\d]+-[\d]+", Path(log).name)[0] # guaranteed to find in log file name
        pid = job_id.split("-")[1]
        worker = id_to_worker.get(pid, "main") # if it's not in the mapping it's the main process

        # df = dd.concat([df, log_df]) # keep only desired columns

        if last_configuration and configuration != last_configuration:
            print("Configuration change detected, concatenating data frames...")
            df = dd.concat([df, sub_df])
            df.compute() # build the dask dataframe
            sub_df = pd.DataFrame()

        # then continue dataframe computation
        log_df = load_darshan_data(log, worker, modules)
        sub_df = pd.concat([sub_df, log_df])

        last_configuration = configuration

    # concat final df
    df = dd.concat([df, sub_df])
    df.compute() # build the dask dataframe
    sub_df = pd.DataFrame()

    if 'file_name' in df.columns:
        df["basename"] = df["file_name"].str.split("/").str[-1]

    print("Logs loaded")

    df.compute()

    return df
