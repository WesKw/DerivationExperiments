#!/bin/bash

set_run_params() {
    # run=(1 2 3)
    export run=(1)
    # processes=(1 2 4 8 16 32)
    # export processes=(1 2 4 8 16)
    export processes=(1)
    # export container_software=("none" "apptainer" "shifter" "podman")
    export container_software=("apptainer")
    # export experiments=("strong_scaling_general.sh" "phases_strong.sh" "shared_fs_impact_strong.sh" "phases_weak.sh" "phases_weak" "shared_fs_impact_weak.sh")

    export experiments=("strong_scaling_general.sh")
    export centos8_ath_release="24.0.14"


    # CONSTANT PARAMS
    export FORMAT="PHYSLITE"
    export DARSHAN_CONFIG=~/PerlmutterExperimentSetup/darshan_configs/perlmutter_env.conf
}

unset_run_params() {
    unset run
    unset processes
    unset container_software

    unset FORMAT
    unset DARSHAN_CONFIG
}

create_run_directory() {
    # echo "Experiment type: $1"
    # echo "Experiment: $2"
    # echo "Nprocs: $3"
    # echo "Container: $4"
    # build the specific run directory
    mkdir -p /pscratch/sd/w/wkwiecin/experiments/$1/$2/$3/$4
    cd /pscratch/sd/w/wkwiecin/experiments/$1/$2/$3/$4

    next=1
    mkdir 1 > /dev/null 2>&1
    if [[ $? -eq 1 ]]; then
        dirs=($(ls -v))
        next=$(( ${dirs[-1]} + 1 ))
        mkdir $next
    fi
    cd $next
    echo $(pwd)
}
