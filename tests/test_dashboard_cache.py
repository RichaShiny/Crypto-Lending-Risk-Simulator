from unittest.mock import patch

import pandas as pd

from src.dashboard_cache import cached_attribution


def test_cache_reuses_runs_but_separates_settings_method_and_portfolio():
    cached_attribution.clear()
    positions = pd.DataFrame({'debt_usd': [100.0]})
    with patch('src.dashboard_cache.run_tail_risk_attribution', return_value={'values': [1]}) as marginal, patch('src.dashboard_cache.run_shapley_tail_risk_attribution', return_value={'values': [2]}) as shapley:
        first = cached_attribution(positions, seed=42)
        first['values'][0] = 999
        assert cached_attribution(positions.copy(), seed=42) == {'values': [1]}
        assert marginal.call_count == 1
        cached_attribution(positions, seed=43)
        assert marginal.call_count == 2
        cached_attribution(positions, use_shapley=True, seed=42)
        assert shapley.call_count == 1
        cached_attribution(pd.DataFrame({'debt_usd': [200.0]}), seed=42)
        assert marginal.call_count == 3
    cached_attribution.clear()
