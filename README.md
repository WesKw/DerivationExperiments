# PerlmutterExperimentSetup

We want to run 8 experiments on Perlmutter to get a good idea of the I/O behavior and patterns
within ATLAS derivations on bare-metal, containers, and how each of them scale up to HPC scale.

For each of these experiments, it's good to set some expectations on what we expect to see from
them so that we can compare them to what we're actually seeing from the log data.

For bare-metal experiments, it's good to establish a baseline with which we can compare other the
efficiency of containers with. We should be running each bare-metal experiment at least 4 times
to get a good idea of what the I/O metric range should look like.



## Strong Scaling Experiments

- Derivations with Strong Scaling
    - Run derivations with an increasing number of processes, with static input size.
    - Switch between bare-metal, apptainer, shifter, and podman.
    - Here, we're collecting general metrics on a standard production derivation run to get an
    idea of the patterns on bare-metal and containers, and how they scale. 
    - What do the I/O activity and patterns look like?
        - Look at common I/O bottlenecks
        - Density of reads and writes
        - Size of reads and writes
        - Distribution of reads and writes among processes
    - What is the I/O throughput?
        - Operations per second?
        - Bytes written & read per second?
    - How do these metrics change as we increase the scaling?
    - Do derivations scale better with strong or weak scaling? How do they compare overall?

- Learning Process of Derivations with strong scaling
    - Track the learning process of derivations with strong scaling.
- Post-learning process of derivations with strong scaling
- Shared file system impact with strong scaling


## Weak Scaling Experiments

-
-
-
-
