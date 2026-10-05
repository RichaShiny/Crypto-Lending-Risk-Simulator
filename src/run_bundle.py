"""Portable inputs and results for a cascade Monte Carlo run.

Replay with: python -m src.run_bundle run.zip replay.zip
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import io
import json
import platform
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.cascade_simulation import run_cascade_aware_monte_carlo, summarize_cascade_monte_carlo


def build_run_bundle(positions, results, settings):
    """Capture resolved engine defaults, input data, outputs, and their hashes."""
    bound = inspect.signature(run_cascade_aware_monte_carlo).bind(positions=positions, **settings)
    bound.apply_defaults()
    parameters = {key: value for key, value in bound.arguments.items() if key != 'positions'}
    if parameters['correlation_matrix'] is not None:
        parameters['correlation_matrix'] = np.asarray(parameters['correlation_matrix']).tolist()
    files = {
        'positions.csv': positions.to_csv(index=False).encode(),
        'scenarios.csv': results.to_csv(index=False).encode(),
        'summary.json': json.dumps(summarize_cascade_monte_carlo(results), indent=2, allow_nan=False).encode(),
    }
    manifest = {
        'schema_version': 1,
        'engine': 'cascade_aware_monte_carlo',
        'settings': parameters,
        'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(Path(__file__).parent.glob('*.py'))},
        'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__},
        'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    files['manifest.json'] = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def replay_run_bundle(bundle):
    """Validate the stored files and rerun using the original positions/settings."""
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('schema_version') != 1 or manifest.get('engine') != 'cascade_aware_monte_carlo':
            raise ValueError('Unsupported run bundle schema or engine')
        files = {name: archive.read(name) for name in ('positions.csv', 'scenarios.csv', 'summary.json')}
        for name, data in files.items():
            if hashlib.sha256(data).hexdigest() != manifest['sha256'].get(name):
                raise ValueError(f'Checksum mismatch: {name}')
    positions = pd.read_csv(io.BytesIO(files['positions.csv']), float_precision='round_trip')
    settings = manifest['settings']
    if settings['correlation_matrix'] is not None:
        settings['correlation_matrix'] = np.asarray(settings['correlation_matrix'])
    results = run_cascade_aware_monte_carlo(positions=positions, **settings)
    return build_run_bundle(positions, results, settings)


def main():
    parser = argparse.ArgumentParser(description='Replay an exported cascade run into a new ZIP bundle.')
    parser.add_argument('bundle', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new path')
    replay = replay_run_bundle(args.bundle.read_bytes())
    with args.output.open('xb') as output:
        output.write(replay)


if __name__ == '__main__':
    main()
