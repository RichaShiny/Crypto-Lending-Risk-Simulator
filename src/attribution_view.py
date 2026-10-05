"""Common presentation columns for the two attribution methods."""


def attribution_frames(result, shapley=False):
    if not shapley:
        return result.asset_summary.copy(), result.attribution_results.copy()
    summary_columns = {
        'mean_shapley_cascade_exposure': 'mean_cascade_exposure_contribution',
        'p95_shapley_cascade_exposure': 'p95_cascade_exposure_contribution',
        'tail_mean_shapley_cascade_exposure': 'tail_mean_cascade_exposure_contribution',
        'probability_positive_shapley_exposure': 'probability_positive_exposure_contribution',
        'tail_mean_shapley_bad_debt': 'tail_mean_bad_debt_contribution',
        'mean_shapley_secondary_liquidations': 'mean_secondary_liquidation_contribution',
        'mean_shapley_endogenous_price_decline': 'mean_endogenous_price_decline_contribution',
    }
    scenario_columns = {column: column.replace('shapley_', 'contribution_', 1)
                        for column in result.shapley_results.columns if column.startswith('shapley_')}
    return (result.asset_summary.rename(columns=summary_columns).copy(),
            result.shapley_results.rename(columns=scenario_columns).copy())
