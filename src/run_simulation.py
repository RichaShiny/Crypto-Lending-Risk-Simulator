"""Run cascade Monte Carlo from saved JSON settings without opening a dashboard."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.cascade_simulation import run_cascade_aware_monte_carlo
from src.data_generator import generate_protocol_positions
from src.run_bundle import build_run_bundle


def main():
    parser = argparse.ArgumentParser(description='Create a cascade simulation ZIP from JSON settings.')
    parser.add_argument('--settings', required=True, type=Path, help='Engine keyword arguments as JSON; market_depth_usd is required')
    parser.add_argument('--output', required=True, type=Path, help='New ZIP path; existing files are never overwritten')
    portfolio = parser.add_mutually_exclusive_group()
    portfolio.add_argument('--positions', type=Path, help='Lending positions CSV using the exported positions.csv schema')
    portfolio.add_argument('--portfolio-size', type=int, help='Synthetic position count (default: 250)')
    parser.add_argument('--portfolio-seed', type=int, help='Synthetic portfolio seed (default: 42), separate from the market seed in settings')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new path')
    if args.positions and args.portfolio_seed is not None:
        parser.error('--portfolio-seed applies only to synthetic portfolios')
    if args.portfolio_size is not None and args.portfolio_size <= 0:
        parser.error('--portfolio-size must be positive')
    if args.portfolio_seed is not None and args.portfolio_seed < 0:
        parser.error('--portfolio-seed must be nonnegative')
    try:
        settings = json.loads(args.settings.read_text())
        if not isinstance(settings, dict) or 'positions' in settings:
            raise ValueError('Settings must be a JSON object of engine arguments, excluding positions')
        if settings.get('correlation_matrix') is not None:
            settings['correlation_matrix'] = np.asarray(settings['correlation_matrix'])
        positions = (pd.read_csv(args.positions, float_precision='round_trip') if args.positions else
                     generate_protocol_positions(n_positions=args.portfolio_size or 250,
                                                 seed=42 if args.portfolio_seed is None else args.portfolio_seed))
        results = run_cascade_aware_monte_carlo(positions=positions, **settings)
        bundle = build_run_bundle(positions, results, settings)
        with args.output.open('xb') as output:
            output.write(bundle)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(f'Saved {len(results)} scenarios and {len(positions)} positions to {args.output}')


if __name__ == '__main__':
    main()
