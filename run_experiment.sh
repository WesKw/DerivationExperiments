main() {
    # Setup environment
    # source ~/.bashrc;
    source ~/.bash_profile; # for setupATLAS
    source ./experiment_params.sh; set_run_params
    # alias setupATLAS='source ${ATLAS_LOCAL_ROOT_BASE}/user/atlasLocalSetup.sh'

    for exp in "${experiments[@]}"; do
        for i in "${run[@]}"; do
            for nproc in "${processes[@]}"; do
                for container in "${container_software[@]}"; do
                    # TODO:: REPLACE THIS WHEN WE RUN ON PERLMUTTER
                    # run specified experiment with a given container
                    exp_short=${exp%.*}
                    workdir="./experiments/$exp_short/run$i/$nproc/$container/"
                    logfile=$workdir/exp.log
                    mkdir -p $workdir
                    setupATLAS -c -el9 --swtype="$container" -m /lcrc/ -r ". ./$experiment $i $nproc $workdir" > $logfile 2>&1
                done
            done
        done
    done

    unset_run_params
}

main