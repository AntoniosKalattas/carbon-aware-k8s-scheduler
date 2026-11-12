# Kubernetes benchmark and experiment results

This directory contains the CPU benchmark, experiment runner, kind cluster
configurations, Go scoring plugin, carbon trace replay inputs, and saved results.
The three scheduling policies are `default-scheduler`, `energy-scheduler`, and
`green-scheduler`. The [project overview](../README.md) describes their objectives.

## Workload

`workloads/cpu_benchmark.py` counts primes from 2 through `--limit` using trial
division, then repeats the calculation `--repeats` times. The measured workload
uses `--limit 300000 --repeats 30`, giving checksum `779910`. It performs fixed
CPU work in a single process and thread, using Python's standard library.

Each Job has one Pod, no retries (`backoffLimit: 0` and `restartPolicy: Never`),
a 128 MiB memory request/limit, and a CPU request/limit set by `--cpu` (default
one). A three-CPU reservation changes scheduling feasibility while this workload
continues to execute on one CPU at a time. Workers are selected through the
`benchmark=true` label. `--scheduler` chooses the policy.

With `--input-region`, the workload first sleeps to model 20 serial data access
requests. Each request has an assumed RTT of 5 ms within the input region or
50 ms across regions, producing 0.10 s or 1.00 s of total added wait. The worker
name comes from the Pod's downward API and is mapped to the recorded node region.
The CPU timer starts after the wait, and both durations are recorded separately.
These RTT assumptions represent sensitivity scenarios on simulated regions.

## Cluster setup

Prerequisites are running Docker, kind, kubectl, Python 3, and Go for the plugin.
Run commands in this directory unless another directory is specified.

### Three workers

```bash
kind create cluster --name green --config cluster/kind-config.yaml
kubectl --context kind-green wait --for=condition=Ready nodes --all --timeout=180s
kubectl config use-context kind-green
kubectl label node green-worker green-worker2 green-worker3 benchmark=true --overwrite
```

### Six workers

```bash
kind create cluster --name green-six --config cluster/kind-config-six.yaml
kubectl --context kind-green-six wait --for=condition=Ready nodes --all --timeout=180s
kubectl config use-context kind-green-six
kubectl get nodes -L region,benchmark
```

The six-worker configuration has two workers per region. Initially only workers
1, 2, and 3 have `benchmark=true`, one in each region. For two eligible workers
per region, label workers 4, 5, and 6 as eligible too:

```bash
kubectl label nodes green-six-worker4 green-six-worker5 green-six-worker6 benchmark=true --overwrite
```

To return to one eligible worker per region, set those three labels to `false`.
The runner checks exactly `3 * --workers-per-region` eligible workers. The
latency mode also checks the expected region counts. All kind workers share
host CPUs and memory. Record Docker resource allocation and the versions of
Docker, kind, and Kubernetes alongside the experiment.

### Preload Python

Pull directly into worker runtimes to avoid the Docker image-import error seen
with `kind load docker-image` on the development Mac. Choose the worker names
for the cluster being tested. For the six-worker cluster:

```bash
for node in green-six-worker{,2,3,4,5,6}; do
  docker exec "$node" crictl pull docker.io/library/python:3.12.8-slim || break
done
```

Continue after all pulls succeed. Existing experiments report image digest
`sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0`.
The tag is versioned. Retain the recorded digest and use the same actual image
for every policy in a comparison. The runner accepts `--image`.

## Run experiments

Build and launch the [Go scheduler](green-plugin/README.md) in a separate terminal
for custom policies. Leave it running during all policies in the comparison.
The runner requires the current kubectl context to match `--context`.

For a three-worker smoke test:

```bash
python3 scripts/run_baseline.py --context kind-green --runs 1 --jobs 3 --limit 10000 --repeats 1
```

The smoke checksum is `1229`. For the calibrated six-worker experiment:

```bash
python3 scripts/run_baseline.py --context kind-green-six \
  --scheduler green-scheduler --input-region italy --workers-per-region 2 \
  --runs 1 --jobs 6 --cpu 3 --limit 300000 --repeats 30 --timeout 60
```

Preload images, warm up each condition, alternate policy/configuration order,
and use identical workload arguments, image, logging, and CPU/memory settings.
The runner saves all failures and returns an error if a batch fails or times out.
The Job deadline defaults to 600 seconds. `--keep` retains namespaces for debugging.
[Carbon replay](carbon/README.md) adds an explicit trace timestamp and optional
`--carbon-snapshot` archival for reproducible time-varying input experiments.

## Results and measurements

Each `results/<session>/` contains:

- `settings.json` with runner arguments, and `nodes.json` with the eligible nodes.
- `jobs.csv` with Pod placement, status, timestamps, image IDs, and restarts.
- `batches.csv` with success counts, observed batch time, throughput, and timeout.
- `run-N/` with submitted manifests, Job/Pod/event JSON, and each Pod's log.
- `carbon-inputs.json` when `--carbon-snapshot` was supplied.

Latency-mode CSVs also include modeled/observed wait, CPU workload elapsed time,
and process CPU time. `observed_batch_seconds` includes submission, API, and
one-second polling overhead. Pod timestamps have coarse resolution. Use the
workload timers when examining CPU execution and added wait. Measure scheduler
execution overhead with dedicated scheduler instrumentation in a separate study.

### Latency comparison on November 10 2026

Three batches of six Jobs ran per policy/input condition, totaling 108 successful
Jobs. Policy order rotated across rounds. Each Job requested one CPU. The custom
energy policy placed all Jobs in Cyprus, and the carbon policy placed all in
Italy. The default policy placed two Jobs per region in each batch.

| Input region | Policy | Mean modeled wait per Job | Mean observed batch time |
|---|---|---:|---:|
| Italy | Default | 0.70 s | 17.187 s |
| Italy | Energy | 1.00 s | 16.857 s |
| Italy | Carbon | 0.10 s | 16.351 s |
| Cyprus | Default | 0.70 s | 16.941 s |
| Cyprus | Energy | 0.10 s | 16.463 s |
| Cyprus | Carbon | 1.00 s | 16.386 s |

Observed waits matched the modeled delays to rounding precision. The CPU work
also varied across conditions. The small number of batches and overlapping
timings limit performance conclusions. Mean added wait reflects locality,
while batch duration includes additional runtime and collection effects.

The measured sessions span `20261110T141507Z-91dc96` through
`20261110T142005Z-55560e`. Earlier sessions that day are pilot checks. The
`20261110T142307Z-1cf77e` session is the later three-CPU reservation pilot.

### Eligible worker comparison on November 11 2026

Both conditions used the same six-worker cluster, carbon scheduler, Italy input,
six Jobs per batch, and three-CPU requests/limits. One condition enabled one
worker per region and the other enabled both. Four paired rounds alternated
which condition ran first. All 48 Jobs succeeded with zero restarts and the
same reported image digest.

| Eligible workers per region | Placement per batch | Mean observed wait per Job | Mean CPU workload elapsed time | Mean workload elapsed time including wait | Mean observed batch time |
|---|---|---:|---:|---:|---:|
| 1 | 3 Italy, 3 Greece | 0.550 s | 10.403 s | 10.953 s | 15.189 s |
| 2 | 3 on each Italian worker | 0.100 s | 10.420 s | 10.521 s | 14.674 s |

The mean workload elapsed reduction was 0.433 s. The mean observed batch
reduction was 0.515 s (3.39%). Batch ranges overlap: 15.181-15.198 s for one
eligible worker per region and 14.130-15.220 s for two. This experiment shows
how resource reservations and region capacity affect feasible placement and
simulated data access delay on shared hardware.

| Round | One eligible worker per region | Two eligible workers per region |
|---|---|---|
| 1 | `20261111T133101Z-633ffe` | `20261111T133117Z-d986ae` |
| 2 | `20261111T133147Z-831424` | `20261111T133132Z-c3f4b4` |
| 3 | `20261111T133203Z-e90cab` | `20261111T133219Z-26b001` |
| 4 | `20261111T133251Z-526518` | `20261111T133235Z-7368e2` |

The preceding sessions at 13:29 are pilots and are excluded from these means.

## Local checks

From the repository root:

```bash
python3 -m unittest discover -s green-scheduler/tests -v
```

From `green-scheduler/green-plugin/`:

```bash
go test ./...
```

Python checks cover benchmark computation, runner export, and carbon replay.
Go checks cover scoring units, policy ordering, invalid inputs, and plugin
configuration. Further work includes verified regional inputs, documented or
measured power profiles, and direct scheduling overhead instrumentation.
