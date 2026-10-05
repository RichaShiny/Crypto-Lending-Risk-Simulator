import pytest

from src.attribution_view import attribution_frames
from src.data_generator import generate_protocol_positions
from src.shapley_attribution import run_shapley_tail_risk_attribution
from src.tail_risk_attribution import run_tail_risk_attribution

DEPTH = {'ETH': 50_000_000., 'BTC': 75_000_000., 'SOL': 20_000_000.}


@pytest.mark.parametrize('shapley', [False, True])
def test_both_methods_supply_dashboard_columns_without_changing_results(shapley):
    positions = generate_protocol_positions(n_positions=20, seed=42)
    runner = run_shapley_tail_risk_attribution if shapley else run_tail_risk_attribution
    result = runner(positions=positions, market_depth_usd=DEPTH, n_simulations=2)
    original = result.asset_summary.copy(deep=True)
    summary, scenarios = attribution_frames(result, shapley)
    assert {'mean_cascade_exposure_contribution', 'p95_cascade_exposure_contribution',
            'tail_mean_cascade_exposure_contribution', 'tail_mean_bad_debt_contribution',
            'probability_positive_exposure_contribution', 'mean_secondary_liquidation_contribution',
            'mean_endogenous_price_decline_contribution'} <= set(summary.columns)
    assert {'asset', 'asset_shock', 'contribution_cascade_debt_share',
            'contribution_bad_debt_share', 'contribution_cascade_created_positions'} <= set(scenarios.columns)
    if shapley:
        assert summary['tail_mean_cascade_exposure_contribution'].tolist() == result.asset_summary['tail_mean_shapley_cascade_exposure'].tolist()
    summary.iloc[0, 0] = 'changed'
    assert result.asset_summary.equals(original)
