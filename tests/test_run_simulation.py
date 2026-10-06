import json
import subprocess
import sys

import pandas as pd

from src.data_generator import generate_protocol_positions
from src.run_bundle import load_run_bundle


def command(tmp_path, extra=(), settings=None):
    config = tmp_path / 'settings.json'
    config.write_text(json.dumps(settings or dict(market_depth_usd={'ETH':1e6,'BTC':2e6,'SOL':5e5}, n_simulations=3, seed=17)))
    output = tmp_path / 'run.zip'
    args = [sys.executable, '-m', 'src.run_simulation', '--settings', str(config), '--output', str(output), *extra]
    return args, output


def test_headless_run_matches_recorded_inputs_and_refuses_overwrite(tmp_path):
    args, output = command(tmp_path, ['--portfolio-size', '12', '--portfolio-seed', '8'])
    run = subprocess.run(args, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    manifest, positions, results, summary = load_run_bundle(output.read_bytes())
    pd.testing.assert_frame_equal(positions, generate_protocol_positions(12, seed=8))
    assert len(results) == 3
    assert manifest['settings']['seed'] == 17
    assert summary['simulations'] == 3
    saved = output.read_bytes()
    second = subprocess.run(args, capture_output=True, text=True)
    assert second.returncode != 0
    assert 'Output already exists' in second.stderr
    assert output.read_bytes() == saved


def test_headless_run_uses_supplied_portfolio(tmp_path):
    positions = generate_protocol_positions(9, seed=7)
    source = tmp_path / 'positions.csv'
    positions.to_csv(source, index=False)
    args, output = command(tmp_path, ['--positions', str(source)])
    run = subprocess.run(args, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    _, actual, _, _ = load_run_bundle(output.read_bytes())
    pd.testing.assert_frame_equal(actual, positions)


def test_invalid_settings_leave_no_output(tmp_path):
    args, output = command(tmp_path, ['--portfolio-size', '12'], settings={'market_depth_usd': {'ETH':1e6,'BTC':2e6,'SOL':5e5}, 'degrees_of_freedom': 2})
    run = subprocess.run(args, capture_output=True, text=True)
    assert run.returncode != 0
    assert 'greater than 2' in run.stderr
    assert not output.exists()
