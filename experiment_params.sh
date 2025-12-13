#!/bin/bash

set_run_params() {
    # run=(1 2 3)
    export run=(1)
    # processes=(1 2 4 8 16 32)
    export processes=(8)
    export container_software=("none" "apptainer" "shifter" "podman")
    # export experiments=("strong_scaling_general.sh" "phases_strong.sh" "shared_fs_impact_strong.sh" "phases_weak.sh" "phases_weak" "shared_fs_impact_weak.sh")

    export experiments=("strong_scaling_general.sh")


    # CONSTANT PARAMS
    export FORMAT="PHYSLITE"
    export DARSHAN_CONFIG="./darshan_configs/perlmutter_env.conf"
}

unset_run_params() {
    unset run
    unset processes
    unset container_software

    unset FORMAT
    unset DARSHAN_CONFIG
}
