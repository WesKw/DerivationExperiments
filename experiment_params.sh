#!/bin/bash

set_run_params() {
    # run=(1 2 3)
    export run=(1 2 3 4 5)
    # processes=(1 2 4 8 16 32)
    # export processes=(1 2 4 8 16 32, 64, 128, 256)
    export processes=(32)
    export container_software=("none") # "apptainer" "shifter" "podman")
    export limit_to_one_core="true" # use this to limit to running derivations on 1 core
    # export container_software=("apptainer")
    # export experiments=("strong_scaling_general.sh" "phases_strong.sh" "shared_fs_impact_strong.sh" "phases_weak.sh" "phases_weak" "shared_fs_impact_weak.sh")

    export experiments=("strong_scaling_general.sh")
    export ath_release="25.0.51"


    # CONSTANT PARAMS
    export FORMAT="PHYSLITE"
    export DARSHAN_CONFIG=~/DerivationExperimentSetup/darshan_configs/perlmutter_env.conf
}

unset_run_params() {
    unset run
    unset processes
    unset container_software

    unset FORMAT
    unset DARSHAN_CONFIG
}

create_storage_directory() {
    # echo "Experiment type: $1"
    # echo "Experiment: $2"
    # echo "Nprocs: $3"
    # echo "Container: $4"
    # build the specific run directory
    # storage_root=$5
    # limiting_to_1_cpu=$6

    mkdir -p $5/exps/$1/$2/$3/$4/$6
    # cd $storage_root/experiments/$1/$2/$3/$4/$6

    next=1
    mkdir 1 > /dev/null 2>&1
    if [[ $? -eq 1 ]]; then
        dirs=($(ls $5/exps/$1/$2/$3/$4/$6 -v))
        next=$(( ${dirs[-1]} + 1 ))
        mkdir $next
    fi
    
    echo "$5/exps/$1/$2/$3/$4/$6/$next"
    # cd $next
    # echo $(pwd)
}
