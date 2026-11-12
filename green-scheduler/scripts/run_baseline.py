#!/usr/bin/env python3
"""Run isolated Job batches, preserve evidence, and export timing CSVs."""
import argparse
from collections import Counter
import csv
import datetime as dt
import json
from pathlib import Path
from statistics import mean
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def kubectl(*args, payload=None):
    return subprocess.check_output(['kubectl', *args], input=payload, text=True)


def seconds(start, end):
    if not start or not end:
        return ''
    return (dt.datetime.fromisoformat(end.replace('Z', '+00:00')) -
            dt.datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds()


def manifest(namespace, index, args, regions=None, cpu=1):
    job = {'apiVersion': 'batch/v1', 'kind': 'Job',
            'metadata': {'name': f'cpu-{index:03}', 'namespace': namespace},
            'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': args.timeout,
                     'template': {'metadata': {'labels': {'app': 'cpu-benchmark'}},
                                  'spec': {'restartPolicy': 'Never',
                                           'schedulerName': args.scheduler,
                                           'nodeSelector': {'benchmark': 'true'},
                                           'containers': [{'name': 'cpu', 'image': args.image,
                                               'imagePullPolicy': 'IfNotPresent',
                                               'command': ['python', '/bench/cpu_benchmark.py',
                                                           '--limit', str(args.limit),
                                                           '--repeats', str(args.repeats)],
                                               'resources': {'requests': {'cpu': str(cpu), 'memory': '128Mi'},
                                                             'limits': {'cpu': str(cpu), 'memory': '128Mi'}},
                                               'volumeMounts': [{'name': 'code', 'mountPath': '/bench', 'readOnly': True}]}],
                                           'volumes': [{'name': 'code', 'configMap': {'name': 'benchmark-code'}}]}}}}


    if regions is not None:
        container = job['spec']['template']['spec']['containers'][0]
        container['command'] += ['--input-region', args.input_region]
        container['env'] = [
            {'name': 'BENCHMARK_NODE_NAME',
             'valueFrom': {'fieldRef': {'fieldPath': 'spec.nodeName'}}},
            {'name': 'BENCHMARK_NODE_REGIONS', 'value': json.dumps(regions)},
        ]
    return job


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', type=int, default=5)
    p.add_argument('--jobs', type=int, default=6)
    p.add_argument('--workers-per-region', type=int, choices=(1, 2), default=1,
                   help='Expected number of benchmark workers per region')
    p.add_argument('--cpu', type=int, default=1,
                   help='CPU cores requested and limited per job (default: 1)')
    p.add_argument('--limit', type=int, default=300000)
    p.add_argument('--repeats', type=int, default=10)
    p.add_argument('--timeout', type=int, default=600)
    p.add_argument('--scheduler', default='default-scheduler')
    p.add_argument('--input-region', choices=('cyprus', 'greece', 'italy'),
                   help='Enable synthetic data access delay from this region')
    p.add_argument('--image', default='python:3.12.8-slim')
    p.add_argument('--context', required=True, help='Expected kubectl context; prevents wrong-cluster runs')
    p.add_argument('--keep', action='store_true', help='Keep namespaces after exporting results')
    p.add_argument('--carbon-snapshot', type=Path,
                   help='Archive the carbon-inputs.json generated for the running scheduler')
    args = p.parse_args()
    if min(args.runs, args.jobs, args.repeats, args.timeout, args.cpu) < 1 or args.limit < 2:
        p.error('positive counts required; limit >= 2')
    carbon_inputs = None
    if args.carbon_snapshot:
        try:
            carbon_inputs = json.loads(args.carbon_snapshot.read_text())
            if carbon_inputs.get('schema_version') != 1 or not isinstance(carbon_inputs.get('regions'), dict):
                p.error('carbon snapshot must be a generated carbon-inputs.json')
        except (OSError, ValueError, AttributeError) as error:
            p.error(f'invalid carbon snapshot: {error}')
    context = kubectl('config', 'current-context').strip()
    if context != args.context:
        p.error(f'current context is {context!r}, expected {args.context!r}')
    nodes = json.loads(kubectl('get', 'nodes', '-l', 'benchmark=true', '-o', 'json'))
    expected_workers = 3 * args.workers_per_region
    if len(nodes['items']) != expected_workers:
        p.error(f'expected {expected_workers} workers labeled benchmark=true')
    regions = {n['metadata']['name']: n['metadata'].get('labels', {}).get('region', '') for n in nodes['items']}
    if args.input_region or args.workers_per_region == 2:
        expected_regions = dict.fromkeys(('cyprus', 'greece', 'italy'), args.workers_per_region)
        if Counter(regions.values()) != expected_regions:
            p.error(f'expected {args.workers_per_region} benchmark worker(s) in each region')
    latency_regions = regions if args.input_region else None
    session = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    out = ROOT / 'results' / session
    out.mkdir(parents=True)
    (out/'settings.json').write_text(json.dumps(vars(args), indent=2, default=str))
    if carbon_inputs is not None:
        (out/'carbon-inputs.json').write_text(json.dumps(carbon_inputs, indent=2))
    (out/'nodes.json').write_text(json.dumps(nodes, indent=2))
    rows, batches = [], []
    failed = False
    for run in range(1, args.runs+1):
        ns = f'green-{session.lower()}-{run}'
        folder = out / f'run-{run}'
        folder.mkdir()
        kubectl('create', 'namespace', ns)
        try:
            kubectl('-n', ns, 'create', 'configmap', 'benchmark-code',
                    '--from-file='+str(ROOT/'workloads/cpu_benchmark.py'))
            specs = {'apiVersion': 'v1', 'kind': 'List',
                     'items': [manifest(ns, i, args, latency_regions, cpu=args.cpu) for i in range(args.jobs)]}
            (folder/'submitted.json').write_text(json.dumps(specs, indent=2))
            begin = time.monotonic()
            kubectl('apply', '-f', '-', payload=json.dumps(specs))
            timed_out = False
            while True:
                jobs = json.loads(kubectl('-n', ns, 'get', 'jobs', '-o', 'json'))
                terminal = sum(any(c['type'] in ('Complete', 'Failed') and c['status'] == 'True'
                                   for c in j.get('status', {}).get('conditions', [])) for j in jobs['items'])
                if len(jobs['items']) == args.jobs and terminal == args.jobs:
                    break
                if time.monotonic()-begin > args.timeout+30:
                    timed_out = True
                    break
                time.sleep(1)
            elapsed = time.monotonic()-begin
            pods = json.loads(kubectl('-n', ns, 'get', 'pods', '-o', 'json'))
            for name, obj in [('jobs', jobs), ('pods', pods)]:
                (folder/f'{name}.json').write_text(json.dumps(obj, indent=2))
            (folder/'events.json').write_text(kubectl('-n', ns, 'get', 'events', '-o', 'json'))
            successes = sum(j.get('status', {}).get('succeeded', 0) for j in jobs['items'])
            failed |= successes != args.jobs or timed_out
            batches.append(dict(run=run, successful_jobs=successes, submitted_jobs=args.jobs,
                                observed_batch_seconds=elapsed, successful_jobs_per_second=successes/elapsed,
                                timed_out=timed_out))
            latency_rows = []
            for pod in pods['items']:
                meta, status = pod['metadata'], pod.get('status', {})
                scheduled = next((c.get('lastTransitionTime') for c in status.get('conditions', [])
                                  if c['type']=='PodScheduled' and c['status']=='True'), None)
                containers = status.get('containerStatuses', [])
                terminated = containers[0].get('state', {}).get('terminated', {}) if containers else {}
                node = pod['spec'].get('nodeName', '')
                row = dict(run=run, pod=meta['name'], node=node, region=regions.get(node, ''),
                           phase=status.get('phase', ''), created=meta['creationTimestamp'],
                           scheduled=scheduled or '', started=terminated.get('startedAt', ''),
                           finished=terminated.get('finishedAt', ''), exit_code=terminated.get('exitCode', ''),
                           image_id=containers[0].get('imageID', '') if containers else '',
                           restarts=sum(c.get('restartCount', 0) for c in containers))
                row['creation_to_scheduled_seconds'] = seconds(row['created'], row['scheduled'])
                row['container_seconds'] = seconds(row['started'], row['finished'])
                row['creation_to_finish_seconds'] = seconds(row['created'], row['finished'])
                try:
                    logs = kubectl('-n', ns, 'logs', meta['name'])
                except subprocess.CalledProcessError:
                    logs = ''
                (folder/(meta['name']+'.log')).write_text(logs)
                if args.input_region:
                    row['input_region'] = args.input_region
                    row['modeled_wait_seconds'] = ''
                    row['observed_wait_seconds'] = ''
                    row['cpu_workload_wall_seconds'] = ''
                    row['cpu_seconds'] = ''
                    if row['phase'] == 'Succeeded':
                        try:
                            metrics = json.loads(logs)
                            row['modeled_wait_seconds'] = metrics['modeled_wait_seconds']
                            row['observed_wait_seconds'] = metrics['observed_wait_seconds']
                            row['cpu_workload_wall_seconds'] = metrics['wall_seconds']
                            row['cpu_seconds'] = metrics['cpu_seconds']
                            latency_rows.append(row)
                        except (ValueError, KeyError, TypeError):
                            print(f'Missing latency metrics for {row["pod"]}', flush=True)
                            failed = True
                rows.append(row)
            for name, data in [('jobs.csv', rows), ('batches.csv', batches)]:
                if data:
                    with (out/name).open('w', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator='\n')
                        writer.writeheader()
                        writer.writerows(data)
            print(f'Run {run}: {successes}/{args.jobs} succeeded, observed batch {elapsed:.2f}s', flush=True)
            if latency_rows:
                modeled = mean(row['modeled_wait_seconds'] for row in latency_rows)
                observed = mean(row['observed_wait_seconds'] for row in latency_rows)
                print(f'Input: {args.input_region}; mean wait across {len(latency_rows)} jobs: '
                      f'{modeled:.2f}s modeled, {observed:.2f}s observed', flush=True)
        finally:
            if not args.keep:
                kubectl('delete', 'namespace', ns, '--wait=false')
    print(f'Results: {out}')
    if failed:
        raise SystemExit('One or more batches failed or timed out; inspect exported evidence.')


if __name__ == '__main__':
    main()
