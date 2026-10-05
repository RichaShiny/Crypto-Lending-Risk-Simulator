# Crypto Lending Risk Simulator

Simulate how falling crypto prices trigger loan liquidations, spread through a lending protocol, and create unpaid debt. Compare market shocks, liquidity assumptions, and the assets driving the worst modeled outcomes.

## Why I Built This

A lending position can look healthy under current market conditions while becoming vulnerable after relatively small changes in collateral prices.

That led to a broader question:

> How can we move from evaluating individual lending positions to measuring protocol-level risk under deterministic and stochastic market stress?

Crypto Lending Risk Simulator explores that question through position-level risk modeling, deterministic stress testing, asset-specific scenarios, endogenous liquidation-cascade simulation, cascade-aware Monte Carlo analysis, reverse stress testing, paired tail-risk attribution, historical market calibration, tail-risk evaluation, and parameter sensitivity.

## Questions I Wanted to Answer

Rather than starting with a dashboard, I built the project around a sequence of risk questions:

1. When does an individual lending position become liquidatable?

2. How quickly does protocol exposure increase as markets decline?

3. Which collateral assets contribute most to liquidation exposure?

4. What happens when ETH, BTC, and SOL experience different shocks instead of moving identically?

5. What happens after liquidation starts if seized collateral is sold into finite market depth?

6. Can those sales create additional price pressure and push previously healthy positions into liquidation?

7. Deterministic scenarios tell us what happens under a chosen crash, but what is the distribution of possible outcomes?

8. Across the same simulated market draws, how much does endogenous liquidation feedback amplify exposure and bad debt relative to first-order stress alone?

9. Which collateral assets contribute most to the worst cascade outcomes, and do their marginal effects become larger in the tail?

10. How often do severe outcomes occur in the tail of that distribution?

11. Instead of choosing a crash first, what is the smallest modeled market decline that causes a chosen protocol-risk threshold to fail?

12. How sensitive are those results to assumptions about liquidation thresholds and market depth?

13. How much do simulation results change when volatility and cross-asset correlations are calibrated from historical market data rather than assumed?

These questions drove the architecture of Crypto Lending Risk Simulator.

## Evaluation Flow

Position Data
↓
Position-Level Risk Metrics
↓
Deterministic Market Stress
↓
Protocol Liquidation Exposure
↓
Asset-Specific Stress Testing
↓
Endogenous Liquidation Cascade
↓
Market-Depth Price Impact
↓
Secondary Liquidations + Bad Debt
↓
Correlated Monte Carlo Market Draws
↓
Paired First-Order vs Cascade-Aware Evaluation
↓
Tail Amplification + Bad-Debt Distribution
↓
Paired Leave-One-Asset-Out Tail Attribution
↓
Reverse Stress Threshold Solver
↓
Historical Volatility + Correlation Calibration
↓
Parameter Sensitivity
↓
Validation and Automated Tests

Each stage answers a different question rather than simply adding another visualization.

## Methodology

### 1. Position-Level Risk

Each lending position contains collateral value, debt, and a liquidation threshold.

Crypto Lending Risk Simulator derives metrics including:

- Loan-to-value ratio
- Health factor
- Liquidation price
- Distance to liquidation
- Risk status

This establishes the position-level mechanics used throughout the rest of the system.

### 2. Deterministic Stress Testing

The stress engine applies controlled collateral-price declines and recalculates position health.

A protocol shock ladder evaluates increasingly severe market declines and measures:

- Liquidatable positions
- Liquidation rate
- Liquidatable debt
- Share of protocol debt exposed to liquidation

This answers:

> How does protocol risk evolve as market conditions deteriorate?

### 3. Asset-Specific Scenarios

A single protocol-wide shock assumes every collateral asset moves identically.

Crypto Lending Risk Simulator therefore supports independent ETH, BTC, and SOL shocks.

This allows scenarios such as:

- ETH: -25%
- BTC: -15%
- SOL: -40%

The resulting exposure can then be decomposed by collateral asset.

### 4. Endogenous Liquidation Cascades

First-order stress testing identifies positions that are liquidatable immediately after a market shock. It does not capture the feedback created by liquidation execution itself.

Crypto Lending Risk Simulator therefore includes an iterative liquidation-cascade engine. Each round:

1. identifies positions with health factor below one,
2. repays debt up to a configurable close factor,
3. seizes collateral including a configurable liquidation bonus,
4. treats the seized collateral as sell pressure,
5. converts that sell pressure into additional price impact using asset-specific market depth,
6. recalculates every position at the new prices, and
7. repeats until the cascade stabilizes or the configured round limit is reached.

The price-impact model is deliberately transparent:

```text
next_price = current_price × exp(-impact_factor × collateral_sold_usd / market_depth_usd)
```

This makes it possible to separate:

- positions liquidatable from the initial exogenous shock,
- positions that become liquidatable only because of endogenous liquidation pressure,
- debt repaid through liquidation,
- collateral sold by asset and round,
- additional price impact caused by the cascade,
- remaining liquidatable positions, and
- residual bad debt when debt exceeds remaining collateral value.

The cascade module is a stress-testing abstraction, not a prediction of realized exchange execution, MEV behavior, liquidator competition, or protocol-specific transaction ordering.

### 5. Cascade-Aware Monte Carlo Risk Simulation

Deterministic scenarios answer "what if this happens?"

Monte Carlo simulation asks:

> What range of outcomes could occur, and how frequently do severe outcomes appear?

Crypto Lending Risk Simulator simulates correlated ETH, BTC, and SOL market returns using either Normal or Student-t return assumptions.

Each simulated market state is evaluated twice using the exact same return draw:

1. **First-order stress:** positions are marked liquidatable immediately after the exogenous ETH/BTC/SOL move.
2. **Cascade-aware stress:** the same move is passed through the liquidation-cascade engine so liquidation sales can create endogenous price impact, secondary liquidations, and bad debt.

Because the two evaluations are paired on the same market draw, Crypto Lending Risk Simulator can measure modeled cascade amplification directly rather than comparing unrelated random scenarios.

For each simulation it records:

- first-order liquidatable debt share,
- cascade-exposed debt share,
- additional debt exposure created by the cascade,
- relative amplification versus first-order exposure,
- positions made liquidatable only by feedback,
- liquidation rounds executed,
- endogenous price decline, and
- residual bad debt.

### 6. Reverse Stress Testing

Forward stress testing starts with a chosen market move and measures the resulting loss or exposure.

Reverse stress testing starts with a failure threshold and asks:

> What is the smallest modeled market decline that causes this threshold to be breached?

Crypto Lending Risk Simulator solves that problem with a bracketed search and bisection over the same protocol and cascade mechanics used elsewhere in the project. Supported targets include:

- first-order liquidatable debt share,
- cascade-aware debt exposure,
- additional exposure created by cascade amplification, and
- bad-debt share.

Optional asset stress weights allow asymmetric scenarios. For example, a common base decline can be scaled so SOL falls more than ETH while BTC falls less.

For each solved target the engine reports the smallest tested breach, the largest tested safe shock immediately below it, the realized asset-specific shock vector, cascade-created positions, and bad debt at the breach point.

The solver also builds a reverse-stress frontier across multiple risk thresholds. This makes it possible to compare how quickly increasingly severe protocol states are reached under different liquidity and liquidation assumptions.

Reverse-stress thresholds are model-based breakpoints, not forecasts of future market moves or recommendations for protocol parameters.

### 7. Tail-Risk Attribution

Portfolio-level tail metrics show how severe the worst simulated outcomes become, but they do not explain which collateral asset is driving those outcomes.

Crypto Lending Risk Simulator therefore includes a paired leave-one-asset-out attribution layer. For each simulated ETH/BTC/SOL market draw:

1. the full scenario is evaluated through the cascade engine,
2. the exact same scenario is re-run with one asset's exogenous return set to zero,
3. all other shocks, protocol positions, market-depth assumptions, and liquidation mechanics remain unchanged, and
4. the difference between the full and muted scenarios is recorded as that asset's marginal counterfactual contribution.

The attribution tracks marginal effects on:

- cascade-exposed debt share,
- first-order exposure,
- cascade amplification,
- bad-debt share,
- secondary liquidations, and
- endogenous price decline.

Crypto Lending Risk Simulator reports both unconditional average contribution and tail-conditioned contribution for the worst cascade-exposure and bad-debt cohorts. This makes it possible for an asset to appear modest on average while still being an important driver of severe outcomes.

These leave-one-asset-out effects are not an additive decomposition. Liquidation cascades are nonlinear and assets interact through correlated shocks and protocol state, so ETH, BTC, and SOL marginal contributions can overlap and are not expected to sum exactly to total risk.

### 8. Historical Calibration

Rather than relying exclusively on assumed market parameters, Crypto Lending Risk Simulator can estimate volatility and cross-asset dependence from historical ETH, BTC, and SOL prices.

The current calibration snapshot uses historical data beginning in January 2022.

Estimated annualized volatility:

| Asset | Volatility |
| --- | ---: |
| ETH | 69.1% |
| BTC | 51.0% |
| SOL | 94.3% |

Estimated return correlations:

| | ETH | BTC | SOL |
| --- | ---: | ---: |
| ETH | 1.000 | 0.847 | 0.755 |
| BTC | 0.847 | 1.000 | 0.753 |
| SOL | 0.755 | 0.753 | 1.000 |

The calibrated correlation matrix was also checked for positive semidefiniteness before being used in simulation.

### 9. Tail-Risk Evaluation

Mean exposure alone can hide severe but less frequent outcomes.

Crypto Lending Risk Simulator therefore evaluates first-order and cascade-aware tails separately, including:

- Median exposure
- 90th, 95th, and 99th percentile cascade exposure
- P(Exposure > 25%)
- P(Exposure > 50%)
- P(Exposure > 75%)
- Probability that endogenous feedback increases exposure
- 95th and 99th percentile tail amplification
- Mean and 95th/99th percentile bad-debt share
- Endogenous price-impact tails

This makes it possible to see not only whether a market draw is severe, but whether liquidation feedback makes the severe tail materially worse under the chosen stress assumptions.

### 10. Parameter Sensitivity

Risk estimates depend on model and protocol assumptions.

Crypto Lending Risk Simulator therefore performs counterfactual liquidation-threshold sensitivity analysis under a fixed market shock.

The liquidation-cascade lab exposes market depth, close factor, liquidation bonus, price-impact strength, and maximum cascade rounds so the effect of execution assumptions can be inspected directly.

The cascade-aware Monte Carlo layer also supports paired market-depth sensitivity. The same simulated market draws are re-evaluated under multiple liquidity-depth multipliers, making it possible to isolate how shallow versus deep markets change cascade amplification and tail risk.

The reverse-stress solver can use the same market-depth and liquidation assumptions, so the critical shock itself can be compared across alternative liquidity regimes.

These are sensitivity analyses, not parameter optimization or recommendations for protocol settings.

## Validation

The project includes automated tests covering:

- Position-level risk calculations
- Price-shock behavior
- Zero-shock invariance
- Monotonic liquidation exposure under increasingly severe shocks
- Asset-specific shock isolation
- Monte Carlo output dimensions
- Simulation reproducibility
- Horizon-dependent dispersion
- Exposure bounds
- Historical return construction
- Calibration output
- Correlation symmetry
- Unit correlation diagonal
- Non-negative volatility
- No-cascade behavior for healthy positions
- Secondary liquidations under shallow market depth
- Zero endogenous price-impact invariance
- Cascade reproducibility
- Non-negative debt, collateral, and bad-debt accounting
- Debt-repayment reconciliation
- Cascade input validation
- Cascade-aware Monte Carlo reproducibility
- Paired first-order/cascade exposure ordering
- First-order parity when endogenous price impact is disabled
- Tail-metric bounds and percentile ordering
- Market-depth sensitivity under identical stochastic draws
- Reverse-stress breach and safe-bracket correctness
- Monotonic critical shocks across increasing risk thresholds
- First-order/cascade threshold parity when endogenous price impact is disabled
- Reverse-stress market-depth sensitivity
- Asset-specific stress-weight behavior
- Tail-risk attribution reproducibility
- Zero-shock attribution invariance
- Isolated-asset attribution behavior
- Tail-cohort contribution aggregation

Pull requests are validated automatically with GitHub Actions.

## Dashboard

The Streamlit application provides interactive access to:

- Protocol stress-test ladders
- Interactive asset-specific shocks
- Liquidation exposure by collateral asset
- Monte Carlo simulations
- Normal vs Student-t return assumptions
- Historical vs assumed calibration
- Tail-risk metrics
- Liquidation-threshold sensitivity

A dedicated **Liquidation Cascade Lab** adds controls for:

- ETH, BTC, and SOL initial shocks
- Asset-specific market depth
- Close factor
- Liquidation bonus
- Price-impact strength
- Maximum cascade rounds

It visualizes asset-level cascade attribution, endogenous price paths, collateral sold by round, secondary liquidations, and the most vulnerable ending positions.

A separate **Cascade Tail Risk** page compares first-order and cascade-aware exposure distributions over identical Monte Carlo draws. It includes:

- mean first-order versus cascade exposure,
- amplification probability,
- P95/P99 tail amplification,
- bad-debt tails,
- simulation-level paired comparisons, and
- optional market-depth sensitivity.

The **Reverse Stress Test** page solves for critical shocks instead of requiring a shock to be chosen first. It includes:

- selectable risk targets,
- asymmetric ETH/BTC/SOL stress weights,
- configurable market depth and liquidation mechanics,
- the smallest tested breach and largest tested safe shock,
- critical asset-level shock vectors, and
- a reverse-stress frontier across increasing risk thresholds.

The **Tail Risk Attribution** page explains which collateral assets drive modeled cascade risk by comparing each full simulated scenario with paired counterfactuals that neutralize one asset at a time. It shows:

- average marginal cascade-exposure contribution,
- tail-conditioned exposure contribution,
- tail bad-debt contribution,
- probability of a positive marginal contribution,
- secondary-liquidation contribution, and
- scenario-level shock-versus-contribution relationships.

## Project Structure

```text
riskforge/
├── .github/
│   └── workflows/
│       └── ci.yml
├── app.py
├── README.md
├── requirements.txt
├── pytest.ini
├── data/
│   └── calibration_snapshot.csv
├── pages/
│   ├── Cascade_Tail_Risk.py
│   ├── Liquidation_Cascade.py
│   ├── Reverse_Stress_Test.py
│   └── Tail_Risk_Attribution.py
├── scripts/
│   └── save_calibration.py
├── src/
│   ├── __init__.py
│   ├── calibration.py
│   ├── cascade_simulation.py
│   ├── data_generator.py
│   ├── liquidation_cascade.py
│   ├── reverse_stress.py
│   ├── risk_engine.py
│   ├── simulation.py
│   ├── stress_engine.py
│   └── tail_risk_attribution.py
└── tests/
    ├── test_calibration.py
    ├── test_cascade_simulation.py
    ├── test_liquidation_cascade.py
    ├── test_reverse_stress.py
    ├── test_risk_engine.py
    ├── test_simulation.py
    ├── test_stress_engine.py
    └── test_tail_risk_attribution.py
```

## Running the Project

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the test suite:

```bash
python -m pytest -q
```

Launch the Streamlit application:

```bash
streamlit run app.py
```

## Asset attribution methods

The Tail Risk Attribution page offers two ways to explain asset contributions:

- **Remove one asset’s shock:** measure the change when one asset’s market move is neutralized. These effects can overlap and need not add up to total exposure.
- **Split shared effects (Shapley):** use the existing exact coalition engine to allocate the change from a no-market-shock baseline across assets. For ETH, BTC, and SOL, this evaluates all eight coalitions. Contributions sum to the change from baseline, rather than necessarily to total exposure.

Both options use the same simulation controls and display tail-conditioned exposure, bad debt, and scenario contributions. Shapley mode reports an allocation reconciliation gap. Download buttons export the summary and scenario contributions, including the attribution method.

## Save and replay a cascade simulation

On **Cascade Tail Risk**, select **Download this simulation run** to save a ZIP containing the actual lending positions, every paired market scenario, the risk summary, and a manifest with resolved engine settings (including the seed and defaults), Python/NumPy/pandas versions, source-file fingerprints, and data-file checksums.

Replay the saved inputs from the repository root:

```bash
python -m src.run_bundle cascade_simulation_run.zip replayed_run.zip
```

The command checks the bundled files before running and refuses to overwrite an existing output. It uses the stored positions rather than generating a new portfolio. Use the same source revision and package versions when comparing results; a seed alone does not guarantee identical results across engine or dependency changes. Checksums detect changed data files, but do not authenticate a bundle's origin. The export covers the main Monte Carlo run, not the optional market-depth sweep.

### Market simulation input checks

The shared return sampler rejects invalid settings before drawing scenarios: simulation counts and horizons must be positive integers, seeds must be nonnegative integers, and each asset needs finite, nonnegative annual volatility. Correlation matrices must be finite, symmetric 3×3 matrices in ETH/BTC/SOL order, with a unit diagonal, entries in [-1, 1], and positive semidefinite structure. Zero volatility and singular positive semidefinite correlations remain supported.

The variance-normalized Student-t model requires finite degrees of freedom greater than two; values at or below two cannot support the configured finite variance. These checks apply to first-order Monte Carlo, cascade Monte Carlo, both attribution engines, and saved-run replay through their shared sampler.

## Compare saved runs

Open **Compare Saved Runs** and upload a baseline and candidate ZIP exported by Cascade Tail Risk. The page validates data-file checksums, shows candidate-minus-baseline summary changes, and lists changed simulation settings, package versions, and source fingerprints. Download the comparison as JSON.

Paired scenario changes are shown only when the saved portfolios match exactly and all recorded ETH/BTC/SOL shocks match by unique simulation ID. Equal seeds alone are insufficient. Unpaired runs still show summary differences, explicitly labeled as separate outcomes. Source and package changes are listed even for paired draws; pairing does not establish why outcomes changed. Fractions retain their original units, and scenario ranges are not confidence intervals.

Attribution dashboard results are cached in memory for up to one hour (at most eight input combinations). Selecting another asset chart reuses the computed run. Portfolio data, attribution method, and simulation settings are all part of the cache key; changing them computes a fresh result. Cached values are copied on retrieval so chart preparation cannot mutate another view's result.
