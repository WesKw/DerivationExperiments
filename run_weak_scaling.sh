#!/bin/bash

source ./experiment_params.sh; set_run_params

echo Scratch location: $PSCRATCH;

# CONSTANT PARAMS
DARSHAN_CONFIG=/global/homes/w/wkwiecin/PerlmutterExperimentSetup/darshan_configs/perlmutter_env.conf
experiment_type=weak_scaling
experiment=general
nprocs=4
container=apptainer

# build the specific run directory
workdir=$(create_run_directory $experiment_type $experiment $nprocs $container)
logfile="$workdir/exp.log"
mkdir -p "$workdir"

case "$container" in
    "none")
        # um how do we do container-less
        module load spack
        spack env activate atlas
        . /global/homes/w/wkwiecin/PerlmutterExperimentSetup/weak_scaling_general.sh 1 $nprocs $workdir $DARSHAN_CONFIG $centos8_ath_release > "$logfile" 2>&1
        ;;
    "apptainer")
        # apptainer comes with cvmfs
        source /cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/user/atlasLocalSetup.sh -c centos7 -m /global/homes/w/wkwiecin/ -m /pscratch/sd/w/wkwiecin/ --swtype="$container" -r ". /global/homes/w/wkwiecin/PerlmutterExperimentSetup/weak_scaling_general.sh 1 $nprocs $workdir $DARSHAN_CONFIG $centos8_ath_release" > "$logfile" 2>&1
        ;;
    "shifter")
        # we have to do some custom work to use shifter
        shifter --image=registry.cern.ch/atlasadc/atlas-grid-centos7 -m cvmfs -m /global/homes/w/wkwiecin/ -m /pscratch/sd/w/wkwiecin/ --env-file=./shifter.env -- /global/homes/w/wkwiecin/PerlmutterExperimentSetup/weak_scaling_general.sh 1 $nprocs $workdir $DARSHAN_CONFIG $centos8_ath_release > "$logfile" 2>&1
        ;;
    "podman")
        # we have to do some custom work to use podman
        podman-hpc run --rm --mount type=bind,src=/global/homes/w/wkwiecin/,target=/global/homes/w/wkwiecin --mount type=bind,src=/cvmfs,target=/cvmfs --mount type=bind,src=/global/homes/w/wkwiecin/,target=/global/homes/w/wkwiecin --mount type=bind,src=/pscratch/sd/w/wkwiecin/,target=/pscratch/sd/w/wkwiecin --env-file "./shifter.env" -it registry.cern.ch/atlasadc/atlas-grid-centos7 cd /global/homes/w/wkwiecin/PerlmutterExperimentSetup && /global/homes/w/wkwiecin/PerlmutterExperimentSetup/weak_scaling_general.sh 1 $nprocs $workdir $DARSHAN_CONFIG $centos8_ath_release > "$logfile" 2>&1
        ;;
    *)
        echo "Unknown container";;
esac

# source /cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/user/atlasLocalSetup.sh -c centos7 -m /global/homes/w/wkwiecin/ -m /pscratch/sd/w/wkwiecin/ --swtype="$container" -r ". /global/homes/w/wkwiecin/PerlmutterExperimentSetup/weak_scaling_general.sh 1 32 $workdir $DARSHAN_CONFIG $centos8_ath_release" > $logfile 2>&1