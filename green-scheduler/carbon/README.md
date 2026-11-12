# Carbon intensity trace replay

Replay selects an immutable snapshot from a CSV at an explicit timestamp before
starting the scheduler. This makes each workload batch repeatable independently
of the wall clock. To evaluate another timestamp, stop the custom scheduler,
start it with the new timestamp, and submit the same workload again.

## Trace format

The UTF-8 CSV requires these columns:

```csv
timestamp,region,carbon_gco2_per_kwh,source
2026-11-11T00:00:00Z,cyprus,700,synthetic-demo
2026-11-11T00:00:00Z,greece,350,synthetic-demo
2026-11-11T00:00:00Z,italy,100,synthetic-demo
```

- `timestamp` uses ISO 8601 with `Z` or an explicit UTC offset.
- `region` is `cyprus`, `greece`, or `italy`.
- `carbon_gco2_per_kwh` is a finite nonnegative number in gCO2e/kWh.
- `source` identifies the measurement dataset, provider, or synthetic generator.

Rows can be unsorted. Duplicate region/timestamp pairs, invalid values, missing
columns, empty traces, and unsupported regions cause configuration generation
to fail. Timestamp comparisons normalize to UTC. Additional columns are allowed.

`demo-trace.csv` contains invented inputs, labeled `synthetic-demo`. It provides
three controlled conditions for checking that a changing carbon signal changes
placement while the energy profiles stay fixed.

| Trace time on November 11, 2026 UTC | Cyprus | Greece | Italy | Preferred carbon region |
|---|---:|---:|---:|---|
| 00:00 | 700 | 350 | 100 | Italy |
| 01:00 | 50 | 400 | 600 | Cyprus |
| 02:00 | 600 | 50 | 800 | Greece |

The values have units gCO2e/kWh. Preferred regions also account for the existing
40/60/80 W power assumptions. The energy-only profile continues to prefer Cyprus.
Resource feasibility filters can change the final placement.

## Selection and fallback

For each region, select the latest reading at or before `--at`. Future readings
are excluded. A reading is usable when its age is at most `--max-age-minutes`
(default 60). Exactly 60 minutes old remains valid at the default limit.

If a region has no past reading, or its latest past reading is stale, use the
existing synthetic fixed carbon value for that region. The provenance records
`fallback_missing` or `fallback_stale`, the effective value, and the previous
reading's age and source when available. Fixed values are Cyprus 700, Greece
350, and Italy 100 gCO2e/kWh. This fallback is an explicit modeling assumption.
An unreadable or malformed trace stops startup so data errors are visible.

Power and the predicted runtime remain 40/60/80 W and 10.5 s. Each selected
snapshot is cached in the scheduler configuration for that launch. Score calls
use the existing in-memory Go model. Updates occur between replay conditions
through a scheduler restart.

## Run a replay on the six-worker cluster

First verify `green-six` is running. In a terminal at `green-scheduler/`, enable
all six workers and select the context:

```bash
kubectl config use-context kind-green-six
kubectl --context kind-green-six label nodes -l region benchmark=true --overwrite
```

In the scheduler terminal, stop any running custom scheduler with Ctrl+C. From
`green-scheduler/green-plugin/`, launch a snapshot:

```bash
bash scripts/start.sh kind-green-six \
  --trace ../carbon/demo-trace.csv --at 2026-11-11T01:00:00Z
```

At startup, the command prints effective carbon values and their selection
status. Leave this terminal open. In a second terminal at `green-scheduler/`:

```bash
python3 scripts/run_baseline.py --context kind-green-six \
  --scheduler green-scheduler --workers-per-region 2 --cpu 3 \
  --input-region italy --runs 1 --jobs 6 --limit 300000 --repeats 30 \
  --carbon-snapshot green-plugin/.runtime/carbon-inputs.json
```

With sufficient available CPU, expect three Jobs on each Cyprus worker at 01:00.
Repeat at 00:00 and 02:00 by restarting the scheduler with that `--at` value.
The expected preferred regions are Italy and Greece, respectively. These are
new replay experiments to validate on the cluster.

For policy comparisons, run the same trace timestamp and workload through
`default-scheduler`, `energy-scheduler`, and `green-scheduler`. Alternate order
across repeated batches. Apply identical snapshot provenance to all three, so
the modeled carbon comparison uses the same inputs even for default placement.

## Preserve input provenance

`configure.py` generates two files in the private `.runtime/` directory:

- `scheduler.json` contains the scheduler profiles and kubeconfig path.
- `carbon-inputs.json` contains the replay timestamp, trace SHA-256 checksum,
  power assumptions, effective carbon values, sources, selected sample timestamps,
  ages, fallback statuses, and predicted runtime.

`--carbon-snapshot` copies only `carbon-inputs.json` into the experiment's results
folder. Use the snapshot from the current scheduler launch and leave its
configuration unchanged during the batch. The runner archives the supplied file,
and the operator is responsible for matching it to the active scheduler.
This provenance file contains model inputs that can be shared with results.
Keep kubeconfig and the rest of `.runtime/` private.

For external recorded traces, document the provider and units, map provider
regions explicitly, and retain the source dataset alongside the experiment or
record a durable source reference. Replace the demo source labels with the
actual source. Querying the replay time does not measure live regional carbon.

## Check without a cluster

From the repository root:

```bash
python3 -m unittest discover -s green-scheduler/tests -v
```

Tests cover static compatibility, changing preferred regions, unsorted and
future readings, timezone offsets, stale/missing fallback, invalid data, and
archiving the selected snapshot with an experiment.
