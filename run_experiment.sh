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
                            module load spack
                            spack env activate atlas
                            . ./$exp $i $nproc $workdir $DARSHAN_CONFIG $centos8_ath_release
                            ;;
                        "apptainer")
                            # apptainer comes with cvmfs
                            source /cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/user/atlasLocalSetup.sh -c centos7 -m /global/homes/w/wkwiecin/ -m /pscratch/sd/w/wkwiecin/ --swtype="$container" -r ". ./$exp $i $nproc $workdir $DARSHAN_CONFIG $centos8_ath_release" > $logfile 2>&1
                            ;;
                        "shifter")
                            # we have to do some custom work to use shifter
                            shifter --image=registry.cern.ch/atlasadc/atlas-grid-centos7 -m cvmfs -m /global/homes/w/wkwiecin/ -m /pscratch/sd/w/wkwiecin/ --env-file=./shifter.env -- ./$exp $i $nproc $workdir $DARSHAN_CONFIG $centos8_ath_release
                            ;;
                        "podman")
                            # we have to do some custom work to use podman
                            podman-hpc run --rm --mount type=bind,src=/global/homes/w/wkwiecin/,target=/global/homes/w/wkwiecin --mount type=bind,src=/cvmfs,target=/cvmfs --mount type=bind,src=/global/homes/w/wkwiecin/,target=/global/homes/w/wkwiecin --mount type=bind,src=/pscratch/sd/w/wkwiecin/,target=/pscratch/sd/w/wkwiecin --env-file "./shifter.env" -it registry.cern.ch/atlasadc/atlas-grid-centos7 cd /global/homes/w/wkwiecin/PerlmutterExperimentSetup && ./$exp $i $nproc $workdir $DARSHAN_CONFIG $centos8_ath_release
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