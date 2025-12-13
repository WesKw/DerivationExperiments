main() {
    # Setup environment
    # source ~/.bashrc;
    # source ~/.bash_profile;
    source ./experiment_params.sh; set_run_params

    for exp in "${experiments[@]}"; do
        for i in "${run[@]}"; do
            for nproc in "${processes[@]}"; do
                for container in "${container_software[@]}"; do
                    # TODO:: REPLACE THIS WHEN WE RUN ON PERLMUTTER
                    # run specified experiment with a given container
                    exp_short=${exp%.*}
                    workdir="./experiments/$exp_short/run_$i/nproc_$nproc/container_$container/"
                    logfile=$workdir/exp.log
                    mkdir -p $workdir
                    setupATLAS -c -el9 --sw-type=$container -m /lcrc/ -r ". ./$experiment $i $nproc $workdir" > $logfile 2>&1
                done
            done
        done
    done

    unset_run_params
}

main