"""Generate scheduler profiles from fixed inputs or a reproducible CSV snapshot."""
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGIONS = {
    'cyprus': {'watts': 40, 'carbon': 700},
    'greece': {'watts': 60, 'carbon': 350},
    'italy': {'watts': 80, 'carbon': 100},
}
PREDICTED_SECONDS = 10.5


def timestamp(value):
    """Require an explicit timezone and normalize comparisons to UTC."""
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamps must include Z or a UTC offset')
    return result.astimezone(timezone.utc)


def carbon_snapshot(trace=None, at=None, max_age_minutes=60):
    """Select the latest past reading per region, with a documented fallback."""
    if (trace is None) != (at is None):
        raise ValueError('--trace and --at must be supplied together')
    if not math.isfinite(max_age_minutes) or max_age_minutes <= 0:
        raise ValueError('--max-age-minutes must be positive and finite')
    profiles = copy.deepcopy(REGIONS)
    provenance = {
        'schema_version': 1,
        'mode': 'static',
        'replay_at': None,
        'trace_sha256': None,
        'trace_file': None,
        'max_age_minutes': max_age_minutes,
        'predicted_seconds': PREDICTED_SECONDS,
        'regions': {},
    }
    if trace is None:
        provenance['regions'] = {
            region: dict(profile, status='static', source='synthetic-fixed-model',
                         sample_timestamp=None, age_seconds=None)
            for region, profile in profiles.items()
        }
        return profiles, provenance

    replay_at = timestamp(at)
    raw = Path(trace).read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    required = {'timestamp', 'region', 'carbon_gco2_per_kwh', 'source'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('trace requires timestamp, region, carbon_gco2_per_kwh, source')
    readings = {region: {} for region in REGIONS}
    count = 0
    for line, row in enumerate(reader, start=2):
        region = row['region'].strip()
        if region not in REGIONS:
            raise ValueError(f'line {line}: unknown region {region!r}')
        sample_at = timestamp(row['timestamp'].strip())
        intensity = float(row['carbon_gco2_per_kwh'])
        source = row['source'].strip()
        if not math.isfinite(intensity) or intensity < 0 or not source:
            raise ValueError(f'line {line}: finite nonnegative carbon and source required')
        if sample_at in readings[region]:
            raise ValueError(f'line {line}: duplicate timestamp for {region}')
        readings[region][sample_at] = (intensity, source)
        count += 1
    if count == 0:
        raise ValueError('trace contains no readings')

    provenance.update(mode='trace', replay_at=replay_at.isoformat(),
                      trace_sha256=hashlib.sha256(raw).hexdigest(),
                      trace_file=Path(trace).name)
    for region, candidates in readings.items():
        past = [sample_at for sample_at in candidates if sample_at <= replay_at]
        detail = dict(profiles[region], status='fallback_missing',
                      source='synthetic-fixed-model', sample_timestamp=None,
                      age_seconds=None)
        if past:
            selected = max(past)
            age = (replay_at - selected).total_seconds()
            intensity, source = candidates[selected]
            detail.update(sample_timestamp=selected.isoformat(), age_seconds=age,
                          sample_source=source, sample_carbon=intensity)
            if age <= max_age_minutes * 60:
                profiles[region]['carbon'] = intensity
                detail.update(carbon=intensity, source=source, status='trace')
            else:
                detail['status'] = 'fallback_stale'
        provenance['regions'][region] = detail
    return profiles, provenance


def scheduler_config(regions, kubeconfig):
    profiles = []
    for mode, name in [('energy', 'energy-scheduler'), ('carbon', 'green-scheduler')]:
        profiles.append({
            'schedulerName': name,
            'plugins': {'score': {'disabled': [{'name': '*'}],
                                  'enabled': [{'name': 'GreenScore', 'weight': 1}]}},
            'pluginConfig': [{'name': 'GreenScore', 'args': {
                'mode': mode, 'seconds': PREDICTED_SECONDS, 'regions': regions,
            }}],
        })
    return {'apiVersion': 'kubescheduler.config.k8s.io/v1',
            'kind': 'KubeSchedulerConfiguration',
            'clientConnection': {'kubeconfig': str(kubeconfig)},
            'leaderElection': {'leaderElect': False},
            'profiles': profiles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, help='CSV with carbon readings and source labels')
    parser.add_argument('--at', help='Explicit replay timestamp, for example 2026-11-11T00:00:00Z')
    parser.add_argument('--max-age-minutes', type=float, default=60)
    args = parser.parse_args()
    try:
        regions, provenance = carbon_snapshot(args.trace, args.at, args.max_age_minutes)
    except (OSError, ValueError, TypeError, AttributeError, csv.Error) as error:
        parser.error(str(error))
    runtime = ROOT / '.runtime'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    outputs = {
        'scheduler.json': scheduler_config(regions, runtime / 'kubeconfig'),
        'carbon-inputs.json': provenance,
    }
    for name, data in outputs.items():
        path = runtime / name
        path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
        path.chmod(0o600)
    print(f'Carbon inputs: {provenance["mode"]}, replay time {provenance["replay_at"]}')
    for region, detail in provenance['regions'].items():
        print(f'  {region}: {detail["carbon"]} gCO2e/kWh ({detail["status"]})')


if __name__ == '__main__':
    main()
