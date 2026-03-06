import darshan as dardarbinks
import darshan.backend.cffi_backend as backend
import pandas as pd
import re
import json

from pathlib import Path
from glob import glob


METADATA_COLUMNS=["file_name", "id", "process", "basename", "max_events", "nprocs", "container", "limit_cpu", "experiment_name", "experiment_type", "run"]


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

        df["max_events"] = max_events
        df["nprocs"] = nprocs
        df["nthreads"] = nthreads
        # print(list(directory.parents))
        df["container"] = directory.parents[1].name
        df["limit_cpu"] = directory.parents[0].name
        df["run"] = directory.name
        df["experiment_name"] = directory.parents[3].name
        df["experiment_type"] = directory.parents[4].name



def load_darshan_data(log_file: str, experiment_type: str, experiment_name: str, limit: bool, worker: str, modules: list) -> pd.DataFrame:
    # we just need to load the darshan logs, no need for gathering release data
    # load the release data
    df = pd.DataFrame()

    report = dardarbinks.DarshanReport(str(log_file), read_all=True)
    # get files that were traced by darshan
    log = backend.log_open(str(log_file))
    # read all data for the given modules
    posix_df = pd.DataFrame()
    stdio_df = pd.DataFrame()
    dxt_df = pd.DataFrame(
        columns=['id', 'hostname', 'write_offsets', 'write_lengths', 'write_starts', 'write_ends', 'read_offsets', 'read_lengths', 'read_starts', 'read_ends']
    )
    for item in report.records:
        # todo:: just pull data from darshan logs directly
        if item == "DXT_POSIX" and item in modules:
            dxt_data = report.records[item].to_dict() # list not a dict
            for data in dxt_data:
                file_id = data['id']
                host = data['hostname']
                
                # read and write data from DXT (todo:: this might not be the most efficient way to do this)
                write_offsets = []
                write_lengths = []
                write_starts = []
                write_ends = []
                for write in data['write_segments']:
                    write_offsets.append(write['offset'])
                    write_lengths.append(write['length'])
                    write_starts.append(write['start_time'])
                    write_ends.append(write['end_time'])

                read_offsets = []
                read_lengths = []
                read_starts = []
                read_ends = []
                for read in data['read_segments']:
                    read_offsets.append(read['offset'])
                    read_lengths.append(read['length'])
                    read_starts.append(read['start_time'])
                    read_ends.append(read['end_time'])

                dxt_df.loc[-1] = [file_id, host, write_offsets, write_lengths, write_starts, write_ends,
                                read_offsets, read_lengths, read_starts, read_ends]
                dxt_df.index = dxt_df.index + 1  # shift index
                dxt_df = dxt_df.sort_index()  # sort by index

                # print(dxt_df.explode(column=["read_offsets", "read_lengths", "read_starts", "read_ends"]))

        elif item == "POSIX" and item in modules:
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

    df = pd.concat([posix_df, stdio_df, dxt_df])

    # get data from runargs file
    get_runargs_data(Path(log_file).parents[0], df, job="Derivation")

    # full_df = pd.merge(posix_df, dxt_df, how="left", left_on="id", right_on="id")
    # full_df = pd.merge(full_df, stdio_df, how="left", left_on="id", right_on="id")
    # join the file trace and dxt data before appending to full table
    # if not posix_df.empty and not dxt_df.empty:
    #     # if the file id is not present in POSIX data we ignore it.
    #     posix_df = pd.merge(posix_df, dxt_df, how="left", left_on="id", right_on="id")

    return df


# load_dxts lets us toggle whether or not we want to load dxt module data.
def load_dataframe(workdir: str, experiment_type: str, experiment_name: str, limit_cpu: bool, modules: list = ["POSIX", "STDIO", "DXT_POSIX"]) -> pd.DataFrame: 
    print("Parameters:")
    print("workdir: ", workdir)
    print("experiment_type: ", experiment_type)
    print("experiment_name: ", experiment_name)
    print("limit_cpu: ", limit_cpu)
    print("modules: ", modules)

    data_paths = \
        sorted(glob(str(Path(workdir, experiment_type, experiment_name, "*", "*", str(limit_cpu).lower(), "*", "*.darshan"))))

    df = pd.DataFrame()

    for log in data_paths:
        # print(log)
        # we absolutely need the workers so this can't fail
        # also this is slow since we're reloading the json with every log
        worker_log_mapping = json.load(open(Path(log).parents[0].joinpath("worker_mapping.json")))
        id_to_worker = {data["id"]: worker for worker, data in worker_log_mapping.items()}
        job_id = re.findall(r"id[\d]+-[\d]+", Path(log).name)[0] # guaranteed to find in log file name
        pid = job_id.split("-")[1]
        worker = id_to_worker.get(pid, "main") # if it's not in the mapping it's the main process

        log_df = load_darshan_data(log, experiment_type, experiment_name, limit_cpu, worker, modules)
        df = pd.concat([df, log_df]) # keep only desired columns

    df["basename"] = df["file_name"].str.split("/").str[-1]
        # we need to load all data from one config, THEN aggregate to retain same functionality for previous loading
        # filter variables
        # op_regex = r"|".join(variables)
        # column_name_regex = DATA_COLUMNS_REGEX + op_regex
        # df = df.filter(regex=column_name_regex)
        
        # add config-specific options to config_df
        # with open(config_dir.joinpath("runargs.Derivation.py")) as file:
        #     data = ''.join(file.readlines())
        #     max_events = next(re.finditer(r"maxEvents = [\d]+", data)).group(0).replace(' ', '').split('=')[1]
        #     nprocs = next(re.finditer(r"nprocs = [\d]+", data)).group(0).replace(' ', '').split('=')[1]
        #     formats = next(re.finditer(r"runArgs.formats[ ]*=[ ]*.+", data)).group(0).replace(' ', '').split('=')[1][2:-2] # remove brackets (this probably won't work if multiple formats are specified)
        #     formats = next(re.finditer(r'runArgs.formats[]*=[]*.+', data)).group(0).replace(' ', '').split('=')[1][1:-1]
                
        #     config_df["max_events"] = max_events
        #     config_df["nprocs"] = nprocs
        #     config_df["formats"] = formats
        #     config_df["platform"] = config_dir.parents[0].name

        # set the release and base version of Athena based on the config
        #date = f"{config_dir.parents[2].name}-{config_dir.parents[3].name}-{config_dir.parents[4].name}"
        # match = re.search(r"\d{4}-\d{2}-\d{2}", str(config_dir))
        # if match:
        #    date = match.group(0)
        #    print(date)  # -> 2025-10-16
        # else:
        #    return 0
        # base = get_nightly_metadata(date)
        # config_df["release"] = f"{date}\n{base}"
        # config_df["base"] = base
        # config_df["config"] = config_mapping[config]

        # then we concat to the df containing every config
        # df = pd.concat([df, config_df])

    print("Logs loaded")

    return df

