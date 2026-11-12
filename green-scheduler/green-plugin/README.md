# GreenScore prototype (Kubernetes 1.37.0)

A Go Scheduling Framework Score plugin with two profiles:
`energy-scheduler` minimizes modelled job energy, and `green-scheduler`
minimizes modelled energy multiplied by carbon intensity. The existing
`default-scheduler` remains available for the baseline.

## Deliberately synthetic inputs

| Region label | Modelled job power (W) | Synthetic carbon intensity (gCO2e/kWh) |
|---|---:|---:|
| cyprus | 40 | 700 |
| greece | 60 | 350 |
| italy | 80 | 100 |

These are invented experiment inputs, NOT measured hardware power or actual
regional carbon data. Runtime prediction is fixed at 10.5 seconds for the
calibrated workload (limit 300000, repeats 30). This assumes the same runtime
on all nodes. It is not a general predictor for arbitrary Pods.

Energy = watts * seconds / 3,600,000 (kWh).
Emissions = energy * carbon (gCO2e).
Configured costs are mapped linearly to integer scores 0..100, lower cost wins.
Equal costs receive 100. Missing region data receives 0 (feasible fallback;
can tie with the worst known region). Inputs are validated at startup.
No HTTP requests occur during scoring. Default Filter plugins remain active;
other Score plugins are disabled to isolate the experimental policy.

With the fixed inputs, the expected preferred region is Cyprus for energy-only
and Italy for combined. Trace replay changes the carbon values between conditions.
Feasibility checks can force placement elsewhere. At this small load all six
Pods may fit on the preferred worker. kind workers share physical CPUs and do
not demonstrate genuine hardware/region differences. Concentration is expected
under this simple objective, not proof of a production-ready policy.

## 1. Build on your Mac

Open a terminal in this extracted `green-plugin` folder:

```bash
go mod tidy
go test ./...
mkdir -p bin
go build -buildvcs=false -o bin/green-scheduler ./cmd/green-scheduler
```

The first build downloads Kubernetes dependencies and can take several minutes.
The package includes go.sum; retain it with the source after building. The
33 staging module replacements were derived from Kubernetes v1.37.0's go.mod
and pinned to v0.37.0. Go 1.26 or newer is required.

## 2. Start the scheduler (leave this terminal open)

```bash
bash scripts/start.sh
```

This local development deployment accepts `kind-green` (default) or
`kind-green-six` as its first argument and requires that context to be selected.
It uses that context's kubeconfig credentials. It writes a private copy into `.runtime/`, which is
excluded from git. Never share that directory. The scheduler runs on the Mac,
connecting to the existing kind API server; no custom container image is needed.
Leader election is disabled for this single-instance local prototype. Only run
one instance. Ctrl-C stops it; default-scheduler continues running.

## 3. Verify scheduling in a second terminal

Return to your existing benchmark directory:

```bash
cd /Users/alexandros/Desktop/carbon-aware-k8s-scheduler/green-scheduler
python3 scripts/run_baseline.py --context kind-green --scheduler energy-scheduler --runs 1 --jobs 6 --limit 300000 --repeats 30
python3 scripts/run_baseline.py --context kind-green --scheduler green-scheduler --runs 1 --jobs 6 --limit 300000 --repeats 30
```

Inspect each printed result folder's jobs.csv. Energy-only should prefer
`green-worker`; combined should prefer `green-worker3`, subject to resource
availability. Terminal logs at verbosity 4 show per-node score decisions.
These first runs establish correctness, not a fair final performance comparison:
repeat the default baseline while this local scheduler is also running, warm
up all policies, alternate policy order, and keep logging settings identical.

## Replay carbon inputs

The startup script forwards optional carbon arguments to `configure.py`:

```bash
bash scripts/start.sh kind-green-six \
  --trace ../carbon/demo-trace.csv --at 2026-11-11T01:00:00Z
```

The generator selects a timestamped CSV snapshot for this scheduler launch.
The Go scoring interface and fixed energy profiles stay compatible. Restart
between trace timestamps and archive the generated `carbon-inputs.json` with
`run_baseline.py --carbon-snapshot green-plugin/.runtime/carbon-inputs.json`
from the benchmark directory. See the [replay guide](../carbon/README.md) for
schema, provenance, expected placement, and stale/missing fallback.

## Remaining validation

The existing fixed-input runs verified placement, resource-feasibility fallback,
and both eligible-worker configurations. New trace replay conditions still
require cluster execution. Further work includes measured/documented energy
profiles, verified live carbon retrieval, predicted-versus-observed energy
accounting, and scheduler overhead instrumentation.

Source API references:
- https://github.com/kubernetes/kubernetes/blob/v1.37.0/staging/src/k8s.io/kube-scheduler/framework/interface.go
- https://github.com/kubernetes/kubernetes/blob/v1.37.0/pkg/scheduler/framework/runtime/registry.go
- https://github.com/kubernetes/kubernetes/blob/v1.37.0/go.mod
