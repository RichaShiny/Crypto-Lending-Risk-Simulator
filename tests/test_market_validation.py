from unittest.mock import patch

import numpy as np
import pytest

from src.simulation import simulate_market_returns


@pytest.mark.parametrize('name,value', [
    ('n_simulations', 0), ('n_simulations', -1), ('n_simulations', True),
    ('n_simulations', 2.5), ('horizon_days', 0), ('horizon_days', -7),
    ('horizon_days', float('nan')), ('horizon_days', False),
    ('seed', -1), ('seed', True), ('seed', 1.5),
    ('distribution', 'unsupported'),
    ('degrees_of_freedom', 0), ('degrees_of_freedom', 2),
    ('degrees_of_freedom', 1.5), ('degrees_of_freedom', float('nan')),
    ('degrees_of_freedom', float('inf')), ('degrees_of_freedom', True),
])
def test_invalid_scalar_settings_fail_before_sampling(name, value):
    with patch('src.simulation.np.random.default_rng') as rng:
        with pytest.raises(ValueError):
            simulate_market_returns(**{name: value})
        rng.assert_not_called()


@pytest.mark.parametrize('value', [-0.1, float('nan'), float('inf'), True, '0.5'])
def test_invalid_volatility_identifies_asset(value):
    with pytest.raises(ValueError, match='volatility for ETH'):
        simulate_market_returns(annual_volatility={'ETH': value, 'BTC': 0.6, 'SOL': 1.0})


def test_missing_volatility_identifies_asset():
    with pytest.raises(ValueError, match='missing asset: SOL'):
        simulate_market_returns(annual_volatility={'ETH': 0.7, 'BTC': 0.6})


@pytest.mark.parametrize('matrix,message', [
    (np.eye(2), '3-by-3'),
    ([[1, 0], [0]], 'numeric'),
    ([[1, np.nan, 0], [np.nan, 1, 0], [0, 0, 1]], 'finite'),
    ([[1, 0.5, 0], [0.1, 1, 0], [0, 0, 1]], 'symmetric'),
    (np.eye(3) * 0.8, 'unit diagonal'),
    ([[1, 1.1, 0], [1.1, 1, 0], [0, 0, 1]], 'between -1 and 1'),
    ([[1, 0.9, 0.9], [0.9, 1, -0.9], [0.9, -0.9, 1]], 'positive semidefinite'),
])
def test_invalid_correlations_fail_before_sampling(matrix, message):
    with patch('src.simulation.np.random.default_rng') as rng:
        with pytest.raises(ValueError, match=message):
            simulate_market_returns(correlation_matrix=matrix)
        rng.assert_not_called()


def test_zero_volatility_and_singular_correlation_remain_supported():
    returns = simulate_market_returns(n_simulations=20, distribution='normal',
                                     annual_volatility={'ETH': 0, 'BTC': 0.5, 'SOL': 0.5},
                                     correlation_matrix=np.ones((3, 3)))
    np.testing.assert_array_equal(returns['ETH'], 0)
    np.testing.assert_allclose(returns['BTC'], returns['SOL'], atol=1e-8)
    assert np.isfinite(returns).all().all()


def test_numpy_integer_controls_and_fractional_student_t_df_are_supported():
    returns = simulate_market_returns(n_simulations=np.int64(10), horizon_days=np.int64(7),
                                     seed=np.int64(0), degrees_of_freedom=2.5)
    assert returns.shape == (10, 3)
    assert np.isfinite(returns).all().all()
