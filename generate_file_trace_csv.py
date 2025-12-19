import re
import glob
import json

from argparse import ArgumentParser
from pathlib import Path


# Save the mapping between worker names and their respective logs so we don't need to save the directories.
def generate_worker_mapping(pid: str, log_dir: str, workers: str):
    worker_logs = glob.glob(f"{workers}/*/AthenaMP.log")
    worker_pid_regex=r"PID=[\d]+"
    if not worker_logs:
        print("Could not find worker logs")

    workers_and_logs = []
    # get root worker
    root_worker = "root"
    parent_pid = pid
    darshan_log_glob = rf"{Path(log_dir).resolve()}/*_python_id{pid}-{pid}_*"
    root_darshan_log = glob.glob(darshan_log_glob)[0]
    workers_and_logs.append((root_worker, root_darshan_log))
    worker_mapping = {}

    # get all other workers via logs
    for log in worker_logs:
        # get worker 
        worker = Path(log).parent.name
        worker_pid=""
        with open(Path(log).resolve()) as file:
            # first line always contains worker pid
            line = file.readline()
            regex_result = re.findall(worker_pid_regex, line)
            if not regex_result:
                print(f"Failed to find worker PID in {log}")
                exit(-1)
            worker_pid = regex_result[0].split('=')[1]
            
        # todo:: this should just take the name, not the entire path of the darshan log.
        #        since this doesn't really affect the generation of the plots in a meaningful
        #        way this is low priority. Mostly just a small waste of space.
        darshan_log_glob = rf"{Path(log_dir).resolve()}/*_python_id{pid}-{worker_pid}_*"
        worker_darshan_log = glob.glob(darshan_log_glob)[0]
        workers_and_logs.append((worker, worker_darshan_log, worker_pid))
        worker_mapping[worker] = {
            "parent_id": parent_pid,
            "id": worker_pid,
            "log": worker_darshan_log
        }
    with open('worker_mapping.json', 'w') as fp:
        json.dump(worker_mapping, fp)


if __name__ == "__main__":
    parser = ArgumentParser("Generate Darshan File Trace", usage="python generate_file_trace.py --pid pid --logdir dir --workers worker_dir", description="Generates a traces of files used by all logs with the process id of the root process defined by pid.")
    parser.add_argument("-p", "--pid", type=str)
    parser.add_argument("-l", "--logdir", type=str)
    parser.add_argument("-w", "--workers", type=str, help="Root directory containing worker directories")
    args = parser.parse_args()

    logdir = str(Path(args.logdir).resolve())
    workers = str(Path(args.workers).resolve())
    print("Generating trace with:")
    print(f"     pid: {args.pid}")
    print(f"     logdir: {logdir}")
    print(f"     workers: {workers}")
    generate_worker_mapping(args.pid, logdir, workers)
