# July External Weather Strategy Audit: stfarm / Predict & Profit

## Document status

This document is an **investigation brief**, not an implementation specification and not owner approval to change strategy behavior.

It contains:

- Preliminary external findings from an earlier review
- Historical observations from a Nimbus repository snapshot
- Hypotheses that require independent verification
- Proposed research and instrumentation work
- Explicit cautions against retrospective tuning

Claude Code must classify every important claim as one of:

- Verified current fact
- Reproduced repository result
- External claim
- Preliminary calculation
- Outdated or contradicted claim
- Not reproducible from available evidence
- Not currently testable
- Hypothesis requiring prospective data

Numerical results may reflect an earlier repository snapshot or an earlier version of the external project. Do not treat them as current ground truth until reproduced.

---

# 1. Purpose

Conduct a rigorous, weather-only investigation into whether ideas from GitHub user `stfarm` and the “Predict & Profit” weather project could materially improve Nimbus.

The goal is **not** to clone another bot or assume it is better. The goal is to determine whether its trade-selection and rejection architecture addresses weaknesses that remain in Nimbus.

Specifically investigate whether the useful difference lies in:

1. Source-level forecast agreement
2. Trade rejection and selectivity
3. Market-quality filtering
4. Order-book depth and realistic fills
5. Forecast, quote, and signal recency
6. City-specific and segment-specific calibration
7. Alternative weather-model providers
8. Execution and accounting reliability
9. Better preservation of decision-time information

The intended outcome is to identify:

- What Nimbus already implements
- What Nimbus implements differently
- What the external project claims but does not substantiate
- What cannot be tested using current Nimbus history
- What should be logged prospectively
- What deserves a shadow experiment
- What should be rejected
- What single behavior-preserving instrumentation patch has the highest expected value

Be skeptical in both directions.

---

# 2. Scope boundaries

This is a **weather strategy audit only**.

Do not investigate or build:

- CPI trading
- PCE trading
- Inflation trading
- Employment or GDP markets
- Federal Reserve markets
- Any separate economics bot

The external project’s combined account may include profit or loss from non-weather strategies. Mention that only as a caveat when isolating weather-only performance.

Do not infer weather profitability from combined account profitability.

---

# 3. Repository safety and governance

Before investigating or modifying anything, read these files in full if they exist:

1. `CLAUDE.md`
2. `HANDOFF.md`
3. `FUTURE.md`
4. `README.md`
5. `audit/AUDIT_TODO.md`
6. `audit/REDDIT_FINDINGS.md`
7. `replay_selection.py`
8. `backtest_models.py`
9. Relevant sections of `kalshi_weather.py`
10. `test_nimbus.py`

Follow all existing Nimbus governance.

In particular:

- Never run `kalshi_weather.py` in the working tree.
- Never edit or regenerate `weather_state.json`.
- Never mutate production state.
- Never hand-edit generated documentation if repository rules prohibit it.
- Use a detached scratch copy for model runs.
- Do not change live or paper forecasting, pricing, selection, sizing, or risk behavior without all required governance steps.
- Preserve the historical record.
- Treat “do not adopt” as a successful outcome.
- Do not combine unrelated behavior changes.
- Do not tune thresholds after seeing results and then present the winner as evidence.
- Distinguish observational logging from behavior-changing code.
- Any claimed behavior-preserving change must pass before/after sandbox equivalence testing.
- Run all existing validation before proposing a commit.
- Do not purchase or access paid materials.
- Do not implement behavior-changing recommendations during the initial investigation.

Start with a read-only investigation.

---

# 4. External materials to investigate

Review the current public versions of:

- GitHub profile and repositories:  
  `https://github.com/stfarm?tab=repositories`
- Gumroad product:  
  `https://predictandprofit.gumroad.com/l/predict-and-profit`
- Predict & Profit website, especially:
  - Results or public ledger
  - How it works
  - Blog posts discussing early performance
  - Reliability, accounting, or version changes
  - Any descriptions of forecast sources, agreement rules, city handling, market filters, and risk controls
- Book:
  - **Predict & Profit: How to Build an Automated Weather Trading Bot for Kalshi**
  - Determine whether the book reflects the current weather system or an older version
- Relevant public Reddit posts or comments from the developer discussing:
  - Initial returns
  - Current profitability
  - Bankroll size
  - Exposure per trade
  - Forecast sources
  - Agreement filters
  - Market-quality scoring
  - Stale forecast problems
  - City-specific failures
  - Order execution
  - Fill accounting
  - Risk limits

Public descriptions may have changed. Verify current numbers and dates independently.

---

# 5. Preliminary external findings to reproduce

Treat everything in this section as a claim to verify.

## 5.1 Public weather performance

An earlier review reported approximately:

| Strategy | Resolved trades | Win rate | Published profit |
|---|---:|---:|---:|
| Weather Bot v2 | 103 | 59.2% | -$21.75 |
| Weather Bot v1, retired | 12 | 25.0% | +$1.42 |

The same public account reportedly showed positive combined profit because it also contained a separate non-weather strategy.

Important interpretation:

- Weather-only performance appeared negative.
- A win rate above 50% did not translate into positive P&L.
- Combined account profit must not be treated as proof that the weather bot is profitable.
- The ledger may not expose enough information to calculate rigorous ROI because cumulative dollars risked and time-varying bankroll may be unclear.

Verify:

- Current weather-only P&L
- Fees-inclusive versus gross P&L
- Dollars risked
- Number of independent weather events
- Number of correlated contracts per event
- Maximum drawdown
- Profit concentration by city and event
- Whether deposits or withdrawals affect reported returns
- Whether displayed “profit” reflects settled fills rather than intended orders

## 5.2 The approximately 410% return claim

The earlier review found that the widely cited approximately 410% return came from a very small first-week test balance and a tiny sample.

Later descriptions reportedly shifted toward:

- “Modest profit”
- Approximately 1% exposure per trade
- More cautious risk management

Determine:

- Original starting capital
- Dollars actually risked
- Realized versus unrealized results
- Exact sample size
- Whether deposits or withdrawals affected the percentage
- Whether the figure represented bankroll growth, return on risked dollars, or another calculation
- Whether the result persisted after the first week
- Whether the claim was weather-only

Do not use the 410% figure as an expected return unless its accounting is fully supported.

## 5.3 Architecture versions

The older public GitHub material reportedly described a 62-member system:

- 31 GFS members
- 31 AIGEFS members

The current website reportedly described:

- 31 GFS members
- 31 AIGEFS members
- 51 ECMWF IFS ensemble members
- 51 ECMWF AIFS ensemble members
- 164 total members

Determine:

- Which architecture is current
- Which architecture is represented in the GitHub repository
- Which architecture is represented in the book
- Whether the paid source uses the same architecture as the public website
- Whether “member count” refers to true independent members, lagged runs, deterministic outputs, or some other structure

## 5.4 Source agreement

The current public system reportedly requires at least three of four forecast sources to agree before trading.

Determine what “agreement” actually means:

- Similar expected temperature
- Same most likely bucket
- Same YES or NO direction
- Positive raw edge
- Positive fee-adjusted edge
- Minimum confidence threshold
- Agreement after bias correction
- Agreement after probability calibration
- Something else

This distinction is critical.

A rule based on expected temperature is not equivalent to a rule based on provider-specific fee-adjusted edge.

## 5.5 Market-quality filtering and rejection rate

The current system reportedly applies a market-quality score using some combination of:

- Bid-ask spread
- Volume
- Open interest
- Order-book imbalance
- Estimated mispricing
- Trade confidence
- Possibly depth or liquidity

The website reportedly says roughly 95% of potential opportunities are rejected.

Investigate:

- Exact factors
- Exact calculation, if public
- Whether the 95% figure refers to markets, candidate sides, model runs, or order attempts
- Whether rejection occurs before or after source agreement
- Whether the score predicts profitability or merely avoids illiquidity
- Whether it uses executable prices or midpoints
- Whether it accounts for fees and slippage
- Whether it evaluates event-level exposure across correlated contracts

## 5.6 Reported failure modes and later changes

The external developer reportedly identified early problems including:

- Trading against stale forecast information
- Excessive confidence in specific cities
- Reliability and accounting issues
- Need for market-recency checks
- Need for city-specific calibration
- Increasing the minimum edge threshold from approximately 10% to 12%
- Separating submitted orders from confirmed fills

Verify these claims and identify:

- Which changes were weather-model changes
- Which were trade-selection changes
- Which were execution/accounting fixes
- Whether results improved afterward
- Whether any change was evaluated prospectively

## 5.7 Book and paid source

The earlier review reported that the book:

- Was approximately 47 pages
- Cost approximately $9.99
- Focused on an older GFS-centered implementation
- Included basic ensemble counting, scoring, and risk-management concepts
- Did not appear to document the full current architecture

The paid source reportedly cost approximately $75 before promotions and included broader code than the public GitHub repository.

Verify current details, but do not purchase anything.

Treat paid source availability as:

- Evidence that the public GitHub repository may be incomplete
- Not evidence that the strategy has a durable edge
- Not permission to infer undocumented formulas

---

# 6. Current Nimbus facts to reproduce

The following observations came from an earlier repository snapshot. Reproduce them read-only.

## 6.1 Test status

The earlier snapshot reportedly passed:

- 46 tests
- 0 failures

Run the current test suite and report any differences.

## 6.2 Stored overall performance

Earlier reviews produced slightly different stake totals:

### Calculation A

- 262 resolved paper plays
- $3,262.78 total staked
- -$277.80 net P&L
- -8.51% ROI
- 40.46% win rate

### Calculation B

- 262 resolved paper plays
- $3,320.00 recorded stake
- -$277.80 fees-inclusive P&L
- -8.37% ROI
- 40.46% win rate

Investigate the denominator discrepancy.

Possible explanations include:

- Intended stake versus executable dollars spent
- Contract rounding
- Unused cash
- Different calculation dates
- Inclusion or exclusion of legacy records
- Different repository snapshots
- Different treatment of fees
- Different handling of missing values

Do not silently choose whichever denominator produces the better result.

## 6.3 Performance by kind and side

Earlier analysis reported approximately:

| Kind and side | Plays | ROI | P&L |
|---|---:|---:|---:|
| HIGH, Buy NO | 124 | -0.2% | -$3.12 |
| HIGH, Buy YES | 90 | -11.4% to -11.5% | approximately -$105 |
| LOW, Buy NO | 36 | -34.8% to -35.6% | approximately -$181 |
| LOW, Buy YES | 12 | +7.4% to +7.5% | approximately +$11 |

Reproduce the exact current figures.

Do not interpret them without controlling for:

- Model version
- Legacy versus current eras
- City
- Lead time
- Entry price
- Trade date
- Sample size

## 6.4 Performance by stored lead

Earlier analysis reported approximately:

| Lead | Plays | ROI | P&L |
|---|---:|---:|---:|
| Lead 0 | 33 | -50.8% to -51.4% | approximately -$190 |
| Lead 1 | 86 | -9.5% to -9.7% | approximately -$119 |
| Missing/legacy lead | 143 | +1.8% | approximately +$31 |

Important cautions:

- Missing lead values are largely legacy records.
- HIGH/LOW and lead may be entangled.
- Same-day nowcasting became live only recently.
- Do not conclude that the current nowcast failed from the full historical lead-0 aggregate.

## 6.5 Performance by model era

The earlier snapshot produced approximately:

| Model version | Plays | ROI | P&L |
|---|---:|---:|---:|
| Blank/legacy | 23 | -40.8% | -$132.59 |
| `2026-07-02.v3-nimbus-calib` | 156 | -2.8% | -$50.65 |
| `2026-07-06.v11-audit12` | 3 | +65.9% | +$23.06 |
| `2026-07-06.v12-capseed` | 28 | -0.5% | -$2.18 |
| `2026-07-13.v13-nowcast-shadow` | 46 | -8.2% | -$53.93 |
| `2026-07-25.v15-nowcast-live` | 6 | -51.3% | -$61.51 |

The six-play v15 result is far too small to judge the live nowcast era.

Use:

- Era-specific performance
- Prospective performance after registration
- Paired comparisons where possible
- Confidence intervals
- Fees-inclusive P&L
- Proper scoring rules

Do not rely only on lifetime ROI.

## 6.6 Forecast and probability scoring

Earlier analysis reported approximately:

- Model Brier: 0.1193
- Market Brier: 0.1013
- Model RPS: 0.5318
- Market RPS: 0.4020

Lower is better.

Interpret cautiously:

- The final market board may contain information Nimbus did not possess at decision time.
- Final-market superiority does not automatically prove decision-time calibration failure.
- Compare model probabilities with market probabilities at the actual decision timestamp where possible.
- Separate final-market scoring, entry CLV, forecast accuracy, and trading selection.

Reproduce the calculations and explain what each one does and does not prove.

---

# 7. Existing Nimbus capabilities that must not be overlooked

Nimbus already appears more sophisticated than the basic public weather-bot description in several areas.

Existing capabilities reportedly include:

- Four-provider ensemble
- GFS
- ECMWF IFS
- ICON
- GEM
- Provider/member pooling
- Per-provider summaries in `members_by_model`
- Bias correction
- Predictive-spread dressing
- Provider-skill weighting
- City/kind calibration
- Kernel-style dressed bucket probabilities
- CRPS
- RPS
- Brier score
- CLV analog
- Same-day observed-maximum nowcasting for highs
- Kalshi settlement verification
- Exposure caps
- Lead caps
- Cost and fee gating
- Quarantine logic
- Model-versioned eras
- Write-once `book0` decision snapshots
- Read-only forecast backtesting
- Read-only play-selection replay
- Preregistered experimental gates
- Audit and recovery procedures

Do not recommend a feature simply because the external project mentions it.

First determine whether Nimbus already has:

- An equivalent mechanism
- A more rigorous mechanism
- A superficially similar but economically different mechanism
- A logging mechanism without a selection rule
- A selection rule without enough diagnostics

At the same time, do not use model sophistication as a substitute for evidence of profitable selection.

---

# 8. Central analytical question

Separate these layers:

1. **Forecast layer**  
   How accurately does Nimbus estimate the actual temperature distribution?

2. **Probability layer**  
   Are bracket probabilities calibrated and sufficiently sharp?

3. **Selection layer**  
   Does Nimbus choose the right market, side, and price?

4. **Rejection layer**  
   Does Nimbus trade too often when evidence is weak or market quality is poor?

5. **Sizing layer**  
   Does unit allocation improve or damage ROI?

6. **Execution layer**  
   Are spread, depth, stale quotes, partial fills, and slippage consuming edge?

7. **Accounting layer**  
   Are intended orders, submitted orders, fills, fees, settlements, and realized returns recorded correctly?

The likely useful distinction to investigate is:

- Nimbus may have the stronger forecasting engine.
- The external project may place more emphasis on deciding **when not to trade**.

Attempt to prove or disprove that distinction.

---

# 9. Investigation A: source-consensus filtering

## 9.1 Hypothesis

Nimbus may produce reasonable pooled probabilities but trade when the apparent edge is driven mainly by one forecast provider or one unusual provider distribution.

Source consensus may improve trade selection even if it does not improve aggregate forecast MAE.

Evaluate it as a selection filter, not automatically as a new weighting method.

## 9.2 Earlier exploratory result

A previous analysis approximated provider agreement using stored provider means and standard deviations.

It reported:

| Sources supporting selected side | Comparable plays | Historical ROI |
|---|---:|---:|
| 2 of 4 | 26 | -61.4% |
| 3 of 4 | 39 | -27.6% |
| 4 of 4 | 50 | +1.5% |

The approximate unanimous result reportedly had a very wide 90% bootstrap interval:

- Approximately -22.7% to +25.7%

Interpretation:

- 4-of-4 was interesting, not proven.
- 3-of-4 did not appear helpful in this approximation.
- The approximation may not represent exact provider-specific probabilities.
- A prospective exact test may be required.
- Unanimity may substantially reduce trade frequency.

Reproduce this only if current data supports it.

Explain exactly how provider means and standard deviations differ from:

- Provider-specific member distributions
- Provider-specific bucket probabilities
- Provider-specific fee-adjusted edge

## 9.3 Inspect the current data model

Determine what Nimbus retains for each provider.

Can historical state reconstruct:

- Provider-specific probability for each bucket
- Provider-specific YES edge
- Provider-specific NO edge
- Provider-specific fee-adjusted net edge
- Provider-specific predictive spread
- Provider-specific calibration adjustment
- Provider-specific member counts
- Missing-provider behavior

Do not claim an exact historical replay if only means or partial summaries are stored.

## 9.4 Define agreement carefully

Evaluate a small set of principled definitions.

### Direction agreement

A provider supports YES when:

`provider_probability > market_mid`

A provider supports NO when:

`provider_probability < market_mid`

Problem: ignores fees and executable cost.

### Cost-adjusted agreement

A provider supports YES when:

`provider_probability - executable_yes_price - estimated_cost >= required_edge`

A provider supports NO when:

`(1 - provider_probability) - executable_no_price - estimated_cost >= required_edge`

This is more economically meaningful.

### Probability-only agreement

A provider supports the selected side when probability exceeds a fixed threshold.

Problem: a high win probability can still be a bad bet at an unfavorable price.

### Expected-temperature agreement

A provider supports the trade based on whether its expected temperature lies inside or outside the contract range.

Problem: discards distribution width and tail risk.

Recommend the primary definition before collecting prospective results.

Do not data-mine a large menu of definitions.

## 9.5 Calibration question

Determine whether provider-specific probabilities should use:

- Raw provider members
- Shared city/kind bias correction
- Provider-specific bias correction
- Shared predictive-spread dressing
- Provider-specific spread dressing
- No dressing, to preserve independence

Do not assume pooled calibration can simply be copied to each provider.

A defensible first prospective test may compare:

1. Raw provider distributions
2. Shared city/kind correction
3. No provider-specific fitting until enough data exists

Avoid building four overfit mini-models from a small sample.

## 9.6 Required prospective schema

Consider additive, versioned logging such as:

```yaml
source_probabilities:
  gfs025:
    yes_probability:
    no_probability:
    yes_net_edge:
    no_net_edge:
    supported_side:
  ecmwf_ifs025:
  icon_seamless:
  gem_global:

source_agreement:
  selected_side:
  supporting_sources:
  support_count:
  unanimous:
  definition_version:
```

Prefer nested versioned structures over many loose top-level fields.

Do not alter live selection merely by logging these values.

## 9.7 Prospective shadow policies

At minimum, evaluate:

- Champion unchanged
- Champion plus at least 3-of-4 cost-adjusted support
- Champion plus 4-of-4 cost-adjusted support

Specify before collecting results:

- Registration date
- Minimum resolved-play count
- Maximum waiting period, if any
- Primary metric
- Secondary metrics
- Adoption threshold
- Rejection threshold
- Paired versus unpaired analysis
- Bootstrap method
- Treatment of ties
- Missing-provider behavior
- Treatment of unhealthy or biased ladders

Do not promote either filter from the retrospective approximation.

---

# 10. Investigation B: market-quality and liquidity gating

## 10.1 Current suspected limitation

Current market ingestion appears to retain fields such as:

- YES bid
- YES ask
- Derived midpoint
- Open interest
- Strike structure

The current `book0` may use fields similar to:

```python
("ticker", "mp", "mid", "yb", "ya", "oi", "floor", "cap", "stype")
```

Confirm the exact schema.

Nimbus may not retain:

- Market volume
- Best-price quantity
- Multi-level depth
- Order-book imbalance
- Estimated slippage
- Quote timestamp
- Market movement between signal and simulated execution

## 10.2 Why open interest is insufficient

Open interest does not directly answer:

- How many contracts are available at the quoted price
- Whether the intended order can fill
- How quickly price worsens across the book
- Whether one side dominates the book
- Whether apparent edge exists only for one contract
- Whether paper P&L assumes unrealistic top-of-book fills

Quantify this risk.

## 10.3 Read-only order-book investigation

Investigate current Kalshi APIs for:

- Single-market order books
- Batch order books
- Market volume
- Open interest
- Bid levels
- Quantities
- Update timestamps
- Historical availability
- Websocket availability
- Rate limits
- Fixed-point versus dollar fields
- YES/NO book representation

Do not introduce authenticated order placement.

## 10.4 Candidate market-quality schema

Consider additive logging:

```yaml
market_quality:
  observed_at:
  volume:
  open_interest:
  yes_bid:
  yes_ask:
  spread:
  yes_depth_at_best:
  no_depth_at_best:
  depth_within_1_cent:
  depth_within_2_cents:
  top_3_level_depth:
  order_book_imbalance:
  intended_contracts:
  estimated_average_fill_price:
  estimated_slippage:
  executable_fraction_at_entry:
  calculation_version:
```

Clarify exactly how NO prices and quantities are derived.

## 10.5 Do not adopt arbitrary thresholds

Earlier exploratory suggestions included:

- Spread no greater than $0.04
- Best-price depth at least 5 times intended order size
- Depth within $0.02 at least 10 times intended order size
- Estimated slippage no greater than $0.01 per contract

Treat these only as candidate bands for analysis.

Do not hard-code them as production thresholds.

Preferred sequence:

1. Log features.
2. Analyze preregistered bands or deciles.
3. Estimate realistic fills.
4. Test association with CLV, fillability, fees-inclusive ROI, slippage, and cancellation risk.
5. Propose a gate only after evidence exists.

## 10.6 Interaction with `book0` and replay

Determine whether order-book data should:

- Extend immutable `book0`
- Live in a separate immutable `book0_depth`
- Be stored in a shadow-only structure
- Be unavailable for old records without imputation

Never fabricate historical depth.

Never substitute a later board for the original decision board.

---

# 11. Investigation C: forecast, quote, and signal recency

## 11.1 Reported external lesson

The external developer reportedly identified stale forecast or stale signal timing as a source of early losses.

Nimbus already appears to address some timing issues through:

- Deliberate forecast-cycle scheduling
- Rejecting redundant runs without new forecast information
- Same-day observational nowcasting
- Write-once decision boards
- Awareness of GitHub Actions delay

However, exact signal-to-order staleness may not be measured.

## 11.2 Separate staleness types

Analyze separately:

1. Forecast staleness
2. Market-quote staleness
3. Signal staleness
4. Execution staleness
5. Workflow-start delay
6. Superseded forecast runs

Do not collapse these into one timestamp.

## 11.3 Candidate timing schema

Consider:

```yaml
signal_timing:
  forecast_run_time:
  forecast_age_minutes:
  market_snapshot_time:
  quote_age_seconds:
  signal_created_at:
  intended_submission_at:
  market_mid_at_signal:
  executable_price_at_signal:
  executable_price_at_recheck:
  market_move_since_signal:
  original_net_edge:
  rechecked_net_edge:
  fraction_of_edge_remaining:
  timing_version:
```

## 11.4 Candidate future rules

Earlier suggestions included:

- Recalculate after a market move of approximately $0.04
- Reject when more than half the original edge disappears
- Recheck immediately before submission
- Reject signals based on superseded forecast runs

Treat these as hypotheses.

Determine what can be tested in shadow mode before behavior changes.

---

# 12. Investigation D: AIGEFS and ECMWF AIFS

## 12.1 Hypothesis

AIGEFS and AIFS may provide additional model diversity.

That does not mean replacing ICON and GEM will improve Nimbus.

The first question is forecast quality, not trading ROI.

## 12.2 Data availability

Determine:

- Whether Open-Meteo or another stable source exposes AIGEFS members
- Whether ECMWF AIFS ensemble data is publicly accessible
- Member counts
- Update frequency
- Forecast horizon
- Geographic coverage
- Historical archive availability
- Reliability
- Terms of service
- Cost
- Rate limits
- Data latency
- Whether outputs are true ensemble members or summaries
- Whether daily extrema align with Kalshi’s Local Standard Time settlement rules

Do not create fragile scraping dependencies.

## 12.3 Controlled forecast challenger

If access is viable, propose:

### Champion

- GFS
- ECMWF IFS
- ICON
- GEM

### Challenger

- GFS
- ECMWF IFS
- AIGEFS
- ECMWF AIFS

Hold constant:

- Calibration method
- Settlement window
- Bias correction
- Probability dressing
- City set
- Forecast horizon
- Observation source
- Scoring method

Compare:

- MAE
- Signed bias
- RMSE
- CRPS
- Bucket Brier
- RPS
- Calibration slope
- Calibration intercept
- City-level performance
- HIGH versus LOW
- Lead
- Seasonal regime
- Missing-data frequency
- Operational reliability

Do not judge provider replacement by trading ROI first.

Do not combine provider replacement with source-consensus filtering in the same initial experiment.

## 12.4 Opportunity cost

Existing Nimbus notes may classify more providers as a diminishing-returns area.

Challenge that honestly, but quantify:

- Expected forecast gain
- Engineering burden
- Reliability risk
- New failure modes
- Maintenance cost
- Sample required to judge the challenger

A tiny MAE gain does not automatically justify a fragile dependency.

---

# 13. Investigation E: measurement and resolved-play schema

## 13.1 Suspected schema gap

Pending plays may retain fields including:

- `net`
- `edge`
- `p_win`
- `entry`
- `mid`
- `tier`
- `units`
- `stake`

When a play resolves, `resolve_pending()` may not preserve every decision-time field.

Confirm precisely whether resolved records lose:

- `p_win`
- `net`
- Gross edge
- Spread cost
- Fee estimate
- Safety buffer
- Open interest
- Source agreement
- Market-quality fields
- Quote timing
- Calculation version

## 13.2 Why this matters

If decision-time decomposition is lost, later analysis cannot reliably distinguish:

- Probability error
- Price error
- Fee burden
- Spread burden
- Slippage
- Buffer assumptions
- Excessively optimistic stated edge
- Low win-probability selections
- Liquidity problems
- Source disagreement
- Strategy-era differences

If the pending record is removed after settlement, unpreserved fields may be permanently lost.

## 13.3 Candidate additive resolved schema

Consider:

```yaml
selection:
  model_probability:
  win_probability:
  market_mid:
  executable_entry:
  raw_edge:
  estimated_spread_cost:
  estimated_fee:
  safety_buffer:
  net_edge:
  open_interest:
  volume:
  intended_contracts:
  source_agreement:
  market_quality:
  signal_timing:
  calculation_version:
```

Do not rewrite legacy records.

Reports must handle missing fields safely.

## 13.4 Accounting verification

Verify:

- Contract calculation from stake and entry
- Whether unused cash from integer rounding counts as risked
- Fee calculation
- Fee rounding
- YES payout
- NO payout
- ROI denominator
- Whether stake means budget or actual spend
- Whether displayed stake equals contracts times entry
- Whether legacy records use the same accounting
- Whether paper results assume fills unsupported by depth

Explain the historical stake-denominator discrepancy.

---

# 14. Investigation F: current losing segments

## 14.1 Do not immediately hard-code quarantines

The earlier analysis identified:

- LOW Buy NO
- Same-day lead-0
- HIGH Buy YES

as potentially problematic.

Do not automatically quarantine them based only on retrospective cells.

Review existing preregistered experiments in `FUTURE.md` and `replay_selection.py`.

The existing replay slate may already include:

- NO-only
- YES-only
- Minimum entry price
- Minimum win probability
- Higher net-edge thresholds
- Higher minimum open interest
- Lead restrictions
- Maximum entry price
- Flat sizing
- Combined entry-floor and NO-only policies

Do not duplicate existing experiments under new names.

## 14.2 Same-day nowcast caution

The live nowcast era reportedly had only about six resolved plays in the earlier snapshot.

Do not infer that nowcast promotion failed.

Instead:

- Compare forecast scores before and after nowcast.
- Compare selection separately.
- Determine whether lead-0 losses were pre-nowcast.
- Break down HIGH versus LOW.
- Break down YES versus NO.
- Check city concentration.
- Check bucket and entry-price concentration.
- Respect existing promotion gates and Decision Log entries.

## 14.3 Required segment analysis

Produce fees-inclusive results by:

- Model version
- Legacy versus audit era
- City
- HIGH/LOW
- YES/NO
- Lead
- Entry-price band
- Stated win-probability band
- Net-edge band
- Open-interest band
- Forecast-spread band
- Source-agreement count, when available
- Market-quality band, when available
- Registration date versus prospective period

Use minimum-sample warnings.

Do not promote conclusions from tiny cells.

---

# 15. Statistical and experimental discipline

For every proposed experiment:

## 15.1 State the hypothesis

Example:

> Trades supported by all four independent forecast sources have higher fees-inclusive ROI than otherwise identical champion candidates.

## 15.2 Define treatment before results

Specify:

- Exact calculation
- Inclusion rules
- Exclusion rules
- Missing-data behavior
- Registration date
- Sample threshold
- Primary metric
- Secondary metrics
- Adoption rule
- Rejection rule
- Maximum number of variants

## 15.3 Use paired comparisons where possible

For a filter applied to champion candidates, compare:

- Candidate set before filter
- Candidate set after filter
- Retained trades
- Rejected trades
- Same prospective period

Report:

- ROI of retained trades
- P&L of retained trades
- Opportunity cost from skipped winners
- Avoided losses
- Trade-frequency reduction

## 15.4 Account for multiple testing

Do not inspect many thresholds and adopt the best one.

Acceptable approaches:

- Small preregistered slate
- Prospective holdout
- Bootstrap comparison
- Reporting the full slate
- No threshold changes after registration

## 15.5 Evaluate more than ROI

Use, where applicable:

- Fees-inclusive ROI
- Net P&L
- Dollars risked
- Win rate
- Average entry price
- Average stated win probability
- Average net edge
- Average CLV
- CLV confidence interval
- Brier score
- RPS
- CRPS
- Calibration slope
- Calibration intercept
- Maximum drawdown
- Trade count
- Rejection rate
- City concentration
- Side concentration
- Fillability
- Estimated slippage
- Missing-data rate
- Operational reliability

A positive five-trade subgroup is not evidence of a durable edge.

---

# 16. Implementation sequence

## Phase 1: read-only external and repository investigation

Produce a written comparison of:

- External weather architecture
- Nimbus architecture
- Public weather-only evidence
- Public marketing claims
- Missing information
- Applicable ideas
- Non-applicable ideas

Do not change live behavior.

## Phase 2: reproduce Nimbus measurements

Use read-only scripts to reproduce:

- P&L
- ROI
- Win rate
- Stake denominator
- Segment results
- Model-era results
- Brier/RPS comparisons
- Existing replay results

Do not mutate state.

## Phase 3: schema and instrumentation proposal

Identify the minimum additive data required for:

- Exact provider consensus
- Market quality
- Signal recency
- Realistic fill modeling
- Better resolved-play analysis

Explain which fields can be derived historically and which must be captured prospectively.

## Phase 4: zero-behavior-change instrumentation

Only after proving the design:

- Add one instrumentation family at a time.
- Add tests.
- Preserve backward compatibility.
- Prove selection output is unchanged.
- Update required documentation.
- Do not change champion behavior.

Potential first instrumentation families:

1. Preserve complete selection-time fields on resolution.
2. Log exact provider-specific probabilities.
3. Log market volume and order-book data.
4. Log signal and quote timestamps.

Do not combine all four in one ambiguous patch.

## Phase 5: prospective shadow experiments

After preregistration:

- 3-of-4 agreement
- 4-of-4 agreement
- Order-book-quality filter
- Realistic-fill replay
- Alternative AI-ensemble challenger

No automatic promotion.

## Phase 6: behavior-change proposal

Only after a gate is readable:

- Present evidence
- Present strongest counterargument
- Present expected trade-frequency reduction
- Present uncertainty
- Present exact code change
- Obtain required owner approval
- Ship one knob family
- Bump model version
- Update governance records

---

# 17. Required deliverables

Do not return only general commentary.

## Deliverable 1: external evidence table

For every relevant external claim, report:

- Claim
- Current source
- Date
- Verified status
- Sample size
- Dollars risked
- P&L
- ROI if calculable
- Major caveat
- Relevance to Nimbus

## Deliverable 2: feature comparison matrix

Use columns:

| Feature | External project | Nimbus | Meaningfully different? | Evidence | Recommended action |
|---|---|---|---|---|---|

Include:

- Forecast sources
- Member counts
- Calibration
- Provider-specific probabilities
- Source consensus
- Trade rejection
- Market-quality score
- Open interest
- Volume
- Order-book depth
- Spread handling
- Slippage
- Forecast staleness
- Quote recency
- Signal recency
- Fill confirmation
- Fees
- Sizing
- Exposure caps
- City calibration
- Nowcasting
- Settlement
- Proper scoring
- CLV
- Replay
- Experiment governance

## Deliverable 3: current-state data audit

Document:

- Relevant state paths
- Fields retained in predictions
- Fields retained in `book0`
- Fields retained in pending plays
- Fields retained in resolved events
- Fields retained in resolved plays
- Fields lost at settlement
- Fields required for each experiment
- Backward-compatibility implications

## Deliverable 4: recommendation verdicts

Assign each major recommendation one status:

- Already implemented
- Implemented differently
- Worth additive logging
- Worth a prospective shadow test
- Historically testable
- Not historically testable
- Low expected value
- Reject
- Requires paid source to assess
- Separate future project

Explain each verdict.

## Deliverable 5: preregistration proposals

Draft exact prospective experiment language for:

1. Source consensus
2. Market quality
3. Signal recency
4. Alternative provider stack

Do not add these to governance files until the designs are coherent.

## Deliverable 6: implementation plan

For each proposed code change, identify:

- File
- Function
- New schema fields
- Whether behavior changes
- Whether `MODEL_VERSION` changes
- Tests
- Sandbox validation
- Migration behavior
- Documentation changes
- Commit boundaries

## Deliverable 7: strongest case against adoption

For every recommendation, explain why it may fail.

Examples:

- Source agreement may retain only obvious, efficiently priced outcomes.
- Four-source unanimity may reduce trade count too severely.
- Forecast sources may not be independent.
- AI weather models may duplicate conventional information.
- High liquidity may correlate with more efficient pricing.
- Market-quality filters may remove high-edge opportunities.
- Public profit may be a small-sample artifact.
- Added complexity may reduce reliability.
- Historical subgroups may be contaminated by model-era changes.

The final recommendation must survive these objections.

---

# 18. Questions the investigation must answer

1. Is the current public stfarm weather strategy profitable after fees?
2. What exactly did the approximately 410% figure measure?
3. How many independent weather events produced the public results?
4. What changed between GitHub, the book, the website, and paid versions?
5. What exactly does three-of-four source agreement mean?
6. Can Nimbus reproduce exact historical source consensus?
7. If not, what minimum prospective instrumentation is required?
8. Does Nimbus’s current `book0` support realistic execution analysis?
9. How much paper P&L assumes top-of-book fills that may not be executable?
10. Is open interest adding meaningful selection value?
11. Would volume and depth add information beyond spread and open interest?
12. Which losses arise from forecasting versus selection?
13. Which losses are legacy versus current-model losses?
14. Is HIGH Buy NO genuinely near break-even prospectively?
15. Is LOW Buy NO still poor after controlling for era, city, lead, entry, and version?
16. Is the lead-0 result mostly pre-nowcast?
17. Is decision-time field loss impairing diagnosis?
18. Can AIGEFS and AIFS be obtained reliably?
19. Would replacing ICON/GEM improve CRPS enough to justify the cost?
20. Is the external project’s likely advantage more about rejection than prediction?
21. What is the highest-value zero-behavior-change instrumentation patch?
22. What evidence would be sufficient to promote any new rule?

---

# 19. Decision standard

Do not recommend a feature because:

- Another developer uses it
- It sounds sophisticated
- It produced a positive retrospective subgroup
- It increases win rate
- It improves one metric while damaging others
- It appears in a paid product
- It contributed to a marketing return claim
- It reduces losses only in a tiny sample

Recommend a feature only when:

- The expected benefit is identifiable
- The mechanism is economically coherent
- The data required can be captured
- The test can be preregistered
- The behavior change can be isolated
- The operational burden is justified
- The downside case is understood

---

# 20. Initial hypotheses to challenge

Use these only as hypotheses:

1. Replacing Nimbus’s full weather model is probably not justified.
2. Source consensus may be useful as a prospective selection filter.
3. Exact historical source consensus may not be reconstructable from provider means alone.
4. Order-book depth and realistic fill modeling become more important as stakes increase.
5. Complete decision-time field retention is a prerequisite for diagnosis.
6. Severe lifetime losses may be concentrated in specific segments and legacy periods.
7. The six-play live-nowcast era cannot be judged.
8. The external weather bot’s public results do not currently demonstrate superior profitability.
9. The best first code change is likely additive measurement, not a new trading rule.
10. Nimbus’s most important weakness may be deciding when not to trade rather than raw forecasting.

Attempt to disprove each one.

---

# 21. Immediate instructions

Begin with:

1. Read all governance and technical files.
2. Re-run the test suite.
3. Reproduce current performance calculations read-only.
4. Inspect exact state and settlement schemas.
5. Review current public external materials.
6. Produce the external evidence table.
7. Produce the feature matrix.
8. Identify the minimum viable instrumentation patch.
9. Stop before behavior-changing implementation.

Do not stop with:

> Nimbus already does most of this.

For each external concept, explain:

- Whether Nimbus truly has an equivalent
- Whether the implementation differs economically
- Whether it targets a measured Nimbus weakness
- Whether it can be tested honestly
- What implementation cost and risk it creates

After the investigation, do not implement anything unless separately instructed.

A proposed strictly additive patch must include:

- Exact files and functions
- Schema changes
- Backward compatibility
- Tests
- Sandbox equivalence procedure
- Explanation of why it cannot alter forecasting, pricing, selection, sizing, settlement, or reporting
