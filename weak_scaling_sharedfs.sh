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
    nevents_per_proc=${2}
    nevents=$((${nproc} * ${nevents_per_proc}))
    format=${3}
    inputAODfile=${4}
    sharedWriter=${5}
    parallelCompression=${6}
    use_rntuple=${7}
    darshan_config=${8}
    localdir=${9}

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
    echo Running with nevents=$nevents, formats=$format, use_sw=$sharedWriter, use_pc=$parallelCompression, use_rnt=$use_rntuple and config=$darshan_config

    # setup job
    job_suffix=$(date +%s)
    release_dir=SPOT/MCOverlay/none
    workdir=./
    drv_cmd=" --athenaopts=--preloadlib=$DARSHAN_BASE_DIR/lib/libdarshan.so "
    drv_cmd+=" --sharedWriter ${sharedWriter}"
    if ${sharedWriter}
    then
        drv_cmd+=" --parallelCompression ${parallelCompression}"
    fi
    echo "working in $workdir"

    # add pre-exec if using rntuple
    enable_rntuple="import os;print(\"PID:\",os.getpid());"
    if [[ "${use_rntuple}" = "true" ]]; then
        enable_rntuple="import os;print(\"PID:\",os.getpid());flags.Output.StorageTechnology.EventData={\"*\":\"ROOTRNTUPLE\"};"
    fi

    # save darshan config    
    echo Copy darshan config $darshan_config to $workdir
    cp -v $darshan_config $workdir
    echo [$SECONDS]copy darshan setup to $workdir

    # run the derivation job
    (touch $workdir/job_output.log && python3 $localdir/misc/athenamp_eventorders.py $nproc $nevents_per_proc && ATHENA_CORE_NUMBER=${nproc} Derivation_tf.py --inputAODFile=${inputAODfile} --maxEvents ${nevents} --athenaMPUseEventOrders True --multiprocess True  --athenaMPMergeTargetSize "DAOD_*:0" --formats ${format//_/ } --outputDAODFile pool.root.1 --CA "all:True" --preExec "${enable_rntuple}" --postExec "default:cfg.getService(\"AthMpEvtLoopMgr\").ExecAtPreFork=[\"AthCondSeq\"];" --multithreadedFileValidation False --imf False ${drv_cmd} 2>&1 |tee $workdir/job_output.log) 
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
        python $localdir/misc/generate_file_trace_csv.py --pid "${_pid}" --logdir "${workdir}" --workers "${workdir}/athenaMP-workers-Derivation-DerivationFramework"
    done
    echo "Done."
    echo $? > __exitcode;
}

__run_mc_overlay_rdo_rdotrig_rawtoall() {
    NEVENTS=${1}
    localdir=${2}
    nproc=${3}

    darshan_config=$(realpath $localdir/darshan_configs/mcoverlay_env.conf)
    nevents=$(( $NEVENTS * $nproc ));

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

    enable_rntuple="import os;print(\"PID:\",os.getpid());"
    # if [[ "${use_rntuple}" = "true" ]]; then
    #     enable_rntuple="import os;print(\"PID:\",os.getpid());flags.Output.StorageTechnology.EventData='ROOTRNTUPLE';"
    # fi
    
    workdir=./
    echo Copy darshan config $darshan_config to $workdir
    cp -v $darshan_config $workdir

    touch $workdir/job_output.log && export ATHENA_CORE_NUMBER=${nproc} && Reco_tf.py --maxEvents $nevents --inputHITSFile /lcrc/project/ATLAS-HEP-group/rwang/Argonne_computing/data/*/HITS.41273927._000001.pool.root.1 --inputRDO_BKGFile /lcrc/project/ATLAS-HEP-group/rwang/Argonne_computing/data/valid2.900149*/* --outputRDOFile RDO.pool.root --AMIConfig=r16807 --multithreaded=True --preExec "${enable_rntuple}"

    # move darshan logs to workdir
    ls -ltrh $logfolder
    mv $logfolder/*.darshan $workdir
    echo "Done."
    echo $? > __exitcode;
}

run_physlite_daod_darshan_shared_writer() {
    FORMAT=${1}
    NEVENTS=${2}
    NPROCS=${3}
    localdir=${4}

    __run_physlite_daod_darshan \
        $NPROCS $NEVENTS $FORMAT /cvmfs/atlas-nightlies.cern.ch/repo/data/data-art/DerivationFrameworkART/mc20_13TeV.410470.PhPy8EG_A14_ttbar_hdamp258p75_nonallhad.recon.AOD.e6337_s3681_r13167/AOD.27162646._000001.pool.root.1 \
        true false false $(realpath $localdir/darshan_configs/event_IO_env.conf) $localdir

    echo $? > __exitcode;
}

run_physlite_daod_darshan_parallel_compression() {
    FORMAT=${1}
    NEVENTS=${2}
    NPROCS=${3}
    localdir=${4}

    __run_physlite_daod_darshan \
        $NPROCS $NEVENTS $FORMAT /cvmfs/atlas-nightlies.cern.ch/repo/data/data-art/DerivationFrameworkART/mc20_13TeV.410470.PhPy8EG_A14_ttbar_hdamp258p75_nonallhad.recon.AOD.e6337_s3681_r13167/AOD.27162646._000001.pool.root.1 \
        true true false $(realpath $localdir/darshan_configs/event_IO_env.conf) $localdir

    echo $? > __exitcode;
}

# Define and execute the test
execute() {
    # Define test parameters
    JOBNAME="${1}";
    JOBRELEASE="${2}";
    JOBPLATFORM="${3}";

    echo "${JOBNAME} - ${JOBRELEASE} - ${JOBPLATFORM}"

    # Define the top-level workdir
    # WORKDIR="/data/atlaspmb/athenamt-perfmonmt-jobs";
    WORKDIR="/data/atlaspmb/athenamp-derivation-darshan";
    # WORKDIR="/lcrc/group/ATLAS/users/ac.wkwiecinski/spot"
    # WORKDIR=$HOME/athena-derivation-darshan # use a local dir for now

    # todo:: I am assuming this script is ran from its own directory which contains supplemental scripts + configs
    #        for using darshan
    LOCALDIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
    echo localdir=$LOCALDIR

    # Create the rundir
    RUNDIR="${WORKDIR}/${JOBNAME}/${JOBRELEASE}/${JOBPLATFORM}";
    echo rundir=$RUNDIR
    if [[ ! -d ${RUNDIR} ]]; then
        mkdir -p ${RUNDIR};
    fi

    # Go to the main rundir
    echo "Using ${RUNDIR} as the rundir...";
    cd "${RUNDIR}";

    setupATLAS
    # Setup the latest Athena - job runs once per day at a fixed time
    echo lsetup="asetup Athena,${JOBRELEASE},${JOBPLATFORM//-/,},latest";
    lsetup "asetup Athena,${JOBRELEASE},${JOBPLATFORM//-/,},latest";

    # Check the currently nightly tag
    nightly=`echo "${Athena_DIR##*/${JOBRELEASE}_Athena_${JOBPLATFORM}/}"`;
    echo nightly=$nightly
    nightly=`echo "${nightly%%/Athena/*}"`;

    # Check if it exists already
    if [[ -d "${nightly}" ]]; then
        echo "Directory for ${nightly} already exists, nothing to do."
        return 0;
    fi

    # Now setup the run directory
    mkdir -p "${nightly}"; cd "${nightly}";

    # Let's start
    touch __start;

    # Now run the job :
    # 1) Run Derivation w/ Physlite using ttree + shared_writer
    # 2) Run Derivation w/ Physlite using ttree + shared_writer + parallel compression
    # 3) Run Derivation w/ Physlite using rntuple + shared writer
    # 4) Run Derivation w/ Physlite using rntuple + parallel compression
    if [[ "${JOBNAME}" == "physlite_daod_darshan_shared_writer" ]]; then # shared writer PHYSLITE IO w/ Darshan w/ 16 processes + 1000 events/proc
        run_physlite_daod_darshan_shared_writer "PHYSLITE" 1000 16 $LOCALDIR;
    elif [[ "${JOBNAME}" == "physlite_daod_darshan_parallel_compression" ]]; then # pc PHYSLITE IO w/ Darshan w/ 16 processes + 1000 events/proc
        run_physlite_daod_darshan_parallel_compression "PHYSLITE" 1000 16 $LOCALDIR;
    elif [[ "${JOBNAME}" == "physlite_daod_darshan_rntuple" ]]; then # rntuple PHYSLITE IO w/ Darshan w/ 16 processes + 1000 events/proc
        run_physlite_daod_darshan_rntuple "PHYSLITE" 1000 16 $LOCALDIR;
    elif [[ "${JOBNAME}" == "physlite_daod_darshan_parallel_compression_rntuple" ]]; then
        run_physlite_daod_darshan_parallel_compression_rntuple "PHYSLITE" 1000 16 $LOCALDIR
    else
        echo "Unknown job ${JOBNAME}, quitting..."
        return 0
    fi

    # check the pool content
    for f in *.pool.root*; do
        checkxAOD.py $f > myDAOD.pool.root.checkfile.txt 2>/dev/null
    done

    # Cleanup the POOL files to save disk-space
    # use {,.1} to cleanup extra DAOD file
    rm -f *.pool.root{,.1};
    # Let's extract the transform command to be used on the webpage
    echo "#!/bin/bash" > __command.txt;
    if [[ -f "env.txt" ]]; then
        echo "export $( grep "ATHENA_CORE_NUMBER" env.txt )" >> __command.txt;
    fi
python3 << END
import json
with open("__command.txt","a") as outfile, open("jobReport.json") as infile:
    data = json.load(infile) # Load the job report
    cmd = data['cmdLine'].split("' '") # Extract the transform command
    tf  = cmd[0].split('/')[-1] # This is the main transform, strip away full path
    cmd = [ f"{val} " if "--" in val else f"'{val}' " for val in cmd[1:] ]
    cmd = [ val.replace("/data/atlaspmb/","/eos/atlas/atlascerngroupdisk/proj-spot/") for val in cmd ]
    cmd = [ val.replace("--","\\\\\n  --") for val in cmd ]
    cmd = [ val.replace("''","'") for val in cmd ]
    outfile.write(f"{tf} {''.join(cmd)}")
END

    # Let's archive the results on EOS
    nightlydate=$( echo "${nightly}" | cut -c1-10 );
    tokens=( $( echo "${nightlydate}" | tr "-" " " ) );
    YEAR="${tokens[0]}";
    MONTH="${tokens[1]}";
    DAY="${tokens[2]}";
    TARGET_DIR="${ARCHIVE_DIR}/${DAY}/${MONTH}/${YEAR}/${JOBRELEASE}/${JOBPLATFORM}/spot-mon-${JOBNAME}";
    echo "Copying results into ${TARGET_DIR}";
    mkdir -p ${TARGET_DIR};

    # check if target archive dir is empty before doing any syncing
    if [ -d "$TARGET_DIR" ] && [ -z "$( ls -A $TARGET_DIR )" ]; then
        # need runargs, worker mapping for plot generation, and save darshan configuration
        rsync -avuz runargs* worker_mapping.json *.conf ${TARGET_DIR}/.;

        # archive darshan logs for DXT data rto pull from when plotting
        tar -zcvf ./logs.darshan.tar.gz *.darshan
        rsync ./logs.darshan.tar.gz ${TARGET_DIR}/.;
        #rm ./logs.darshan.tar.gz

        # Copy the command to the webpage area
        TARGET_DIR="${WEB_DIR}/spot-mon-${JOBNAME}/pages/commands";
        echo "Copying commands into ${TARGET_DIR}";
        mkdir -p ${TARGET_DIR};
        rsync -avuz __command.txt ${TARGET_DIR}/${DAY}-${MONTH}-${YEAR}-${JOBRELEASE}-${JOBPLATFORM}-${JOBNAME}

        # Copy the logs to the webpage area
        TARGET_DIR="${WEB_DIR}/spot-mon-${JOBNAME}/pages/logs";
        echo "Copying logs into ${TARGET_DIR}";
        mkdir -p ${TARGET_DIR};
        for file in $( ls log.* )
        do
            tokens=( $( echo "${file}" | tr "." " "  ) );
            JOBSTEP="${tokens[1]}"
            rsync -avuz ${file} ${TARGET_DIR}/${DAY}-${MONTH}-${YEAR}-${JOBRELEASE}-${JOBPLATFORM}-${JOBNAME}-${JOBSTEP}
        done
    else
        echo "Archive directory already contains completed run."
    fi

    # All done
    touch __done;

    # Go back to rundir
    cd "${RUNDIR}";
    cd $LOCALDIR # return to the dir that launched the script
}


main() {
    # Setup environment
    source ~/.bashrc;
    source ~/.bash_profile;

    # define the list of experiments to run

    # general w/ strong and weak scaling
    # learning and post-learning phase experiments
    # shared fs impact experiments


    # Define the jobs this setup will attempt to run
    if [[ -z "${2}" ]]; then
        # For the time being make sure only a single instance of this script is running
        # This prevents jobs running on top of each other by serializing the executions
        # In the future we can changes this logic...
        pidof -o %PPID -x $0 >/dev/null && echo "WARNING: Script ${0} already running, nothing to do..." && exit 0
    # These are the standard jobs
    elif [[ "${2}" == "el9_derivation_darshan" ]]; then
        JOBS=( "main x86_64-el9-gcc14-opt physlite_daod_darshan_shared_writer" \
               "main x86_64-el9-gcc14-opt physlite_daod_darshan_parallel_compression" \
               "main x86_64-el9-gcc14-opt physlite_daod_darshan_rntuple" \
               "main x86_64-el9-gcc14-opt physlite_daod_darshan_parallel_compression_rntuple" )
    elif [[ "${2}" == "el9_overlay_darshan" ]]; then
        JOBS=("main x86_64-el9-gcc14-opt run_mc_overlay_rdo_rdotrig_rawtoall_16t")
    else
        JOBS=()
    fi
}

# Execute the main function
main "${1}" "${2}"
