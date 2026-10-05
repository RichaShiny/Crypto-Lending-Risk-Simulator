import io
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from src.cascade_simulation import run_cascade_aware_monte_carlo
from src.data_generator import generate_protocol_positions
from src.run_bundle import build_run_bundle, replay_run_bundle


def sample_bundle():
    positions = generate_protocol_positions(n_positions=12)
    settings = dict(market_depth_usd={'ETH': 1e6, 'BTC': 2e6, 'SOL': 5e5},
                    n_simulations=3, seed=13, correlation_matrix=np.eye(3))
    results = run_cascade_aware_monte_carlo(positions=positions, **settings)
    return build_run_bundle(positions, results, settings), results


def test_replay_preserves_positions_and_paired_scenario_results():
    bundle, results = sample_bundle()
    replay = replay_run_bundle(bundle)
    with zipfile.ZipFile(io.BytesIO(bundle)) as original, zipfile.ZipFile(io.BytesIO(replay)) as repeated:
        assert original.read('positions.csv') == repeated.read('positions.csv')
        actual = pd.read_csv(io.BytesIO(repeated.read('scenarios.csv')))
        pd.testing.assert_frame_equal(actual, results, check_exact=False, rtol=1e-12, atol=1e-12)
        manifest = json.loads(original.read('manifest.json'))
        assert manifest['settings']['max_rounds'] == 20
        assert manifest['settings']['degrees_of_freedom'] == 5
        assert manifest['settings']['correlation_matrix'] == np.eye(3).tolist()
        assert {'python', 'numpy', 'pandas'} <= manifest['environment'].keys()


@pytest.mark.parametrize('filename', ['positions.csv', 'scenarios.csv', 'summary.json'])
def test_replay_rejects_modified_files(filename):
    bundle, _ = sample_bundle()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle)) as source, zipfile.ZipFile(output, 'w') as target:
        for name in source.namelist():
            target.writestr(name, source.read(name) + (b' ' if name == filename else b''))
    with pytest.raises(ValueError, match='Checksum mismatch'):
        replay_run_bundle(output.getvalue())


def test_cli_replays_and_refuses_to_overwrite(tmp_path):
    import subprocess
    import sys

    bundle, _ = sample_bundle()
    source = tmp_path / 'run.zip'
    output = tmp_path / 'replay.zip'
    source.write_bytes(bundle)
    command = [sys.executable, '-m', 'src.run_bundle', str(source), str(output)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    saved = output.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode != 0
    assert 'Output already exists' in second.stderr
    assert output.read_bytes() == saved
