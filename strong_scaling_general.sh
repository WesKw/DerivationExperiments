#!/bin/bash

# Archive dir
ARCHIVE_DIR="${HOME}/eos_atlaspmb/archive/custom"

# Web dir
# The actual EOS path doesn't work w/ mkdir -p
# Therefore, I'm using a soft-link from ${HOME} instead.
# See JIRA EOS-4364
WEB_DIR="${HOME}/www_atlaspmb"

__run_physlite_daod_darshan() {
    # gather job arguments
    nproc=${1}
    nevents=${2}
    format=${3}
    inputAODfile=${4}
    darshan_config=${5}

    # setup atlas release
    asetup Athena,25.0.47

    # load darshan with params
    lsetup darshan

    export DARSHAN_BASE_DIR=$DARSHAN_INSTALLEDDIR
    export DARSHAN_LOGPATH=$(pwd)
    export DARSHAN_LOGDIR=$(pwd)
    export DARSHAN_CONFIG_PATH=${darshan_config}
    export DARSHAN_DUMP_CONFIG=0

    echo 'using Darshan lib ' $DARSHAN_BASE_DIR
    echo 'using Darshan config' $DARSHAN_CONFIG_PATH
    echo 'store Darshan log in' $DARSHAN_LOGDIR

    mkdir -p $DARSHAN_LOGDIR/$(date +%Y)/$(date +%-m)/$(date +%-d)
    subfolder=$(date +'%Y/%m/%d')
    logfolder=$DARSHAN_LOGDIR/${subfolder//"/0"/"/"}
    echo Running with nevents=$nevents, formats=$format

    # setup job
    job_suffix=$(date +%s)
    release_dir=SPOT/MCOverlay/none
    workdir=./
    drv_cmd=" --athenaopts=--preloadlib=$DARSHAN_BASE_DIR/lib/libdarshan.so "
    drv_cmd+=" --sharedWriter true --parallelCompression true"
    echo "working in $workdir"

    # print pid in pre-exec
    print_pid="import os;print(\"PID:\",os.getpid());"

    # save darshan config    
    echo Copy darshan config $darshan_config to $workdir
    cp -v $darshan_config $workdir
    echo [$SECONDS]copy darshan setup to $workdir

    # run the derivation job
    # python3 $localdir/misc/athenamp_eventorders.py $nproc $nevents_per_proc && 
    # ATHENA_CORE_NUMBER=${nproc} Derivation_tf.py --inputAODFile=${inputAODfile} --maxEvents ${nevents} --athenaMPUseEventOrders True --multiprocess True  --athenaMPMergeTargetSize "DAOD_*:0" --formats ${format//_/ } --outputDAODFile pool.root.1 --CA "all:True" --preExec "${print_pid}" --postExec "default:cfg.getService(\"AthMpEvtLoopMgr\").ExecAtPreFork=[\"AthCondSeq\"];" --multithreadedFileValidation False --imf False ${drv_cmd} 2>&1 |tee $workdir/job_output.log
    ATHENA_CORE_NUMBER=${nproc} Derivation_tf.py --inputAODFile=${inputAODfile} --maxEvents ${nevents} --multiprocess True  --athenaMPMergeTargetSize "DAOD_*:0" --formats ${format//_/ } --outputDAODFile pool.root.1 --CA "all:True" --preExec "${print_pid}" --postExec "default:cfg.getService(\"AthMpEvtLoopMgr\").ExecAtPreFork=[\"AthCondSeq\"];" --multithreadedFileValidation False --imf False ${drv_cmd} 2>&1 |tee $workdir/job_output.log
    if ! ${sharedWriter}
    then
        echo "Not sharedWriter"
        for f in ${format//_/ }
        do
            (DAODMerge_tf.py --inputDAOD_${f}File DAOD_${f}.pool.root.* --outputDAOD_${f}_MRGFile DAOD_${f}.pool.root  --imf False --perfmon none --athenaopts=' --preloadlib=$DARSHAN_BASE_DIR/lib/libdarshan.so' 2>&1 |tee -a $workdir/job_output.log)
        done
    fi
    echo "Derivation ${job_suffix} complete"

    # save worker mapping to darshan logs
    ls -ltrh $logfolder
    for lfile in $(find $workdir -type f -name 'log.*')
    do
        echo "logfile=${lfile}"
        l=$(grep -e 'PID: ' $lfile)
        _pid=$(python3 -c "print('$l'.split(' ')[-1])")
        echo job_pid=$_pid
        echo Searching for ${logfolder}/*_python_id${_pid}-*.darshan $workdir
        mv -f $logfolder/*_python_id${_pid}-*.darshan $workdir
        export PYTHONPATH=$HOME/.local/lib/python3.11/site-packages:$PYTHONPATH
        python ~/PerlmutterExperimentSetup/generate_file_trace_csv.py --pid "${_pid}" --logdir "${workdir}" --workers "${workdir}/athenaMP-workers-Derivation-DerivationFramework"
    done
    echo "Done."
    # echo $? > __exitcode;
}

run_physlite_daod_darshan_parallel_compression() {
    FORMAT=${1}
    NEVENTS=${2}
    NPROCS=${3}
    CONFIG=${4}

    __run_physlite_daod_darshan \
        $NPROCS $NEVENTS $FORMAT /cvmfs/atlas-nightlies.cern.ch/repo/data/data-art/DerivationFrameworkART/mc20_13TeV.410470.PhPy8EG_A14_ttbar_hdamp258p75_nonallhad.recon.AOD.e6337_s3681_r13167/AOD.27162646._000001.pool.root.1 \
        $(realpath $CONFIG)

    echo $? > __exitcode;
}

run_general_strong() {
    echo "Starting run $1 with processes=$2 and container=$3 with config $4"

    # get parameters
    RUN=$1
    NPROC=$2
    CONTAINER=$3
    CONFIG=$4
    WORKDIR=$5

    cd $WORKDIR;

    run_physlite_daod_darshan_parallel_compression "PHYSLITE" 2000 $NPROC $CONFIG
}


# main() {
#     # Setup environment
#     # source ~/.bashrc;
#     # source ~/.bash_profile;
#     # source ./experiment_params.sh; set_run_params

#     # for i in "${run[@]}"; do
#     #     for nproc in "${processes[@]}"; do
#     #         for container in "${container_software[@]}"; do
#     #             # TODO:: REPLACE THIS WHEN WE RUN ON PERLMUTTER
#     #             workdir="./experiments/strong_scaling/run_$i/nproc_$nproc/container_$container/"
#     #             run_general_strong $i $nproc $container $workdir
#     #         done
#     #     done
#     # done

#     # unset_run_params
# }

# Execute the main function
run_general_strong $1 $2 $3 $4 $5
