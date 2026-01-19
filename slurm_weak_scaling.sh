#!/bin/bash
#SBATCH --nodes=1
#SBATCH -C cpu
#SBATCH --time=02:00:00
#SBATCH --account=m2845
#SBATCH --qos=shared
#SBATCH --ntasks-per-node=32
#SBATCH -c 4
#SBATCH --constraint=cpu

export SLURM_CPU_BIND="cores"

# apptainer comes with cvmfs
./run_weak_scaling.sh