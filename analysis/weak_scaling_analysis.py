import darshan as dardarbinks
import seaborn as sb
import pandas as pd

from glob import glob
from pathlib import Path
from argparse import ArgumentParser


def load_darshan_data(workdir: str, experiment_type: str, experiment_name: str, limit: bool) -> pd.DataFrame:
    # setup the path
    data_paths = glob(str(Path(workdir, experiment_type, experiment_name, "*", "*", str(limit), "*")))
    print(data_paths)

    # we just need to load the darshan logs, no need for gathering release data
    # load the release data
    df = pd.DataFrame()

    return df


def plot_weak_scaling(df, x, y, z):
    ...


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("data", help="Root location of the data.")
    parser.add_argument("-e", "--experiment-type", "The experiment type to analyze", required=True, choices=["strong_scaling", "weak_scaling"])
    parser.add_argument("-n", "--name", help="Name of experiment.", required=True, choices=["general", "phases", "shared_fs_impact"])
    parser.add_argument("-l", "--limit-cpu", help="Limiting CPU usage to 1", required=True, action="store_true")
    parser.add_argument("-x", "--x-var", help="X variable to plot from darshan logs.", required=True)
    parser.add_argument("-y", "--y-var", help="Y variable to plot from darshan logs.", required=True)
    parser.add_argument("-z", "--categorical", help="Categorize by this var", required=True)

    args = parser.parse_args()

    darshan_data = load_darshan_data(args.data)

    plot_weak_scaling(darshan_data, args.x, args.y, args.z)

