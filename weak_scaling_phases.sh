#!/bin/bash

__run_physlite_daod_darshan() {
    # gather job arguments
    nproc=${1}
    nevents=$((${nproc} * 1000)) # 1000 events per process for weak scaling.
    format=${2}
    inputAODfile=${3}
    darshan_config=${4}
    release=${5}
    auto_flush_size=${6}

    echo "NPROC:$nproc"
    echo "NEVENTS:$nevents"
    echo "FORMAT:$format"
    echo "INPUT:$inputAODfile"
    echo "CONFIG:$darshan_config"
    echo "RELEASE:$release"
    echo "AUTO_FLUSH:$auto_flush_size"

    export ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase
    export DARSHAN_LOG_PATH=$HOME/darshanlogs

    # run setupATLAS
    # setupATLAS
    source ${ATLAS_LOCAL_ROOT_BASE}/user/atlasLocalSetup.sh

    # setup atlas release
    asetup Athena,$release

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
    workingdir=./
    drv_cmd=" --athenaopts=--preloadlib=$DARSHAN_BASE_DIR/lib/libdarshan.so "
    drv_cmd+=" --sharedWriter true --parallelCompression true"    
    echo "working in $workingdir"

    # print pid in pre-exec
    print_pid="import os;print(\"PID:\",os.getpid());flags.Output.TreeAutoFlush={\"DAOD_PHYSLITE\":$auto_flush_size};"

    # save darshan config    
    echo Copy darshan config $darshan_config to $workingdir
    cp -v $darshan_config $workingdir
    echo [$SECONDS]copy darshan setup to $workingdir

    # add extra data if we have a large number of processes
    if (( nproc >= 64 )); then
        echo Using $nproc procs
        cp /eos/user/w/wkwiecin/data/AOD.27162646._000002.pool.root.1 /tmp/wkwiecin/
        inputAODfile="$inputAODfile,/tmp/wkwiecin/AOD.27162646._000002.pool.root.1"
    fi

    post_exec="default:cfg.getService(\"AthMpEvtLoopMgr\").ExecAtPreFork=[\"AthCondSeq\"];print(flags.Output.TreeAutoFlush);"

    # run the derivation job
    ATHENA_CORE_NUMBER=${nproc} Derivation_tf.py --inputAODFile=${inputAODfile} --maxEvents ${nevents} --multiprocess True  --athenaMPMergeTargetSize "DAOD_*:0" --formats ${format//_/ } --outputDAODFile pool.root.1 --CA "all:True" --preExec "${print_pid}" --postExec $post_exec --multithreadedFileValidation False --imf False ${drv_cmd} 2>&1 |tee $workingdir/job_output.log
    
    echo "Derivation ${job_suffix} complete"

    # save worker mapping to darshan logs
    ls -ltrh $logfolder
    for lfile in $(find $workingdir -type f -name 'log.*')
    do
        echo "logfile=${lfile}"
        l=$(grep -e 'PID: ' $lfile)
        _pid=$(python3 -c "print('$l'.split(' ')[-1])")
        echo job_pid=$_pid
        echo Searching for ${logfolder}/*_python_id${_pid}-*.darshan $workingdir
        mv -f $logfolder/*_python_id${_pid}-*.darshan $workingdir
        export PYTHONPATH=$HOME/.local/lib/python3.11/site-packages:$PYTHONPATH
        python ~/DerivationExperimentSetup/generate_file_trace_csv.py --pid "${_pid}" --logdir "${workingdir}" --workers "${workingdir}/athenaMP-workers-Derivation-DerivationFramework"
    done
    echo "Done."

    # remove DAOD output
    rm DAOD_PHYSLITE.pool.root.1
}

run_physlite_daod_darshan_parallel_compression() {
    FORMAT=${1}
    NPROCS=${2}
    CONFIG=${3}
    RELEASE=${4}
    AUTO_FLUSH_SIZE=${5}

    __run_physlite_daod_darshan \
        $NPROCS $FORMAT /cvmfs/atlas-nightlies.cern.ch/repo/data/data-art/DerivationFrameworkART/mc20_13TeV.410470.PhPy8EG_A14_ttbar_hdamp258p75_nonallhad.recon.AOD.e6337_s3681_r13167/AOD.27162646._000001.pool.root.1 $(realpath $CONFIG) $RELEASE $AUTO_FLUSH_SIZE

    echo $? > __exitcode;
}

run_phases_weak() {
    echo "Starting phases $1 with processes=$2 with config $4"
    echo "Working in $3"
    echo "Using Athena release $5"
    echo "Running with autoflush size=$6"

    # get parameters
    RUN=$1
    NPROC=$2
    WORKLOC=$3
    CONFIG=$4
    RELEASE=$5
    AUTO_FLUSH_SIZE=$6

    cd $WORKLOC;

    ls $WORKLOC;

    run_physlite_daod_darshan_parallel_compression "PHYSLITE" $NPROC $CONFIG $RELEASE $AUTO_FLUSH_SIZE
}

# Execute the main function
run_phases_weak $1 $2 $3 $4 $5 $6
