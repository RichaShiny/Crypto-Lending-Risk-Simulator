import plotly.express as px
import streamlit as st

from src.attribution_view import attribution_frames
from src.dashboard_cache import cached_attribution
from src.data_generator import generate_protocol_positions


st.set_page_config(
    page_title="Crypto Lending Risk Simulator · Tail Risk Attribution",
    page_icon="🧭",
    layout="wide",
)

st.title("Tail Risk Attribution")

st.write("Explore which collateral assets drive the worst modeled liquidation outcomes.")
method = st.radio(
    "How should asset contributions be measured?",
    ["Remove one asset's shock", "Split shared effects (Shapley)"],
    horizontal=True,
)
use_shapley = method == "Split shared effects (Shapley)"
contribution_label = "Allocated" if use_shapley else "Marginal"
if use_shapley:
    st.info(
        "Shapley attribution divides the change from a no-market-shock baseline across assets, "
        "averaging over every possible order of asset shocks. The contributions add up to "
        "that change, which can differ from total exposure if the baseline is already risky."
    )
else:
    st.info(
        "Each asset's shock is removed in turn while other shocks stay fixed. These marginal "
        "effects can overlap, so their sum need not equal total exposure."
    )

positions = generate_protocol_positions()

with st.sidebar:
    st.header("Simulation")

    n_simulations = st.select_slider(
        "Market draws",
        options=[10, 25, 50],
        value=25,
    )

    horizon_days = st.select_slider(
        "Horizon (days)",
        options=[7, 14, 30, 60, 90],
        value=30,
    )

    distribution_label = st.radio(
        "Return distribution",
        options=["Student-t", "Normal"],
    )
    distribution = (
        "student_t" if distribution_label == "Student-t" else "normal"
    )

    tail_percentile = st.select_slider(
        "Tail cohort",
        options=[75, 90, 95],
        value=95,
        format_func=lambda value: f"Top {100 - value}% risk tail (P{value}+)",
    )

    st.header("Market depth")

    eth_depth_m = st.slider(
        "ETH depth ($M)",
        min_value=5,
        max_value=200,
        value=50,
        step=5,
    )
    btc_depth_m = st.slider(
        "BTC depth ($M)",
        min_value=5,
        max_value=250,
        value=75,
        step=5,
    )
    sol_depth_m = st.slider(
        "SOL depth ($M)",
        min_value=2,
        max_value=100,
        value=20,
        step=2,
    )

    st.header("Liquidation mechanics")

    close_factor = st.slider(
        "Close factor",
        min_value=0.10,
        max_value=1.00,
        value=0.50,
        step=0.05,
    )
    liquidation_bonus = st.slider(
        "Liquidation bonus",
        min_value=0.00,
        max_value=0.20,
        value=0.05,
        step=0.01,
        format="%.2f",
    )
    price_impact_factor = st.slider(
        "Price-impact strength",
        min_value=0.0,
        max_value=3.0,
        value=1.0,
        step=0.1,
    )

market_depth = {
    "ETH": eth_depth_m * 1_000_000.0,
    "BTC": btc_depth_m * 1_000_000.0,
    "SOL": sol_depth_m * 1_000_000.0,
}

with st.spinner("Calculating asset contributions..."):
    result = cached_attribution(
        positions=positions,
        use_shapley=use_shapley,
        market_depth_usd=market_depth,
        n_simulations=n_simulations,
        horizon_days=horizon_days,
        seed=42,
        distribution=distribution,
        tail_quantile=tail_percentile / 100,
        close_factor=close_factor,
        liquidation_bonus=liquidation_bonus,
        price_impact_factor=price_impact_factor,
    )

summary, attribution_results = attribution_frames(result, use_shapley)
summary['attribution_method'] = 'exact_shapley' if use_shapley else 'leave_one_out'
attribution_results['attribution_method'] = summary['attribution_method'].iloc[0]
summary["mean_contribution_pct"] = (
    summary["mean_cascade_exposure_contribution"] * 100
)
summary["tail_contribution_pct"] = (
    summary["tail_mean_cascade_exposure_contribution"] * 100
)
summary["tail_bad_debt_contribution_pct"] = (
    summary["tail_mean_bad_debt_contribution"] * 100
)
summary["positive_contribution_probability_pct"] = (
    summary["probability_positive_exposure_contribution"] * 100
)

scenario_results = result.scenario_results
full_tail_cutoff = scenario_results["cascade_debt_share"].quantile(
    tail_percentile / 100
)

leader = summary.iloc[0]
mean_exposure = scenario_results["cascade_debt_share"].mean()
p95_exposure = scenario_results["cascade_debt_share"].quantile(0.95)
mean_bad_debt = scenario_results["bad_debt_share"].mean()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Largest tail contributor", leader["asset"])
col2.metric("Mean cascade exposure", f"{mean_exposure:.1%}")
col3.metric("P95 cascade exposure", f"{p95_exposure:.1%}")
col4.metric("Mean bad debt", f"{mean_bad_debt:.1%}")

st.caption(
    f"{n_simulations} paired draws · {horizon_days}-day horizon · "
    f"{distribution_label} returns · P{tail_percentile}+ tail cohort begins at "
    f"{full_tail_cutoff:.1%} cascade exposure"
)

st.subheader("Asset Contribution to Cascade Exposure")

contribution_chart = px.bar(
    summary,
    x="asset",
    y=["mean_contribution_pct", "tail_contribution_pct"],
    barmode="group",
    labels={
        "asset": "Collateral Asset",
        "value": f"{contribution_label} Cascade Exposure Contribution (percentage points)",
        "variable": "Contribution Window",
    },
    title=f"Average vs Tail-Conditioned {contribution_label} Contribution",
)

st.plotly_chart(contribution_chart, width="stretch")

st.subheader("Tail Bad-Debt Contribution")

bad_debt_chart = px.bar(
    summary,
    x="asset",
    y="tail_bad_debt_contribution_pct",
    labels={
        "asset": "Collateral Asset",
        "tail_bad_debt_contribution_pct": (
            "Tail Mean Bad-Debt Contribution (percentage points)"
        ),
    },
    title=f"{contribution_label} Contribution in the Bad-Debt Tail",
)

st.plotly_chart(bad_debt_chart, width="stretch")

st.subheader("Attribution Summary")

display = summary[
    [
        "asset",
        "mean_contribution_pct",
        "tail_contribution_pct",
        "p95_cascade_exposure_contribution",
        "positive_contribution_probability_pct",
        "tail_bad_debt_contribution_pct",
        "mean_secondary_liquidation_contribution",
        "mean_endogenous_price_decline_contribution",
    ]
].copy()

display["p95_cascade_exposure_contribution"] *= 100
display["mean_endogenous_price_decline_contribution"] *= 100

display = display.rename(
    columns={
        "asset": "Asset",
        "mean_contribution_pct": "Mean exposure contribution (pts)",
        "tail_contribution_pct": "Tail mean exposure contribution (pts)",
        "p95_cascade_exposure_contribution": "P95 exposure contribution (pts)",
        "positive_contribution_probability_pct": "P(positive contribution) (%)",
        "tail_bad_debt_contribution_pct": "Tail mean bad-debt contribution (pts)",
        "mean_secondary_liquidation_contribution": "Mean secondary liquidation contribution",
        "mean_endogenous_price_decline_contribution": "Mean price-decline contribution (pts)",
    }
)

st.dataframe(display, width="stretch", hide_index=True)

st.subheader("Scenario-Level Attribution")

asset_choice = st.selectbox(
    "Inspect one collateral asset",
    options=summary["asset"].tolist(),
)

asset_rows = attribution_results.loc[
    attribution_results["asset"] == asset_choice
].copy()
asset_rows["cascade_exposure_contribution_pct"] = (
    asset_rows["contribution_cascade_debt_share"] * 100
)
asset_rows["bad_debt_contribution_pct"] = (
    asset_rows["contribution_bad_debt_share"] * 100
)

scenario_chart = px.scatter(
    asset_rows,
    x="asset_shock",
    y="cascade_exposure_contribution_pct",
    size=asset_rows["contribution_cascade_created_positions"].abs() + 1,
    labels={
        "asset_shock": f"{asset_choice} Simulated Return",
        "cascade_exposure_contribution_pct": (
            f"{contribution_label} Cascade Exposure Contribution (pts)"
        ),
    },
    title=f"{asset_choice} Shock vs {contribution_label} Cascade Contribution",
)

st.plotly_chart(scenario_chart, width="stretch")

st.write(
    "A negative allocated contribution means that the asset's shock reduced risk on average "
    "across the evaluated coalition orders. Positive market returns or cascade interactions "
    "can produce this result."
    if use_shapley else
    "A negative marginal contribution means that removing the asset's return made the "
    "paired outcome worse. Positive market returns or cascade interactions can produce this result."
)

if use_shapley:
    reconciliation = scenario_results["shapley_efficiency_error_cascade_debt_share"].abs().max()
    st.caption(f"Largest allocation reconciliation gap: {reconciliation * 100:.10f} percentage points.")

st.download_button("Download asset contribution summary", summary.to_csv(index=False),
                   file_name="asset_contributions.csv", mime="text/csv")
st.download_button("Download scenario-level contributions", attribution_results.to_csv(index=False),
                   file_name="scenario_contributions.csv", mime="text/csv")
