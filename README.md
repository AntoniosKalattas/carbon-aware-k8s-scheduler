# Carbon aware Kubernetes scheduler

CS452 / EPL452 Datacenter Computing project by Antonios Kalattas and Alexandros
Georgiou. The project evaluates how energy and carbon objectives change the
placement of independent CPU batch jobs and their estimated environmental cost.

The prototype uses Kubernetes v1.37.0 in kind and a Go Scheduling Framework
plugin named `GreenScore`. Three policies run the same benchmark:

| Scheduler | Placement objective |
|---|---|
| `default-scheduler` | Standard Kubernetes scheduling |
| `energy-scheduler` | Lowest modeled job energy among feasible workers |
| `green-scheduler` | Lowest modeled job energy multiplied by carbon intensity |

Default resource feasibility filters remain enabled. The two custom profiles
use GreenScore as their sole Score plugin. Region labels represent Cyprus,
Greece, and Italy on containers sharing one laptop's physical resources.

## Start here

- [Cluster setup, benchmark commands, and measured results](green-scheduler/README.md)
- [Build and start the Go scheduler](green-scheduler/green-plugin/README.md)
- [Replay carbon intensity CSV snapshots](green-scheduler/carbon/README.md)
- [Raw experiment evidence](green-scheduler/results/)

From the repository root, check the Python components with:

```bash
python3 -m unittest discover -s green-scheduler/tests -v
```

## Verified experiments

The fixed-work workload counts primes through 300,000 by trial division and
repeats that calculation 30 times. Its checksum is `779910`. Jobs request
128 MiB of memory and use either one CPU for the latency comparison or three
CPUs for the reservation-capacity comparison. The process remains single-threaded.

On November 10, 2026, latency experiments compared all three policies with input
data assigned to Italy or Cyprus. Three batches of six Jobs per condition
completed successfully, totaling 108 Jobs. The simulated data stage modeled 20
serial requests with 5 ms local RTT or 50 ms remote RTT. Observed added waits
matched the prescribed 0.10 s local and 1.00 s remote delays.

On November 11, 2026, eight batches compared one versus two eligible workers per
region within the same six-worker kind cluster. All 48 Jobs succeeded.

| Eligible workers per region | Placement per six-job batch | Mean added wait | Mean CPU workload elapsed time | Mean observed batch time |
|---|---|---:|---:|---:|
| 1 | 3 Italy, 3 Greece | 0.550 s | 10.403 s | 15.189 s |
| 2 | 3 on each Italian worker | 0.100 s | 10.420 s | 14.674 s |

The three-CPU requests made at most three benchmark Pods fit concurrently on
one ten-CPU worker. Adding a second eligible Italian worker allowed all six
Jobs to remain near their simulated input. The mean observed batch reduction
was 0.515 s (3.39%), with overlapping ranges and roughly one-second polling
resolution. See the detailed README for methods and session identifiers.

## Carbon replay and interpretation

The scheduler supports repeatable CSV snapshots selected at an explicit trace
timestamp. A new snapshot is selected at scheduler startup for each replay
condition. The included demonstration trace is labeled `synthetic-demo` and
changes the preferred carbon region across three timestamps. Recorded datasets
can use the same schema with their actual source recorded in each row.

Modeled power, carbon values, and the fixed 10.5 s predicted runtime are explicit
experimental assumptions. Measured outputs cover placement, workload timings,
completion, and restarts. The delay stage uses `sleep` to represent serial data
access latency. Estimated energy and emissions depend on the chosen model.

Further work includes a verified regional data source, measured or documented
power profiles, time-varying input collection, and direct scheduler overhead
instrumentation. Keep Kubernetes credentials in the ignored
`green-scheduler/green-plugin/.runtime/` directory.
