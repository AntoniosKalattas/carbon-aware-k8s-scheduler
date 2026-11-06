# Green Kubernetes Scheduler — baseline milestone

This package adds a fixed-work CPU benchmark and repeated Kubernetes baseline
collection to the supplied cluster configuration. It does not implement a custom
scheduler or claim carbon savings. The cluster configuration is copied unchanged.

## 1. Start and verify the cluster (on your laptop)

Prerequisites: running Docker, kind, kubectl, and Python 3. Use a kind release
compatible with the pinned Kubernetes image. From this folder:

```bash
kind create cluster --name green --config cluster/kind-config.yaml
kubectl --context kind-green wait --for=condition=Ready nodes --all --timeout=180s
kubectl config use-context kind-green
kubectl get nodes -L region
kubectl label node green-worker green-worker2 green-worker3 benchmark=true --overwrite
```

The runner requires exactly three nodes with `benchmark=true`; it only submits
work to those nodes. If you already have a cluster, skip creation, label your
three workers, and pass its context to the runner instead. Do not label the
control-plane node. No cluster is deleted by the runner.

Record your environment with `docker version`, `kind version`, and
`kubectl version`. Record the Docker CPU/memory allocation and avoid unrelated
heavy workloads during experiments. Three kind workers share physical hardware;
their advertised allocatable resources are not three independent physical CPUs.

## 2. Preload the benchmark image

```bash
docker pull python:3.12.8-slim
kind load docker-image python:3.12.8-slim --name green
```

The tag is versioned but not immutable. The results record actual image IDs.
For final experiments, use the same image digest across every comparison and
pass that image reference through `--image` (preload the same reference).

## 3. Run a small smoke test

```bash
python3 scripts/run_baseline.py --context kind-green --runs 1 --jobs 3 --limit 10000 --repeats 1
```

Check that all three Jobs succeed and logs report checksum `1229`. The default
scheduler may place multiple Jobs on one node; one Job per node is not guaranteed.

## 4. Collect a baseline

First run one warm-up batch and exclude that folder from analysis:

```bash
python3 scripts/run_baseline.py --context kind-green --runs 1 --jobs 6
python3 scripts/run_baseline.py --context kind-green --runs 5 --jobs 6
```

If Jobs take only a few seconds, increase `--repeats` so startup overhead does not
dominate. Use the same settings for all later policies. Increase `--timeout` if
needed. The default is 600 seconds per Job, including waiting after Job start.
Timeouts and failures are recorded, and the command exits unsuccessfully if any
batch does not fully succeed. Do not discard failed runs from your report.

Each session writes `results/<session>/` with:

- `settings.json` and `nodes.json`: parameters and node snapshot.
- `jobs.csv`: Pod placement, status, image ID, restarts, and timestamps.
- `batches.csv`: completion counts, observed batch duration, and throughput.
- `run-N/`: submitted manifests, Job/Pod/event JSON, and workload logs.

The runner creates a unique namespace per batch and deletes only that namespace
after export. Use `--keep` to retain resources for debugging. Interrupted runs
may leave a namespace; inspect it before manually deleting it.

`creation_to_scheduled_seconds` includes queueing and timestamp granularity; it
is NOT scheduler CPU time or plugin execution overhead. `observed_batch_seconds`
includes submission, polling, and API overhead (roughly one-second polling
resolution). `container_seconds` is container lifetime, while the log's
`wall_seconds` measures the workload itself. CPU time is also logged. Final
scheduler-overhead experiments require scheduler metrics or instrumentation.

## Local validation (no cluster required)

```bash
python3 -m unittest discover -s tests -v
python3 workloads/cpu_benchmark.py --limit 10000 --repeats 1
```

These validate computation and manifest/timing helpers, not Kubernetes execution.
`validation.txt` contains the checks run when preparing this package. No cluster
results were generated in the preparation environment.

## Next implementation milestone

Once the baseline succeeds, build the Go Scheduling Framework scoring plugin
against the chosen Kubernetes version. Start with fixed, documented synthetic
energy and carbon inputs. Keep resource feasibility filters and explicitly
configure scoring weights. Add carbon caching and recorded traces afterward.
Use the identical benchmark with `--scheduler green-scheduler` only after that
scheduler is deployed. Modelled energy and emissions must be clearly separated
from measured workload runtime; kind cannot validate physical regional savings.
