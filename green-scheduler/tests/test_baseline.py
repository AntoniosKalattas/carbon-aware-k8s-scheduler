import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = load('bench', ROOT/'workloads/cpu_benchmark.py')
runner = load('runner', ROOT/'scripts/run_baseline.py')


class BaselineTests(unittest.TestCase):
    def test_known_prime_counts(self):
        for limit, expected in [(2, 1), (10, 4), (100, 25), (1000, 168)]:
            self.assertEqual(bench.count_primes(limit), expected)

    def test_timestamp_offsets_and_missing_data(self):
        self.assertEqual(runner.seconds('2026-11-06T10:00:00Z', '2026-11-06T12:00:03+02:00'), 3)
        self.assertEqual(runner.seconds(None, '2026-11-06T10:00:00Z'), '')

    def test_job_is_bounded_and_worker_only(self):
        args = SimpleNamespace(timeout=60, scheduler='default-scheduler',
                               image='python:3.12.8-slim', limit=1000, repeats=2)
        job = runner.manifest('test', 1, args)
        self.assertEqual(job['spec']['backoffLimit'], 0)
        self.assertEqual(job['spec']['activeDeadlineSeconds'], 60)
        pod = job['spec']['template']['spec']
        self.assertEqual(pod['nodeSelector'], {'benchmark': 'true'})
        self.assertEqual(pod['containers'][0]['resources']['requests'],
                         pod['containers'][0]['resources']['limits'])

class RunnerFlowTests(unittest.TestCase):
    def test_successful_batch_exports_and_cleans_up(self):
        import json
        import tempfile
        from unittest.mock import patch
        calls = []
        def fake(*args, payload=None):
            calls.append(args)
            if args == ('config', 'current-context'):
                return 'kind-test\n'
            if 'nodes' in args:
                return json.dumps({'items': [{'metadata': {'name': f'w{i}', 'labels': {'region': 'test'}}} for i in range(3)]})
            if 'jobs' in args:
                return json.dumps({'items': [{'status': {'succeeded': 1, 'conditions': [{'type': 'Complete', 'status': 'True'}]}}]})
            if 'pods' in args:
                return json.dumps({'items': [{'metadata': {'name': 'cpu-000-x', 'creationTimestamp': '2026-11-06T10:00:00Z'},
                    'spec': {'nodeName': 'w0'}, 'status': {'phase': 'Succeeded',
                    'conditions': [{'type': 'PodScheduled', 'status': 'True', 'lastTransitionTime': '2026-11-06T10:00:01Z'}],
                    'containerStatuses': [{'imageID': 'test-image', 'restartCount': 0,
                        'state': {'terminated': {'startedAt': '2026-11-06T10:00:02Z', 'finishedAt': '2026-11-06T10:00:05Z', 'exitCode': 0}}}]}}]})
            if 'events' in args:
                return '{"items": []}'
            if 'logs' in args:
                return '{"checksum": 1229}\n'
            return ''
        for with_snapshot in (False, True):
            with self.subTest(with_snapshot=with_snapshot), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                argv = ['runner', '--context', 'kind-test', '--runs', '1', '--jobs', '1']
                snapshot = {'schema_version': 1, 'regions': {'italy': {'carbon': 100}}}
                if with_snapshot:
                    source = root / 'carbon-inputs.json'
                    source.write_text(json.dumps(snapshot))
                    argv += ['--carbon-snapshot', str(source)]
                with patch.object(runner, 'ROOT', root), patch.object(runner, 'kubectl', fake), patch('sys.argv', argv):
                    runner.main()
                outputs = list((root/'results').iterdir())
                self.assertEqual(len(outputs), 1)
                self.assertIn('Succeeded', (outputs[0]/'jobs.csv').read_text())
                self.assertIn('successful_jobs_per_second', (outputs[0]/'batches.csv').read_text())
                self.assertTrue((outputs[0]/'run-1'/'events.json').exists())
                self.assertTrue(any(c[:2] == ('delete', 'namespace') for c in calls))
                archived = outputs[0] / 'carbon-inputs.json'
                self.assertEqual(archived.exists(), with_snapshot)
                if with_snapshot:
                    self.assertEqual(json.loads(archived.read_text()), snapshot)
                    settings = json.loads((outputs[0]/'settings.json').read_text())
                    self.assertEqual(settings['carbon_snapshot'], str(source))


if __name__ == '__main__':
    unittest.main()
