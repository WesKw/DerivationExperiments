import darshan as dardarbinks
import seaborn as sb
import pandas as pd
import darshan.backend.cffi_backend as backend

dardarbinks.enable_experimental()

from argparse import ArgumentParser
from darshan_helpers import load_dataframe
from darshan_helpers import METADATA_COLUMNS

special_groupings = [
    "operation_types",
    "posix_v_stdio"
]


def plot_posix_v_stdio(df):
    """
    Plot the number of posix vs stdio operations.
    """
    # filter df columns to only include operation counts
    # POSIX_OPENS include POSIX_DUPS and POSIX_FILENO operations
    # STDIO_OPENS include STDIO_FDOPENS
    module_operations = [
        "POSIX_OPENS", "POSIX_READS", "POSIX_WRITES", "POSIX_SEEKS", "POSIX_STATS", 
        "POSIX_MMAPS", "POSIX_FSYNCS", "POSIX_FDSYNCS", "STDIO_OPENS", "STDIO_READS",
        "STDIO_WRITES", "STDIO_SEEKS", "STDIO_FLUSHES"
    ]
    reduced_df = df[METADATA_COLUMNS + module_operations]


def plot_operation_types(df):
    """
    Plot operation types according grouping by global, local, sublocal files
        X: nprocs
        Y: number of operations
        Z: global, local & data transfer, metadata
    """
    


def plot_weak_scaling(df, x, y, z):
    ...


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("data", help="Root location of the data.")
    parser.add_argument("-e", "--exp-type", help="The experiment type to analyze", required=True, choices=["strong_scaling", "weak_scaling"])
    parser.add_argument("-n", "--exp-name", help="Name of experiment.", required=True, choices=["general", "phases", "shared_fs_impact"])
    parser.add_argument("-l", "--limit-cpu", help="Limiting CPU usage to 1", action="store_true")
    parser.add_argument("-x", "--x-var", help="X variable to plot from darshan logs.")
    parser.add_argument("-y", "--y-var", help="Y variable to plot from darshan logs.")
    parser.add_argument("-z", "--categorical", help="Categorize by this var")
    parser.add_argument("-s", "--special-plot", help="Special comparisons to plot. Ignores any existing data", choices=special_groupings)

    args = parser.parse_args()

    darshan_data = load_dataframe(args.data, args.exp_type, args.exp_name, args.limit_cpu, modules=["POSIX", "STDIO"])

    plot_posix_v_stdio(darshan_data)
    # print(list(darshan_data.columns))

    # plot_weak_scaling(darshan_data, args.x, args.y, args.z)

