"""Compare saved outcomes without assuming equal seeds imply paired scenarios."""
import numpy as np

from src.run_bundle import load_run_bundle


PAIRED_METRICS = ('first_order_debt_share', 'cascade_debt_share',
                  'amplification_debt_share', 'bad_debt_share')
SHOCK_COLUMNS = ['eth_return', 'btc_return', 'sol_return']


def _changes(before, after):
    return [{'field': key, 'baseline': before.get(key), 'candidate': after.get(key)}
            for key in sorted(before.keys() | after.keys())
            if before.get(key) != after.get(key)]


def compare_run_bundles(baseline, candidate):
    """Report candidate-minus-baseline changes and conservatively establish pairing."""
    left_meta, left_positions, left, left_summary = load_run_bundle(baseline)
    right_meta, right_positions, right, right_summary = load_run_bundle(candidate)
    same_portfolio = left_positions.equals(right_positions)
    valid_ids = all('simulation_id' in frame and frame['simulation_id'].notna().all()
                    and frame['simulation_id'].is_unique for frame in (left, right))
    same_draws = False
    if valid_ids and all(set(SHOCK_COLUMNS).issubset(frame.columns) for frame in (left, right)):
        left = left.set_index('simulation_id').sort_index()
        right = right.set_index('simulation_id').sort_index()
        same_draws = (not left.empty and left.index.equals(right.index)
                      and left[SHOCK_COLUMNS].equals(right[SHOCK_COLUMNS])
                      and np.isfinite(left[SHOCK_COLUMNS].to_numpy()).all())
    paired = bool(same_portfolio and same_draws)
    metrics = []
    for name in sorted(left_summary.keys() & right_summary.keys()):
        before, after = left_summary[name], right_summary[name]
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            metrics.append({'metric': name, 'baseline': before, 'candidate': after,
                            'change': after - before})
    paired_deltas = []
    if paired:
        for name in PAIRED_METRICS:
            if name not in left or name not in right:
                raise ValueError(f'Saved scenarios are missing metric: {name}')
            delta = right[name] - left[name]
            if not np.isfinite(delta.to_numpy()).all():
                raise ValueError(f'Saved scenarios contain nonfinite metric: {name}')
            paired_deltas.append({'metric': name, 'mean_change': float(delta.mean()),
                                  'min_change': float(delta.min()), 'max_change': float(delta.max()),
                                  'scenarios': int(len(delta))})
    return {
        'same_portfolio': bool(same_portfolio), 'same_market_draws': bool(same_draws),
        'paired': paired, 'metrics': metrics, 'paired_deltas': paired_deltas,
        'settings_changes': _changes(left_meta['settings'], right_meta['settings']),
        'environment_changes': _changes(left_meta.get('environment', {}), right_meta.get('environment', {})),
        'source_changes': _changes(left_meta.get('source_sha256', {}), right_meta.get('source_sha256', {})),
    }


def main():
    """Write a comparison report without opening Streamlit."""
    import argparse
    import json
    import zipfile
    from pathlib import Path

    parser = argparse.ArgumentParser(description='Compare two saved cascade runs; changes are candidate minus baseline.')
    parser.add_argument('baseline', type=Path, help='Baseline simulation ZIP')
    parser.add_argument('candidate', type=Path, help='Candidate simulation ZIP')
    parser.add_argument('--output', type=Path, required=True, help='New JSON report path')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new path')
    try:
        report = compare_run_bundles(args.baseline.read_bytes(), args.candidate.read_bytes())
        data = json.dumps(report, indent=2, allow_nan=False)
        with args.output.open('x') as output:
            output.write(data)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    if report['paired']:
        print('Paired comparison: matching portfolio and recorded market draws.')
    else:
        print('Unpaired comparison: summary changes do not isolate a settings effect.')
    print(f'Saved comparison to {args.output}')


if __name__ == '__main__':
    main()
