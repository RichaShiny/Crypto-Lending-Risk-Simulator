import pandas as pd
import pytest

from src.data_generator import generate_protocol_positions
from src.liquidation_cascade import run_liquidation_cascade


def fragile_eth_positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "position_id": [1, 2, 3],
            "asset": ["ETH", "ETH", "ETH"],
            "collateral_amount": [1.0, 1.0, 1.0],
            "collateral_price": [100.0, 100.0, 100.0],
            "collateral_value": [100.0, 100.0, 100.0],
            "debt_usd": [80.0, 72.0, 55.0],
            "liquidation_threshold": [0.80, 0.80, 0.80],
            "ltv": [0.80, 0.72, 0.55],
            "health_factor": [1.00, 1.0 / 0.90, 0.80 / 0.55],
        }
    )


def test_healthy_protocol_has_no_liquidation_rounds():
    positions = pd.DataFrame(
        {
            "position_id": [1, 2],
            "asset": ["ETH", "BTC"],
            "collateral_amount": [1.0, 1.0],
            "collateral_price": [100.0, 200.0],
            "debt_usd": [40.0, 80.0],
            "liquidation_threshold": [0.80, 0.75],
        }
    )

    result = run_liquidation_cascade(
        positions=positions,
        initial_shocks={"ETH": 0.0, "BTC": 0.0},
        market_depth_usd={"ETH": 100_000.0, "BTC": 100_000.0},
    )

    assert result.summary["rounds_executed"] == 0
    assert result.summary["initial_liquidatable_positions"] == 0
    assert result.summary["cascade_liquidated_positions"] == 0
    assert result.summary["debt_repaid_usd"] == pytest.approx(0.0)
    assert result.round_history.empty


def test_low_market_depth_can_create_endogenous_cascade():
    positions = fragile_eth_positions()

    deep_market = run_liquidation_cascade(
        positions=positions,
        initial_shocks={"ETH": -0.05},
        market_depth_usd={"ETH": 1_000_000_000.0},
        max_rounds=6,
    )

    shallow_market = run_liquidation_cascade(
        positions=positions,
        initial_shocks={"ETH": -0.05},
        market_depth_usd={"ETH": 100.0},
        max_rounds=6,
    )

    deep_price = deep_market.asset_summary.loc[0, "final_price"]
    shallow_price = shallow_market.asset_summary.loc[0, "final_price"]

    assert deep_market.summary["initial_liquidatable_positions"] == 1
    assert deep_market.summary["cascade_liquidated_positions"] == 0
    assert shallow_market.summary["cascade_liquidated_positions"] >= 1
    assert shallow_price < deep_price


def test_zero_price_impact_preserves_exogenous_shocked_price():
    result = run_liquidation_cascade(
        positions=fragile_eth_positions(),
        initial_shocks={"ETH": -0.05},
        market_depth_usd={"ETH": 100.0},
        price_impact_factor=0.0,
        max_rounds=6,
    )

    asset = result.asset_summary.iloc[0]

    assert asset["shocked_price"] == pytest.approx(95.0)
    assert asset["final_price"] == pytest.approx(95.0)
    assert asset["endogenous_price_impact_pct"] == pytest.approx(0.0)
    assert result.summary["cascade_liquidated_positions"] == 0


def test_cascade_outputs_are_deterministic():
    positions = generate_protocol_positions(
        n_positions=120,
        seed=7,
    )
    kwargs = {
        "positions": positions,
        "initial_shocks": {
            "ETH": -0.20,
            "BTC": -0.15,
            "SOL": -0.30,
        },
        "market_depth_usd": {
            "ETH": 20_000_000.0,
            "BTC": 30_000_000.0,
            "SOL": 8_000_000.0,
        },
        "max_rounds": 10,
    }

    first = run_liquidation_cascade(**kwargs)
    second = run_liquidation_cascade(**kwargs)

    pd.testing.assert_frame_equal(
        first.final_positions,
        second.final_positions,
    )
    pd.testing.assert_frame_equal(
        first.round_history,
        second.round_history,
    )
    pd.testing.assert_frame_equal(
        first.asset_summary,
        second.asset_summary,
    )
    assert first.summary == second.summary


def test_liquidation_accounting_remains_non_negative_and_reconciles():
    positions = generate_protocol_positions(
        n_positions=150,
        seed=11,
    )

    result = run_liquidation_cascade(
        positions=positions,
        initial_shocks={
            "ETH": -0.30,
            "BTC": -0.25,
            "SOL": -0.40,
        },
        market_depth_usd={
            "ETH": 8_000_000.0,
            "BTC": 12_000_000.0,
            "SOL": 3_000_000.0,
        },
        max_rounds=12,
    )

    final_positions = result.final_positions

    assert (final_positions["debt_usd"] >= 0).all()
    assert (final_positions["collateral_amount"] >= 0).all()
    assert (final_positions["bad_debt_usd"] >= 0).all()

    initial_debt = final_positions["initial_debt_usd"].sum()
    remaining_debt = final_positions["debt_usd"].sum()

    assert result.summary["debt_repaid_usd"] == pytest.approx(
        initial_debt - remaining_debt
    )
    assert result.summary["remaining_debt_usd"] == pytest.approx(
        remaining_debt
    )


def test_missing_market_depth_is_rejected():
    positions = pd.DataFrame(
        {
            "position_id": [1],
            "asset": ["ETH"],
            "collateral_amount": [1.0],
            "collateral_price": [100.0],
            "debt_usd": [70.0],
            "liquidation_threshold": [0.80],
        }
    )

    with pytest.raises(ValueError, match="market_depth_usd"):
        run_liquidation_cascade(
            positions=positions,
            initial_shocks={"ETH": -0.10},
            market_depth_usd={},
        )


@pytest.mark.parametrize('column', ['collateral_amount', 'collateral_price', 'debt_usd', 'liquidation_threshold'])
@pytest.mark.parametrize('value', [float('inf'), float('-inf'), float('nan')])
def test_nonfinite_portfolio_values_are_rejected_before_state_calculation(column, value):
    from unittest.mock import patch

    positions = fragile_eth_positions()
    positions[column] = value
    with patch('src.liquidation_cascade._recalculate_state') as recalculate:
        with pytest.raises(ValueError, match=f'{column} must contain only finite numeric values'):
            run_liquidation_cascade(positions, {'ETH': -0.2}, {'ETH': 100_000.0})
        recalculate.assert_not_called()


def test_numeric_strings_are_normalized_without_mutating_caller_portfolio():
    numeric = fragile_eth_positions()
    strings = numeric.copy(deep=True)
    for column in ('collateral_amount', 'collateral_price', 'debt_usd', 'liquidation_threshold'):
        strings[column] = strings[column].astype(str)
    original = strings.copy(deep=True)
    expected = run_liquidation_cascade(numeric, {'ETH': -0.2}, {'ETH': 100_000.0})
    actual = run_liquidation_cascade(strings, {'ETH': -0.2}, {'ETH': 100_000.0})
    assert actual.summary == expected.summary
    pd.testing.assert_frame_equal(actual.final_positions, expected.final_positions)
    pd.testing.assert_frame_equal(strings, original)
