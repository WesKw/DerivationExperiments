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
                    # exp_short=${exp%.*}
                    # workdir="./experiments/$exp_short/run$i/$nproc/$container/"
                    # mkdir -p $workdir

                    case "$container" in
                        "none")
                            # if we're not using a container we're on aiatlasbm nodes, so we need to use most efficient storage (EOS)
                            workdir="/tmp/wkwiecin/experiment/"
                            rm -rf $workdir # clear the workdir before doing anything
                            logfile=$workdir/exp.log
                            mkdir -p $workdir
                            storage_dir=$(create_storage_directory "weak_scaling" "general" $nproc $container "/eos/user/w/wkwiecin" $limit_to_one_core)
                            # um how do we do container-less
                            . ./$exp $i $nproc $workdir $DARSHAN_CONFIG $ath_release $limit_to_one_core > $logfile 2>&1
                            cp -r $workdir $storage_dir
                            ;;
                        "apptainer")
                            # if we're using a container we're on perlmutter then we use the scratch file system (update workdir)

                            # apptainer comes with cvmfs
                            source /cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase/user/atlasLocalSetup.sh -c centos7 -m /global/homes/w/wkwiecin/ -m /pscratch/sd/w/wkwiecin/ --swtype="$container" -r ". ./$exp $i $nproc $workdir $DARSHAN_CONFIG $ath_release $limit_to_one_core" > $logfile 2>&1
                            mkdir -p $storage_dir_perlmutter
                            cp -r $workdir $storage_dir_perlmutter
                            ;;
                        "shifter")
                            # we have to do some custom work to use shifter
                            shifter --image=registry.cern.ch/atlasadc/atlas-grid-centos7 -m cvmfs -m /global/homes/w/wkwiecin/ -m /pscratch/sd/w/wkwiecin/ --env-file=./shifter.env -- ./$exp $i $nproc $workdir $DARSHAN_CONFIG $ath_release $limit_to_one_core
                            mkdir -p $storage_dir_perlmutter
                            cp -r $workdir $storage_dir_perlmutter
                            ;;
                        "podman")
                            # we have to do some custom work to use podman
                            podman-hpc run --rm --mount type=bind,src=/global/homes/w/wkwiecin/,target=/global/homes/w/wkwiecin --mount type=bind,src=/cvmfs,target=/cvmfs --mount type=bind,src=/global/homes/w/wkwiecin/,target=/global/homes/w/wkwiecin --mount type=bind,src=/pscratch/sd/w/wkwiecin/,target=/pscratch/sd/w/wkwiecin --env-file "./shifter.env" -it registry.cern.ch/atlasadc/atlas-grid-centos7 cd /global/homes/w/wkwiecin/PerlmutterExperimentSetup && ./$exp $i $nproc $workdir $DARSHAN_CONFIG $ath_release $limit_to_one_core
                            mkdir -p $storage_dir_perlmutter
                            cp -r $workdir $storage_dir_perlmutter
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