Kalshi Weather Trading Platform Technical Review
================================================

Your objective is **not simply to improve my existing bot.**

Your objective is to redesign every component to maximize long-term expected value while maintaining statistical rigor.

Assume every design decision could be wrong.

Challenge everything.

Suggest new features whenever they are justified by evidence.

Treat this as if millions of dollars were being traded.

Use plain language to explain what improvements and changes are being made. I want you to think like a quant, but explain like I am someone without experience in this. 

* * *



1. # Step 0 - Data Integrity & Measurement Audit (Highest Priority)

Before suggesting any new models or features, assume the current dataset may contain hidden flaws.

Your first task is to verify that every downstream analysis is built on reliable data.

Investigate:

### API Reliability

- Missing API responses
- Partial responses
- Rate limiting
- Silent failures
- Retry logic
- Duplicate requests
- Stale cached responses
- Timestamp consistency

### Forecast Data Integrity

- Missing forecasts
- Duplicate forecasts
- Incorrect issue times
- Incorrect valid times
- Forecast revisions
- Provider outages
- Unit conversion errors
- Time zone mistakes
- Daylight Saving Time edge cases

### Kalshi Market Data

- Missing markets
- Missing price history
- Incorrect bid/ask values
- Liquidity anomalies
- Settlement discrepancies
- Delisted or canceled markets
- Market metadata consistency

### Weather Station Validation

- Verify every market settles using the expected official observing station.
- Check station metadata.
- Detect station changes over time.
- Verify elevation and location.
- Detect observation outages.

### Data Leakage

Determine whether any information unavailable at trade time is accidentally entering the model.

Examples:

- Future forecast revisions
- Settlement observations
- Closing market prices
- Late API updates
- Forecasts published after trade execution
- Cached responses created after execution time

### Timestamp Audit

Verify that every timestamp in the pipeline is correct.

Check:

- UTC vs local time
- Forecast issue time
- Forecast valid time
- API retrieval time
- Trade execution time
- Kalshi market timestamps
- Settlement timestamps

### Historical Completeness

Determine:

- What percentage of historical observations are missing?
- Which providers have gaps?
- Which cities have sparse history?
- Are missing values random or systematic?

### Data Quality Metrics

Design automated health metrics for:

- Missing data %
- Duplicate rate
- API uptime
- Forecast freshness
- Provider latency
- Settlement accuracy
- Data consistency
- Schema validation

### Deliverables

Provide:

1. A complete data quality report.
2. Every potential source of data corruption.
3. Every possible source of hidden bias.
4. Confidence that the historical database is trustworthy.
5. Recommended automated integrity checks that should run every day before trading.
6. Any improvements that should be made before continuing with model optimization.

**Do not proceed to the remaining audit until you are satisfied that the data foundation is statistically sound.**

1. Forecast Ingestion
   =====================

Review every aspect of forecast collection.

Questions:

* Am I collecting enough forecast providers?
* Which providers consistently outperform others?
* Which providers are redundant?
* Which providers should receive larger weights?
* Which providers specialize in different forecast horizons?

Investigate adding:

* ECMWF
* GFS
* HRRR
* NAM
* RAP
* GEFS
* SREF
* Open-Meteo
* WeatherAPI
* Tomorrow.io
* NOAA
* National Weather Service
* Meteostat
* OpenWeather

Determine whether ensemble model members should be stored individually instead of only storing the blended forecast.

* * *

2. Forecast Timing
   ==================

Investigate:

Which model runs contain the most predictive information?

Should forecasts be saved after:

00z

06z

12z

18z

How much information arrives after each run?

Should trades occur immediately after a model update?

Should probabilities evolve continuously?

* * *

3. Historical Database
   ======================

Critique my historical data architecture.

Should I store:

Every forecast

Every model run

Every revision

Every API response

Every Kalshi market

Every price update

Settlement observations

Weather station metadata

Forecast issue times

Forecast valid times

Lead time

Market liquidity

Bid/ask spread

Execution latency

Determine the ideal database schema.

* * *

4. Calibration Engine
   =====================

Audit my auto-calibration model.

Investigate:

Bias correction

Temperature bias

Seasonal bias

Regional bias

Elevation effects

Urban heat island effects

Provider drift

Climate regime shifts

Suggest the statistically best calibration pipeline.

* * *

5. Probability Modeling
   =======================

My goal is NOT to predict one temperature.

My goal is to estimate

P(72°F)

P(73°F)

P(74°F)

...

Determine the best statistical methods.

Compare:

Gaussian assumptions

Kernel density estimation

Bayesian models

Quantile regression

Mixture models

Gradient boosting

Distributional regression

Ensemble distributions

Bayesian Model Averaging

CRPS optimization

* * *

6. Forecast Uncertainty
   =======================

Determine how uncertainty should be modeled.

Investigate:

Ensemble spread

Forecast disagreement

Historical calibration

Confidence intervals

Prediction intervals

Weather regime uncertainty

Extreme event uncertainty

Should uncertainty itself influence bet sizing?

* * *

7. Provider Weighting
   =====================

Instead of fixed weights,

Design an adaptive weighting system.

Weights should potentially depend on:

City

Season

Forecast horizon

Weather pattern

Temperature range

Provider history

Recent performance

Lead time

Model agreement

Recent calibration

Recommend the best algorithm.

* * *

8. Market Modeling
   ==================

Treat Kalshi as a prediction market.

Investigate:

How quickly prices react

How quickly weather forecasts update

Market inefficiencies

Liquidity effects

Bid/ask spreads

Order book imbalance

Price momentum

Mean reversion

Intraday behavior

When the market is slowest to react

* * *

9. Market Timing
   ================

Determine the optimal time to trade.

Questions:

Immediately after model runs?

Hours later?

Near settlement?

Early markets?

Late markets?

How does timing affect EV?

* * *

10. Expected Value
    ==================

Audit my EV calculations.

Investigate:

vig removal

probability estimation

confidence intervals

Kelly sizing

fractional Kelly

uncertainty-adjusted EV

probability error propagation

* * *

11. Auto Learning
    =================

Critique my learning pipeline.

How should the system improve automatically?

Ideas:

continuous recalibration

rolling validation

adaptive provider weights

automatic bias correction

concept drift detection

performance decay alerts

automatic retraining

* * *

12. Machine Learning
    ====================

Would ML outperform the current calibration system?

Compare:

XGBoost

LightGBM

CatBoost

Random Forest

Bayesian regression

Gaussian Processes

Neural Networks

Distributional Neural Networks

Stacked ensembles

Meta learners

If ML is not justified, explain why.

* * *

13. Backtesting
    ===============

Audit everything.

Look for:

Look-ahead bias

Survivorship bias

Settlement bias

Timestamp errors

API timing errors

Station mismatches

Calibration leakage

Selection bias

Data leakage

Overfitting

Curve fitting

* * *

14. Risk Management
    ===================

Evaluate:

Kelly Criterion

Fractional Kelly

Maximum drawdown

Risk of ruin

Correlation between markets

Daily exposure

City concentration

Weather event concentration

Tail risk

Black swan events

* * *

15. Weather Science
    ===================

Investigate whether additional meteorological information would improve forecasts.

Examples:

Humidity

Cloud cover

Wind speed

Wind direction

Pressure

Dew point

Elevation

Terrain

Urban heat island

Snow cover

Soil moisture

Frontal passages

Storm systems

Air mass changes

Satellite observations

Radar

Upper-air soundings

Determine which actually improves predictive performance.

* * *

16. Advanced Statistical Ideas
    ==============================

Investigate:

Bayesian updating

Kalman filters

Particle filters

State-space models

Markov models

Hidden Markov Models

Hierarchical Bayesian models

Gaussian Processes

Copulas

Monte Carlo simulation

Bootstrap confidence intervals

CRPS

Proper scoring rules

Distribution calibration

Reliability diagrams

Expected Calibration Error

Brier Score

Log Loss

* * *

17. Trading Engine
    ==================

Critique:

Order execution

Latency

Slippage

Partial fills

Liquidity detection

Position sizing

Trade cancellation

Multiple simultaneous markets

Portfolio optimization

* * *

18. Monitoring
    ==============

Design dashboards showing:

ROI

Expected ROI

Calibration

Provider performance

Forecast error

Market error

CLV (where applicable)

API health

Model health

Database health

Latency

Provider drift

Weather regime changes

* * *

19. New Feature Brainstorm
    ==========================

Think creatively.

Suggest features that I have not considered.

Examples:

Market confidence score

Provider agreement score

Forecast volatility index

Weather regime classifier

Market efficiency score

Probability confidence interval

Automatic no-trade classifier

Market anomaly detector

Forecast revision tracker

Forecast surprise detector

Settlement risk estimator

Execution quality score

Portfolio optimizer

* * *

20. Software Architecture
    =========================

Review my entire codebase.

Recommend improvements for:

Database design

Caching

Parallel processing

Asynchronous jobs

API retry logic

Fault tolerance

Logging

Versioning

Testing

Containerization

Deployment

Configuration management

Feature flags

CI/CD

Observability

Scalability

* * *

21. Think Like a Quant Fund
    ===========================

Assume this system eventually manages a $10M bankroll.

What would a professional quantitative weather trading firm build that I haven't?

Consider:

Research infrastructure

Simulation environment

Forecast archives

Experiment tracking (MLflow, Weights & Biases)

Feature stores

Model registry

Canary deployments

A/B testing

Automatic hyperparameter optimization

Bayesian optimization

Walk-forward optimization

Real-time anomaly detection

Research notebooks

Decision logging

Post-trade analysis

* 

* * *

One thing I'd add beyond this prompt—and this comes from seeing how experienced quantitative hobbyists tend to think—is to ask Claude to spend time on **the value of information**. Specifically, ask questions like:

* Which additional data source would increase predictive accuracy the most per dollar or hour invested?
* If only one new feature could be added, which one would provide the highest expected return?
* Which parts of the current system are likely already near the point of diminishing returns?

Those questions can help prioritize effort. It's common to spend weeks squeezing tiny improvements out of a well-performing model, while another missing data source or modeling change could have a much larger impact.
