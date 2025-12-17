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
                    # setupATLAS -c -el9 --swtype="$container" -m /lcrc/ -r ". ./$experiment $i $nproc $workdir" > $logfile 2>&1

                    case "$container" in
                        "none")
                            # um how do we do container-less
                            setupATLAS
                            . ./$experiment $i $nproc $workdir
                            ;;
                        "apptainer")
                            # apptainer comes with cvmfs
                            setupATLAS -c -el9 --swtype="$container" -m /lcrc/ -r ". ./$experiment $i $nproc $workdir" > $logfile 2>&1;;
                        "shifter")
                            # we have to do some custom work to use shifter
                            ;;
                        "podman")
                            # we have to do some customer work to use podman
                            ;;
                        *)
                            echo "Unknown container";;
                    esac

                done
            done
        done
    done

    unset_run_params
}

main