"""Exercise trace selection, fallback, and the scheduler configuration boundary."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'carbon_configure', ROOT / 'green-plugin/scripts/configure.py')
configure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configure)
HEADER = 'timestamp,region,carbon_gco2_per_kwh,source\n'


class CarbonTraceTests(unittest.TestCase):
    def snapshot(self, rows, at='2026-11-11T01:00:00Z', max_age=60):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.csv'
            path.write_text(HEADER + rows)
            return configure.carbon_snapshot(path, at, max_age)

    def test_static_configuration_keeps_existing_profiles(self):
        regions, provenance = configure.carbon_snapshot()
        self.assertEqual(regions, configure.REGIONS)
        config = configure.scheduler_config(regions, Path('/private/kubeconfig'))
        self.assertFalse(config['leaderElection']['leaderElect'])
        self.assertEqual([p['schedulerName'] for p in config['profiles']],
                         ['energy-scheduler', 'green-scheduler'])
        for profile in config['profiles']:
            self.assertEqual(set(profile['plugins']), {'score'})
            self.assertEqual(profile['pluginConfig'][0]['args']['regions'], regions)
        self.assertEqual(provenance['mode'], 'static')

    def test_demo_changes_carbon_winner_and_keeps_energy_profiles(self):
        trace = ROOT / 'carbon/demo-trace.csv'
        for hour, winner in [(0, 'italy'), (1, 'cyprus'), (2, 'greece')]:
            with self.subTest(hour=hour):
                regions, provenance = configure.carbon_snapshot(
                    trace, f'2026-11-11T0{hour}:00:00Z')
                self.assertEqual(min(regions, key=lambda r: regions[r]['watts'] * regions[r]['carbon']), winner)
                self.assertEqual({r: p['watts'] for r, p in regions.items()},
                                 {'cyprus': 40, 'greece': 60, 'italy': 80})
                self.assertTrue(all(p['status'] == 'trace' for p in provenance['regions'].values()))
                self.assertEqual(len(provenance['trace_sha256']), 64)

    def test_selection_handles_unsorted_rows_offsets_and_future_data(self):
        regions, provenance = self.snapshot(
            '2026-11-11T02:00:00Z,cyprus,1,future\n'
            '2026-11-11T00:30:00Z,cyprus,20,older\n'
            '2026-11-11T03:00:00+02:00,cyprus,0,newest\n')
        self.assertEqual(regions['cyprus']['carbon'], 0)
        self.assertEqual(provenance['regions']['cyprus']['source'], 'newest')
        self.assertEqual(provenance['regions']['cyprus']['age_seconds'], 0)
        self.assertEqual(provenance['regions']['italy']['status'], 'fallback_missing')
        self.assertEqual(regions['italy']['carbon'], 100)

    def test_staleness_boundary_and_fallback(self):
        row = '2026-11-11T00:00:00Z,cyprus,1,recorded-test\n'
        regions, provenance = self.snapshot(row)
        self.assertEqual(regions['cyprus']['carbon'], 1)
        self.assertEqual(provenance['regions']['cyprus']['status'], 'trace')
        regions, provenance = self.snapshot(row, at='2026-11-11T01:00:01Z')
        self.assertEqual(regions['cyprus']['carbon'], 700)
        detail = provenance['regions']['cyprus']
        self.assertEqual(detail['status'], 'fallback_stale')
        self.assertEqual(detail['sample_source'], 'recorded-test')
        self.assertEqual(detail['sample_carbon'], 1)

    def test_rejects_invalid_readings(self):
        rows = [
            '',
            '2026-11-11T00:00:00,cyprus,1,test\n',
            '2026-11-11T00:00:00Z,unknown,1,test\n',
            '2026-11-11T00:00:00Z,cyprus,-1,test\n',
            '2026-11-11T00:00:00Z,cyprus,nan,test\n',
            '2026-11-11T00:00:00Z,cyprus,inf,test\n',
            '2026-11-11T00:00:00Z,cyprus,1,\n',
            '2026-11-11T00:00:00Z,cyprus,1,test\n' * 2,
        ]
        for row in rows:
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.snapshot(row)
        for age in [0, -1, float('nan'), float('inf')]:
            with self.subTest(age=age), self.assertRaises(ValueError):
                configure.carbon_snapshot(max_age_minutes=age)
        with self.assertRaises(ValueError):
            configure.carbon_snapshot(at='2026-11-11T00:00:00Z')

    def test_cli_writes_config_and_credential_free_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ROOT / 'carbon/demo-trace.csv'
            with patch.object(configure, 'ROOT', root), patch('sys.argv', [
                'configure', '--trace', str(trace), '--at', '2026-11-11T01:00:00Z'
            ]):
                configure.main()
            config = json.loads((root / '.runtime/scheduler.json').read_text())
            provenance = json.loads((root / '.runtime/carbon-inputs.json').read_text())
            self.assertEqual(config['profiles'][1]['pluginConfig'][0]['args']['regions']['cyprus']['carbon'], 50)
            self.assertEqual(provenance['regions']['cyprus']['carbon'], 50)
            self.assertNotIn('clientConnection', provenance)
            self.assertEqual((root / '.runtime/carbon-inputs.json').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
