from numbers import Integral, Real

import numpy as np
import pandas as pd

from src.stress_engine import run_asset_specific_stress_test


ASSETS = ["ETH", "BTC", "SOL"]

ANNUAL_VOLATILITY = {
    "ETH": 0.75,
    "BTC": 0.60,
    "SOL": 1.00,
}

CORRELATION_MATRIX = np.array(
    [
        [1.00, 0.75, 0.65],
        [0.75, 1.00, 0.55],
        [0.65, 0.55, 1.00],
    ]
)


def simulate_market_returns(
    n_simulations: int = 1000,
    horizon_days: int = 30,
    seed: int = 42,
    distribution: str = "student_t",
    degrees_of_freedom: int = 5,
    annual_volatility: dict[str, float] | None = None,
    correlation_matrix: np.ndarray | None = None,
) -> pd.DataFrame:
    """
    Simulate correlated crypto returns.

    Supported distributions:
        - "normal"
        - "student_t" (finite degrees of freedom greater than two)

    Volatility must be finite and nonnegative for every asset. Correlation
    matrices use ETH/BTC/SOL order and must be valid positive semidefinite
    correlation matrices. Invalid settings raise ValueError before sampling.
    """
    for name, value in (("n_simulations", n_simulations), ("horizon_days", horizon_days)):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if distribution not in ("normal", "student_t"):
        raise ValueError("distribution must be 'normal' or 'student_t'")
    if distribution == "student_t" and (
        isinstance(degrees_of_freedom, (bool, np.bool_))
        or not isinstance(degrees_of_freedom, Real)
        or not np.isfinite(degrees_of_freedom)
        or degrees_of_freedom <= 2
    ):
        raise ValueError("Student-t degrees_of_freedom must be finite and greater than 2")

    if annual_volatility is None:
        annual_volatility = ANNUAL_VOLATILITY

    if correlation_matrix is None:
        correlation_matrix = CORRELATION_MATRIX

    for asset in ASSETS:
        if asset not in annual_volatility:
            raise ValueError(f"annual_volatility is missing asset: {asset}")
        value = annual_volatility[asset]
        if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
                or not np.isfinite(value) or value < 0):
            raise ValueError(f"annual volatility for {asset} must be nonnegative and finite")

    try:
        correlation_matrix = np.asarray(correlation_matrix, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("correlation_matrix must be a numeric 3-by-3 matrix") from error
    if correlation_matrix.shape != (len(ASSETS), len(ASSETS)):
        raise ValueError("correlation_matrix must be a 3-by-3 matrix in ETH, BTC, SOL order")
    if not np.isfinite(correlation_matrix).all():
        raise ValueError("correlation_matrix must contain finite values")
    if not np.allclose(correlation_matrix, correlation_matrix.T, rtol=0, atol=1e-10):
        raise ValueError("correlation_matrix must be symmetric")
    if not np.allclose(np.diag(correlation_matrix), 1, rtol=0, atol=1e-10):
        raise ValueError("correlation_matrix must have a unit diagonal")
    if np.any(np.abs(correlation_matrix) > 1):
        raise ValueError("correlation_matrix entries must be between -1 and 1")
    if np.linalg.eigvalsh(correlation_matrix).min() < -1e-10:
        raise ValueError("correlation_matrix must be positive semidefinite")

    rng = np.random.default_rng(seed)

    time_fraction = horizon_days / 365

    vol_vector = np.array(
        [
            annual_volatility[asset]
            for asset in ASSETS
        ]
    )

    horizon_vol = (
        vol_vector * np.sqrt(time_fraction)
    )

    covariance_matrix = (
        np.outer(
            horizon_vol,
            horizon_vol,
        )
        * correlation_matrix
    )

    normal_draws = rng.multivariate_normal(
        mean=np.zeros(len(ASSETS)),
        cov=covariance_matrix,
        size=n_simulations,
    )

    if distribution == "normal":
        simulated_returns = normal_draws

    elif distribution == "student_t":
        chi_square_draws = rng.chisquare(
            degrees_of_freedom,
            size=n_simulations,
        )

        scaling = np.sqrt(
            (degrees_of_freedom - 2)
            / chi_square_draws
        )

        simulated_returns = (
            normal_draws
            * scaling[:, None]
        )

    else:
        raise ValueError(
            "distribution must be 'normal' or 'student_t'"
        )

    simulated_returns = np.clip(
        simulated_returns,
        -0.99,
        None,
    )

    return pd.DataFrame(
        simulated_returns,
        columns=ASSETS,
    )


def run_monte_carlo_simulation(
    positions: pd.DataFrame,
    n_simulations: int = 1000,
    horizon_days: int = 30,
    seed: int = 42,
    distribution: str = "student_t",
    annual_volatility: dict[str, float] | None = None,
    correlation_matrix: np.ndarray | None = None,
) -> pd.DataFrame:
    """
    Simulate market outcomes and measure liquidation exposure
    for the protocol under each scenario.
    """
    market_returns = simulate_market_returns(
        n_simulations=n_simulations,
        horizon_days=horizon_days,
        seed=seed,
        distribution=distribution,
        annual_volatility=annual_volatility,
        correlation_matrix=correlation_matrix,
    )

    total_debt = positions["debt_usd"].sum()

    results = []

    for simulation_id, row in market_returns.iterrows():
        shocks = {
            asset: max(row[asset], -0.99)
            for asset in ASSETS
        }

        stressed = run_asset_specific_stress_test(
            positions,
            shocks,
        )

        liquidatable = stressed[
            stressed["liquidatable"]
        ]

        liquidatable_debt = (
            liquidatable["debt_usd"].sum()
        )

        results.append(
            {
                "simulation_id": simulation_id,
                "eth_return": shocks["ETH"],
                "btc_return": shocks["BTC"],
                "sol_return": shocks["SOL"],
                "liquidatable_positions": len(
                    liquidatable
                ),
                "liquidatable_debt": (
                    liquidatable_debt
                ),
                "liquidatable_debt_share": (
                    liquidatable_debt
                    / total_debt
                ),
            }
        )

    return pd.DataFrame(results)


def run_threshold_sensitivity(
    positions: pd.DataFrame,
    threshold_adjustments: list[float],
    market_shock: float = -0.20,
) -> pd.DataFrame:
    """
    Measure how changes to liquidation thresholds affect
    protocol liquidation exposure under a fixed market shock.
    """
    results = []

    total_debt = positions["debt_usd"].sum()

    for adjustment in threshold_adjustments:
        adjusted_positions = positions.copy()

        adjusted_positions[
            "liquidation_threshold"
        ] = (
            adjusted_positions[
                "liquidation_threshold"
            ]
            + adjustment
        ).clip(
            lower=0.10,
            upper=0.95,
        )

        stressed = run_asset_specific_stress_test(
            adjusted_positions,
            {
                "ETH": market_shock,
                "BTC": market_shock,
                "SOL": market_shock,
            },
        )

        liquidatable = stressed[
            stressed["liquidatable"]
        ]

        liquidatable_debt = (
            liquidatable["debt_usd"].sum()
        )

        results.append(
            {
                "threshold_adjustment": (
                    adjustment
                ),
                "liquidatable_positions": len(
                    liquidatable
                ),
                "liquidation_rate": (
                    len(liquidatable)
                    / len(positions)
                ),
                "liquidatable_debt": (
                    liquidatable_debt
                ),
                "liquidatable_debt_share": (
                    liquidatable_debt
                    / total_debt
                ),
            }
        )

    return pd.DataFrame(results)