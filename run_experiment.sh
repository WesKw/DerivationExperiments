main() {
    # Setup environment
    # source ~/.bashrc;
    # source ~/.bash_profile; # for setupATLAS
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
                            . ./$exp $i $nproc $workdir $DARSHAN_CONFIG $centos8_ath_release
                            ;;
                        "apptainer")
                            # apptainer comes with cvmfs
                            source /cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/user/atlasLocalSetup.sh -c centos8s --swtype="$container" -r ". ./$exp $i $nproc $workdir $DARSHAN_CONFIG $centos8_ath_release" > $logfile 2>&1
                            ;;
                        "shifter")
                            # we have to do some custom work to use shifter
                            shifter --image=registry.cern.ch/atlasadc/atlas-grid-centos8s -m cvmfs --env-file=./shifter.env -- ./$exp $i $nproc $workdir $DARSHAN_CONFIG $centos8_ath_release
                            ;;
                        "podman")
                            # we have to do some custom work to use podman
                            podman-hpc 
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