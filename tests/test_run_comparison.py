import io
import json
import zipfile

import pytest

from src.cascade_simulation import run_cascade_aware_monte_carlo
from src.data_generator import generate_protocol_positions
from src.run_bundle import build_run_bundle
from src.run_comparison import compare_run_bundles


def make_run(seed=42, portfolio_seed=42, depth=1e6, reverse=False, duplicate=False):
    positions = generate_protocol_positions(n_positions=12, seed=portfolio_seed)
    settings = dict(market_depth_usd={asset: depth for asset in ('ETH', 'BTC', 'SOL')},
                    n_simulations=4, seed=seed)
    results = run_cascade_aware_monte_carlo(positions=positions, **settings)
    if reverse:
        results = results.iloc[::-1]
    if duplicate:
        results['simulation_id'] = 0
    return build_run_bundle(positions, results, settings), results


def test_same_run_has_zero_changes():
    bundle, _ = make_run()
    report = compare_run_bundles(bundle, bundle)
    assert report['paired']
    assert all(row['change'] == 0 for row in report['metrics'])
    assert all(row['mean_change'] == 0 for row in report['paired_deltas'])
    assert report['settings_changes'] == []


def test_depth_change_is_paired_and_deltas_have_candidate_minus_baseline_direction():
    baseline, left = make_run(depth=1e4)
    candidate, right = make_run(depth=1e8, reverse=True)
    report = compare_run_bundles(baseline, candidate)
    assert report['paired']
    assert report['settings_changes'][0]['field'] == 'market_depth_usd'
    expected = right.set_index('simulation_id')['cascade_debt_share'] - left.set_index('simulation_id')['cascade_debt_share']
    actual = next(row for row in report['paired_deltas'] if row['metric'] == 'cascade_debt_share')
    assert actual['mean_change'] == pytest.approx(expected.mean())
    assert actual['scenarios'] == 4


@pytest.mark.parametrize('settings', [{'seed': 43}, {'portfolio_seed': 43}, {'duplicate': True}])
def test_unpaired_runs_do_not_report_paired_deltas(settings):
    baseline, _ = make_run()
    candidate, _ = make_run(**settings)
    report = compare_run_bundles(baseline, candidate)
    assert not report['paired']
    assert report['paired_deltas'] == []


def test_metadata_changes_are_visible():
    baseline, _ = make_run()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(baseline)) as source, zipfile.ZipFile(buffer, 'w') as target:
        for name in source.namelist():
            data = source.read(name)
            if name == 'manifest.json':
                manifest = json.loads(data)
                manifest['environment']['numpy'] = 'different-version'
                manifest['source_sha256']['simulation.py'] = 'different-source'
                data = json.dumps(manifest).encode()
            target.writestr(name, data)
    report = compare_run_bundles(baseline, buffer.getvalue())
    assert report['environment_changes'][0]['field'] == 'numpy'
    assert report['source_changes'][0]['field'] == 'simulation.py'


def test_comparison_validates_checksums():
    baseline, _ = make_run()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(baseline)) as source, zipfile.ZipFile(buffer, 'w') as target:
        for name in source.namelist():
            target.writestr(name, source.read(name) + (b' ' if name == 'scenarios.csv' else b''))
    with pytest.raises(ValueError, match='Checksum mismatch'):
        compare_run_bundles(baseline, buffer.getvalue())


def test_equal_recorded_seed_is_insufficient_when_shocks_differ():
    baseline, results = make_run()
    positions = generate_protocol_positions(n_positions=12, seed=42)
    settings = dict(market_depth_usd={asset: 1e6 for asset in ('ETH', 'BTC', 'SOL')},
                    n_simulations=4, seed=42)
    changed = results.copy()
    changed.loc[0, 'eth_return'] += 0.01
    candidate = build_run_bundle(positions, changed, settings)
    report = compare_run_bundles(baseline, candidate)
    assert report['settings_changes'] == []
    assert report['same_portfolio']
    assert not report['same_market_draws']
    assert not report['paired']
    assert report['paired_deltas'] == []


@pytest.mark.parametrize('candidate_seed,paired', [(42, True), (43, False)])
def test_comparison_cli_writes_report_and_preserves_existing_output(tmp_path, candidate_seed, paired):
    import subprocess
    import sys

    baseline, _ = make_run()
    candidate, _ = make_run(seed=candidate_seed)
    left, right, output = tmp_path / 'baseline.zip', tmp_path / 'candidate.zip', tmp_path / 'report.json'
    left.write_bytes(baseline)
    right.write_bytes(candidate)
    command = [sys.executable, '-m', 'src.run_comparison', str(left), str(right), '--output', str(output)]
    run = subprocess.run(command, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(output.read_text()) == compare_run_bundles(baseline, candidate)
    assert ('Paired comparison:' if paired else 'Unpaired comparison:') in run.stdout
    saved = output.read_bytes()
    again = subprocess.run(command, capture_output=True, text=True)
    assert again.returncode != 0
    assert 'Output already exists' in again.stderr
    assert output.read_bytes() == saved


def test_comparison_cli_rejects_invalid_archive_without_report(tmp_path):
    import subprocess
    import sys

    source, output = tmp_path / 'invalid.zip', tmp_path / 'report.json'
    source.write_bytes(b'not a ZIP archive')
    run = subprocess.run([sys.executable, '-m', 'src.run_comparison', str(source), str(source),
                          '--output', str(output)], capture_output=True, text=True)
    assert run.returncode != 0
    assert 'not a zip file' in run.stderr.lower()
    assert not output.exists()
