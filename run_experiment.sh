main() {
    # Setup environment
    # source ~/.bashrc;
    # source ~/.bash_profile; # for setupATLAS
    # source ./experiment_params.sh; set_run_params
    source ./experiment_params.sh
    # alias setupATLAS='source ${ATLAS_LOCAL_ROOT_BASE}/user/atlasLocalSetup.sh'
    starting_dir=$(pwd)
    ath_release="25.0.51"
    exp=$1
    nproc=$2
    container=$3
    storage_location=$4
    extra_option=$5 # changes depending on the experiment being ran
    # baseline -> limit to one cpu
    # phases -> autoflush size
    # sharedfs -> File system, more?
    start=$6
    end=$7
    file_system_to_use=$8
    # auto_flush_size=$8
    host=$(cat /etc/hostname)
    fs_to_use=""

    FORMAT="PHYSLITE"
    DARSHAN_CONFIG=~/DerivationExperimentSetup/darshan_configs/perlmutter_env.conf

    for i in $(seq $start $end); do
        cd $starting_dir;
        exp_short=${exp%.*}
        exp_name=$(echo $exp_short | cut -d "_" -f 1,2)
        exp_type=$(echo $exp_short | cut -d "_" -f 3);
        
        temp_work_directory=$file_system_to_use/$exp_name/$nproc/$container/$extra_option/$i/
        # temp_work_directory=/tmp/wkwiecin/$exp_name/$exp_type/$nproc/$container/$extra_option/$i/
        echo $temp_work_directory

        case "$container" in
            "none")
                # if we're not using a container we're on aiatlasbm nodes, so we need to use most efficient storage (EOS)
                workdir=$temp_work_directory
                rm -rf $workdir # clear the workdir before doing anything
                logfile=$workdir/exp.log
                mkdir -p $workdir
                # echo $workdir
                storage_dir=$(create_storage_directory $exp_name $exp_type $nproc $container $storage_location $extra_option $i)
                echo $storage_dir
                . ./$exp $i $nproc $workdir $DARSHAN_CONFIG $ath_release $extra_option > $logfile 2>&1
                # . ./$exp $i $nproc $workdir $DARSHAN_CONFIG $ath_release $limit_to_one_core
                # clear the storage directory just in case
                rm -rf $storage_dir/*
                cp -r $workdir/* $storage_dir
                ;;
            "apptainer")
                # if we're using a container we're on perlmutter then we use the scratch file system (update workdir)
                mkdir -p $storage_location/exps/$exp_name/$exp_type/$no_procs/$container_runtime/$limit_cores/$i
                # mkdir -p $storage_location/exps/$exp_name/$exp_type/$no_procs/$container_runtime/$limit_cores/$i
                # export TMPDIR=$workdir
                # apptainer comes with cvmfs, using apptainer through setupATLAS is usual way
                source /cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/user/atlasLocalSetup.sh -c el9 -m /global/homes/w/wkwiecin/ -m /pscratch/sd/w/wkwiecin/ -m /global/cfs/cdirs/m2845/derivation_exps/ --swtype="$container_runtime" -r ". /global/homes/w/wkwiecin/PerlmutterExperimentSetup/$experiment $i $no_procs $workdir $DARSHAN_CONFIG $ath_release $limit_cores > $logfile 2>&1"
                cp -r $workdir/* $storage_location/exps/$exp_name/$exp_type/$no_procs/$container_runtime/$limit_cores/$i
                ;;
            "shifter")
                # we have to do some custom work to use shifter since it does not properly work with setupATLAS on Perlmutter
                mkdir -p $storage_location/exps/$exp_name/$exp_type/$no_procs/$container_runtime/$limit_cores/$i
                shifter --image=registry.cern.ch/atlasadc/atlas-grid-almalinux9 --module=cvmfs --env-file=./shifter.env /global/homes/w/wkwiecin/PerlmutterExperimentSetup/run_wrapper.sh /global/homes/w/wkwiecin/PerlmutterExperimentSetup/$experiment $i $no_procs $workdir $DARSHAN_CONFIG $ath_release $limit_cores $logfile
                cp -r $workdir/* $storage_location/exps/$exp_name/$exp_type/$no_procs/$container_runtime/$limit_cores/$i
                ;;
            "podman")
                # we have to do some custom work to use podman since it does not work properly with setupATLAS on Perlmutter
                # storage_dir=$(create_storage_directory $exp_name $exp_type $no_procs $container_runtime $storage_location $limit_cores $i)
                mkdir -p $storage_location/exps/$exp_name/$exp_type/$no_procs/$container_runtime/$limit_cores/$i
                podman-hpc shared-run --rm --cvmfs --replace --mount type=tmpfs,tmpfs-size=0,target=/dev/shm --mount type=bind,src=/tmp/wkwiecin/,target=/tmp/wkwiecin/ --mount type=bind,src=/global/homes/w/wkwiecin/,target=/global/homes/w/wkwiecin --mount type=bind,src=/pscratch/sd/w/wkwiecin/,target=/pscratch/sd/w/wkwiecin --env-file /global/homes/w/wkwiecin/PerlmutterExperimentSetup/shifter.env -e ATLAS_LOCAL_ROOT_BASE=/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase -e DARSHAN_LOG_PATH=/global/homes/w/wkwiecin/darshanlogs registry.cern.ch/atlasadc/atlas-grid-almalinux9 /global/homes/w/wkwiecin/PerlmutterExperimentSetup/run_wrapper.sh /global/homes/w/wkwiecin/PerlmutterExperimentSetup/$experiment $i $no_procs $workdir $DARSHAN_CONFIG $ath_release $limit_cores $logfile
                cp -r $workdir/* $storage_location/exps/$exp_name/$exp_type/$no_procs/$container_runtime/$limit_cores/$i
                ;;
            *)
                echo "Unknown container"
                ;;
        esac
    done
}

main $1 $2 $3 $4 $5 $6 $7
