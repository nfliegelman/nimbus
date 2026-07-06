# Nimbus Technical Audit: Working TODO

**Plan version:** audit-plan v1 (2026-07-04). **STATUS: AUDIT COMPLETE 2026-07-06.** All 12 batches plus the owner's Reddit batch executed. The consolidated findings register is at the bottom of this file; the post-audit build order is at the top of FUTURE.md.
**Source:** AUDIT_ORIGINAL.md (the owner's full audit brief, kept verbatim in the repo). This file is the working task list built from it. Every enumerated check from the original is preserved here; items marked **(ADDED)** were not in the original and were added while building the plan, in the spirit of the original brief.
**Companions:** HANDOFF.md (spec, changelog, session protocol), FUTURE.md (ideas backlog), README.md (owner setup doc).
**Code under audit:** kalshi_weather.py (847 lines, stdlib only, MODEL_VERSION "2026-07-02.v3-nimbus-calib"), .github/workflows/run.yml (crons 12:00 and 02:00 UTC), weather_state.json (persistence), docs/index.html + docs/results.html (rendered dashboards).

---

## Baseline captured at audit start (2026-07-04)

- State file: 73 resolved bucket records across target dates 2026-07-01 to 2026-07-03. ALL 73 predate version stamping (no `model_version` field). 19 pending predictions, all stamped `2026-07-02.v3-nimbus-calib`.
- `py_compile` passes on the current file. Both GitHub Pages dashboards are live and rendering.
- The repo is PUBLIC. `weather_state.json` is world-readable at raw.githubusercontent.com. This is convenient for auditing (any AI session can pull live state without an upload) and a privacy/security decision to make explicitly in Batch 12, before any API keys or real-money data exist.
- History is 3 days deep. Most performance verdicts in this audit are data-gated. The audit therefore verifies MECHANISMS now (math, timestamps, leakage, settlement correctness) and defines explicit evidence gates for the verdicts that need history, rather than pretending 73 records prove anything.

---

## How to use this file

- Status legend: `[ ]` not started, `[~]` in progress, `[x]` done (findings summarized in the HANDOFF changelog), `[>]` deferred (moved to FUTURE.md with a note).
- Work in batch order unless the owner says otherwise. One batch per working session is the intent.
- When a batch finishes: mark items here, write findings into the HANDOFF changelog with severity tags, move any new ideas into FUTURE.md, and hand the owner a zip of every changed root file.
- Findings severity: **P0** = invalidates data, settlements, or the measurement of the model itself (fix before anything else). **P1** = materially changes EV, sizing, or risk. **P2** = hygiene, polish, or robustness.
- Per AUDIT_ORIGINAL: think like a quant, explain like the owner has no quant background. Every finding gets a plain-language explanation of what it means and why it matters.

## Session protocol (binding for any AI running a batch)

1. Read HANDOFF.md fully first, then FUTURE.md, then this file. AUDIT_ORIGINAL.md is the reference brief.
2. No em dashes anywhere: not in code, docs, or chat. Surgical edits only. Do not rebuild from scratch.
3. Hand back FULL FILES in a zip, never paste-in snippets. Exception per HANDOFF 0b: `run.yml` changes are delivered as paste-in content for the web editor at `.github/workflows/run.yml`, because root uploads cannot reach dot-folders.
4. Never include `weather_state.json` or anything in `docs/` in a handback.
5. Validate before handback: `py_compile` passes, `CI=true python kalshi_weather.py` writes both dashboards, no backslash inside any f-string expression, no guard removed, HANDOFF changelog updated.
6. Bump MODEL_VERSION only when scoring, sizing, calibration, or logging behavior changes. Audit convention: `2026-MM-DD.vN-audit<batch>`.
7. Honesty rule: when evidence is insufficient (at n=73 it usually is), say "data-gated," state the gate, and move on. Do not manufacture verdicts.

---

## Batch plan

| Batch | Sections | Research mode | Notes |
|---|---|---|---|
| 1 | 0 Data integrity and measurement (plus added 0.9 to 0.11) | No | DONE 2026-07-04. Findings in Section 0 below and HANDOFF v5.4 |
| 2 | 1 Forecast ingestion + 2 Forecast timing | **YES** | DONE 2026-07-05. Research report in chat; findings in Sections 1-2 and HANDOFF v5.5 |
| 3 | 3 Historical database + 4 Calibration engine | No | DONE 2026-07-05. P0 calibration sign bug found and fixed; schema in HANDOFF 7b |
| 4 | 5 Probability modeling + 6 Forecast uncertainty | No | DONE 2026-07-05. Thin-tail P1 found, TAIL_FLOOR guard shipped; CRPS logging live |
| R | Reddit deep research (owner runs in ChatGPT) | n/a | PROMPT DELIVERED 2026-07-05 (REDDIT_RESEARCH_PROMPT.md). Owner runs it; findings ingest at Batch 6 |
| 5 | 7 Provider weighting + 8 Market modeling | Optional | DONE 2026-07-05. CLV shipped; microstructure measured; weights kept pooled |
| 6 | 9 Market timing + 10 Expected value | Optional | Fee formula verified against current Kalshi fee docs; Reddit findings ingested here |
| 7 | 11 Auto learning + 12 Machine learning | No | DONE 2026-07-05. Gate + drift alarms shipped; ML gated at 3000 records/2 seasons |
| 8 | 13 Backtesting + 14 Risk management | No | DONE 2026-07-05. Quarantine amendment + exposure caps shipped; kill criteria pre-registered |
| 9 | 15 Weather science + 16 Advanced statistical ideas | **YES** | Literature-flavored; which meteorological inputs actually pay |
| 10 | 17 Trading engine + 18 Monitoring | No | DONE 2026-07-06. LIVE_TRADING_SPEC.md + full monitoring suite + Telegram shipped |
| 11 | 19 New feature brainstorm + 22 Value of information | No | DONE 2026-07-06. VoI roadmap ranked; mean_hist shipped; five features killed |
| 12 | 20 Software architecture (incl. security and privacy) + 21 Quant-fund capstone + final report | No | Closes the audit: consolidated report, doc sync, README refresh |

Research mode meaning: the owner enables Claude's Research feature for that session because the batch needs broad multi-source web investigation, not just a couple of lookups.

---

## Section 0: Data Integrity and Measurement Audit  [Batch 1]  Status: [x] COMPLETE 2026-07-04

**Verdict (deliverable 4):** the historical dataset is TRUSTWORTHY. All 73 pre-audit resolved records were logged exactly once each (HIGHs at lead 0, LOWs at lead 1), settled from Kalshi's own `result`/`expiration_value`, with no duplicates, correct LST windows, and correctly labeled leads. Contamination is limited to 5 Houston records priced off the wrong station (IAH vs Hobby). The alarming dashboard discrepancy found mid-audit (+$56 shown vs -$53 real) was a GitHub Pages serving failure, not a data problem: the committed state and committed HTML were correct. Full fix list in HANDOFF v5.4; per-item findings below.

### 0.1 API reliability  [x]
- Retry logic: `fget` 3 tries then None with console-only notice. Callers degrade silently (city dropped, pagination truncated). Mitigated: per-city fetch failures now surface in a header health strip; zero ladders now aborts the run (exit 2) instead of publishing a fake sit-out board. Kalshi pagination cap (60 pages x 200) currently consumes well under the cap; truncation risk documented.
- Duplicate requests: none material (one events sweep, one ensemble call per model/city, one settlement call per due event). Stale cached responses: none; no caching layer exists.
- **P1 found and fixed:** any crash exited 0 in CI, so the commit step ran and a broken run published as healthy. Crashes now exit 1.

### 0.2 Forecast data integrity  [x]
- LST shift verified by construction and live probe: clock 00:00 CDT maps to LST 23:00 prior day; Phoenix shift is 0 year-round; CLI day boundaries correct for HIGH and LOW at all leads. `forecast_days=10` covers lead 0-4 with margin. `temperature_unit=fahrenheit` confirmed on the wire. Member pooling confirmed live: 31+51+40+21 = 143 members, matching docs.
- Issue-time metadata: Open-Meteo does NOT expose model run/issue times; recorded as a permanent caveat for Batch 2 (timing) and Batch 8 (backtesting).
- Duplicates impossible in predictions (keyed map); overwrite semantics now governed by the freeze guard.

### 0.3 Kalshi market data  [x]
- Strike-field parsing (`floor_strike`/`cap_strike`/`strike_type`) verified against live bucket shapes; buckets missing bid or ask are skipped (one-sided books excluded, conservative). Canceled/voided markets: `resolve_pending` requires every bucket to settle yes/no before writing (retries otherwise); a voided event would remain pending forever rather than corrupt records; acceptable, monitor.
- **P0 found and fixed:** two ticker generations coexist; parsing only `KXHIGHT*` made 7 of 20 HIGH ladders (AUS, CHI, DEN, LAX, MIA, NYC as KXHIGHNY, PHIL) invisible since v1, including the most liquid markets. Parser now accepts legacy `KXHIGH*`/`KXLOW*` plus an NY -> NYC alias; verified live (80 ladders vs 33).
- Market timing facts captured: next-day markets list at 14:00 UTC the day before; markets close ~06:00 UTC after the target; settlement typically lands the day after the target (~19:00 UTC expected-expiration pattern).

### 0.4 Weather station validation  [x]
- All 20 cities verified 2026-07-04 against each market's `rules_secondary` CLI product. 19 match config coordinates (NYC=CLINYC Central Park, CHI=CLIMDW Midway, AUS=CLIAUS Bergstrom, PHIL=CLIPHL, DAL=CLIDFW, DC=CLIDCA, etc.).
- **P1 found and fixed:** Houston settles at HOBBY (`CLIHOU`), config pointed at IAH 28 km away. Coordinates and label corrected; 5 existing HOU records carry the IAH regime and will roll out of the 30-settlement lookback naturally.
- Station-change detection: re-verify CLI products whenever Kalshi rules text changes (note added to HANDOFF section 6).

### 0.5 Data leakage  [x]
- Calibration ordering is leak-free by construction: `calib_params` learns only from `resolved` (settled) records and is applied to later scoring; verified.
- **P0 found and fixed (measurement leakage):** every run overwrote each logged prediction with the freshest forecast, so the tracker would have scored near-settlement boards rather than actionable ones. Empirically this had fired ZERO times on existing data (each record was logged exactly once thanks to the timing quirks), so history is clean, but the next schedule change would have poisoned it. Plays now freeze at first non-empty log with `plays_lead`/`plays_logged_at`/`plays_model_version` stamps; buckets/mean/sigma still refresh for calibration.
- Brier-vs-market baseline uses the market price at the record's last refresh (near-close): a conservative benchmark that flatters the market, not us. Documented, acceptable.

### 0.6 Timestamp audit  [x]
- **P0 found and fixed:** `lead` and the realized guard's local hour derived from the runner's UTC date (`dt.date.today()` on a UTC runner). After 00:00 UTC the runner date is tomorrow in every US zone, so evening runs mislabeled every market by one day and realized-guarded away ALL next-day logging. LOW capture literally depended on the morning cron drifting past Kalshi's 14:00 UTC listing (Jul 2: drifted to 14:13, LOWs captured; Jul 3: 14:07, missed; Jul 4: 13:26, missed, so Jul 4 LOWs and all of Jul 5 were never going to be logged). Leads/local hour now come from each city's own clock.
- Cron drift measured from commit history: 12:00 UTC fired 13:26 (+1:26), 02:00 UTC fired 05:51 (+3:51). Crons moved off the hour and a 14:43 UTC capture run added.
- `logged_at` had no timezone marker; now explicit UTC (`...Z`). Resolution due-filter semantics (runner UTC date) reviewed and fine: early attempts simply retry.

### 0.7 Historical completeness  [x]
- Within the parser's (pre-fix) visible universe of 33 ladders/day, capture was 100% on Jul 2 and Jul 3 (33/33 each) and 13 on Jul 1 (setup day). Missing-by-design: 7 legacy HIGH ladders/day (17.5% of the true 40) plus every LOW whose capture lost the 14:00 UTC race. Missingness was systematic (by series naming and by clock), not random, and is closed by the parser + schedule fixes. Expected steady state going forward: ~40 records/day.

### 0.8 Data quality metrics  [x] gate SHIPPED batch 7 (owner-approved)
- Shipped now (display): header health strip on both pages (ladders found, cities fetched OK, named fetch failures) and a client-side staleness banner past 16h (also catches failed Pages deploys). Hard aborts shipped: exit 1 crash, exit 2 zero ladders, exit 3 corrupt state.
- SHIPPED in batch 7 after owner approval; AMENDED in batch 8 at the owner's direction to QUARANTINE rather than drop (gated records log fully with a `gated` flag, excluded from plays, calibration, alarms, and all report aggregates, resolved normally so every exclusion is auditable against its settlement later). Second refinement stands: the probability-sum test became a structural contiguity check computed before the quote filter (stronger for its purpose, no unquoted-tail false positives). Constants: GATE_MIN_LADDERS=25, GATE_MIN_MEMBERS=90, GATE_MIN_MODELS=3. Live false-positive rate at ship time: 0/80 ladders.

### 0.9 Dashboard and reporting integrity (ADDED)  [x]
- Recomputed every headline metric from raw state and diffed against rendered HTML: committed HTML matched state exactly (net -$52.99, 73 events, Brier 0.146 vs market 0.127).
- **P1 found and mitigated:** GitHub Pages served the PREVIOUS run's board (+$56.47, 46 events) for 12+ hours while the repo held the current one. Cause: the Pages deploy for the newest commit never landed (deploy-from-branch is fire-and-forget). Mitigation shipped: build-epoch staleness banner on both pages. Structural fix (deploy via Actions) logged in FUTURE.md section 4 for the Batch 12 infrastructure decision.

### 0.10 State-file resilience and commit race (ADDED)  [x]
- **P1 confirmed and fixed:** corrupted state JSON was renamed to `.bak` and replaced with an EMPTY state, which the workflow would then commit: a silent wipe of the visible track record. Now exits 3 with recovery instructions; a red run leaves the last good commit untouched. Schema is validated on load (predictions dict + resolved list).
- Commit sequence reviewed: `concurrency: group nimbus, cancel-in-progress false` serializes runs; rebase-then-push handles manual-dispatch interleaving; failed script means the commit step never runs (nothing partial is pushed).
- `resolve_pending` idempotency verified live: del-on-success, double-run produced zero duplicates and identical P&L.

### 0.11 Version-stamp integrity (ADDED)  [x]
- Baseline correction: all 73 records lacked RECORD-level stamps by design (only plays were stamped, and 23 of 77 plays predate the v4 stamp fix). Decision: no backfill; old records read defensively, and the calibration-relevant split is date-based anyway. Fixed forward: resolved records now carry record-level `model_version` and `first_logged`, and resolved plays carry their decision-time `lead`.

### Section 0 deliverables: all six delivered
(1) Data quality report: this section plus HANDOFF v5.4. (2) Corruption sources enumerated: silent exit-0 crashes, empty-state reset, Pages staleness, fget silent degradation, pagination cap. (3) Hidden-bias sources enumerated: legacy-ticker universe truncation, race-dependent LOW capture, prediction overwrite, HOU station offset, near-close market Brier baseline. (4) Trust verdict above. (5) Automated checks: shipped strip/banner/aborts plus the approval-gated scoring gate. (6) Pre-optimization fixes: all P0s shipped this batch. **GATE PASSED: later sections may proceed.**

---

## Section 1: Forecast Ingestion  [Batch 2]  Status: [x] COMPLETE 2026-07-05

Findings (research report in the owner's chat; endpoint facts re-verified live on 2026-07-05):
- Current stack confirmed sound: 4 pooled ensembles = 143 members exactly (GFS 31, ECMWF 51, ICON 40, GEM 21). `icon_seamless` serves ICON-EPS GLOBAL for US points (metadata id `dwd_icon_eps`, 00/12z): a blend name, one effective model here; consistent with observed member counts, mapping inferred.
- Single-aggregator dependency quantified and accepted: usage ~320 calls/day vs Open-Meteo's 10,000/day non-commercial tier (~3%). Outage behavior already surfaces via the batch 1 health strip; a full-provider outage fails loudly.
- Provider verdicts for THIS use case (predicting NWS CLI max/min at 20 verified stations): ADD as reference: NBM (NOAA's station-calibrated blend, the only free source with per-station calibration) and HRRR (sharpest lead 0-1 CONUS model). SKIP: Tomorrow.io, WeatherAPI, OpenWeather, Visual Crossing, Meteostat, Pirate Weather: paid or re-serving the same global models with no station calibration, no independent information. RESERVE: NWS api.weather.gov observations for the nowcasting item (FUTURE section 5).
- SHIPPED: `ref` field logs NBM + HRRR CLI-day values on every prediction (`ncep_nbm_conus` / `ncep_hrrr_conus`, verified live, 40/40 coverage at lead 1), and `members_by_model` logs per-model n/mean/sd. Both evidence-only: scoring untouched. Blend decision deferred to Batches 4-5 with settled-skill numbers (rule written into FUTURE section 5).
- Multi-model pooling question (does ICON+GEM add over GFS+ECMWF): now empirically answerable from `members_by_model` once settlements accrue; no action until then.

## Section 2: Forecast Timing  [Batch 2]  Status: [x] COMPLETE 2026-07-05

- Run provenance solved: Open-Meteo forecast responses carry NO run id, but `api.open-meteo.com/data/{id}/static/meta.json` exposes `last_run_initialisation_time` per model. SHIPPED: every record stamps `model_runs`. Metadata ids differ from ensemble names: gfs025 -> ncep_gefs025, icon_seamless -> dwd_icon_eps, gem_global -> cmc_gem_geps.
- Availability lags MEASURED live (single-day point estimates, re-check casually as data accrues): GEFS init+5.7h (6-hourly), ECMWF ENS init+8.2h (6-hourly, the slowest), ICON-EPS init+3.7h (00/12z only), GEM ENS init+6.6h (00/12z only), NBM ~+1.1h (hourly), HRRR ~+1.6h (hourly). The research report's ECMWF open-data delay question is thereby resolved by measurement.
- Cron-to-cycle map: 12:17 UTC = 06z GFS + 00z ECMWF/ICON/GEM. 21:38 UTC = COMPLETE 12z cycle (slowest lands ~20:12, 86 min slack, and +4h GitHub drift still beats every city's local midnight for LOW capture). 02:07 UTC = adds 18z GFS; ECMWF 18z lands ~02:14 so it is caught only when the cron drifts (it usually does).
- SHIPPED: capture cron retimed 14:43 -> 21:38 UTC. The 14:43 slot consumed zero new model data vs 12:17 (the 12z cycle had not landed) and existed only for the Kalshi 14:00 UTC listing race; 21:38 keeps the capture role AND upgrades it to the freshest data. Owner-behavior note: next-day plays now first-freeze on the 4:38 PM CT board, closer in time and information to the 9 PM check than 9:43 AM was.
- Trade-immediately-after-model-runs question: deferred to Batch 6 (market timing) where the CLV/price-snapshot design can actually measure market reaction; the reasoned prior is that the 21:38 board is the day's information peak for next-day markets.

---

## Section 3: Historical Database  [Batch 3]  Status: [x] COMPLETE 2026-07-05

- Architecture verdict: JSON-in-git AFFIRMED at this scale; the deliberate no-database constraint holds. Ideal-schema answer delivered as HANDOFF section 7b: full field reference for predictions/buckets/plays/resolved, era-optional fields by version, and the binding defensive-read contract (new REQUIRED fields need a migration note).
- Storage decisions from the brief's checklist: every forecast revision: NO (freeze governs plays; buckets keep last refresh; run provenance via `model_runs` is the honest substitute since issue-time-per-value is unknowable from Open-Meteo). Every Kalshi price update: NO at this scale; bucket bid/ask/oi at last refresh already stored per record; true CLOSE snapshot deferred to the Batch 5 CLV design. Per-model member data: SHIPPED as summaries (`members_by_model`), not raw members (bytes discipline). Settlements, station metadata, lead, liquidity: already stored or now stored.
- Growth math: ~40 resolved/day x ~1.2 KB = ~1.5 MB/month. Archive policy ratified (3 MB trigger, 120-day split to `weather_state_archive.json`, merge-at-load for reporting, calibration reads live file only); implement only when tripped.

## Section 4: Calibration Engine  [Batch 3]  Status: [x] COMPLETE 2026-07-05

- **P0 found and fixed: reconstruction sign.** `calib_params` rebuilt raw bias as `bias + bias_corr`; the correct identity is `bias - bias_corr` (corrected_mean = raw_mean + corr). Simulated on the exact learning loop: with a true +3.0 offset the old code converges to corr ~ -0.95 where ~ -2.57 is needed (fixed point s/(1+2s): a stable loop that permanently delivers about a third of the correction, so a 3 degree station offset keeps a ~2 degree error and trips the bias guard forever instead of healing). Zero live damage: every stored bias_corr is still 0.0 (no city has reached BIAS_MIN_N). HANDOFF 4b text corrected too (it documented the wrong sign).
- Lookback windowing fixed: most recent `BIAS_LOOKBACK` by TARGET DATE, not append order (settlement batches resolve out of order).
- Verified correct as-built: shrinkage n/(n+K); activation thresholds 5/8/15 behave as documented (live recompute: corr 0.0 at n=3, pooled sigma active at n>=15); Wang-Bishop sigma = sqrt(max(Var(raw errors) - mean(member variance), 0)) is structurally right, demeaning is correct because the mean is handled by the bias correction, and the (1+1/m) finite-ensemble factor is negligible at m=143; HIGH and LOW learn separately by design; rounding consistency holds (bias measured on float settlement, `round_nws` only for display/margin).
- Convergence check (fixed code, simulation): corr reaches -2.43 of an ideal -2.57 by n=40 with 1.0 degree noise; no oscillation.
- Seasonal split criteria defined for FUTURE section 5: revisit only when a city/kind has 60+ settlements spanning two seasons, and adopt a split only if it beats the rolling-30 window on held-out MAE. Elevation/urban-heat/provider-drift items from the brief: all absorbed by the per-city, per-kind settlement-learned correction; no separate machinery justified at this scale.
- Carry-forward to Batch 4: the psd/sigma uncertainty question (is dressing plus member spread double-counting) and the NBM-anchor evaluation once `ref` skill data exists.

---

## Section 5: Probability Modeling  [Batch 4]  Status: [x] COMPLETE 2026-07-05

- **Mechanics verified.** Bucket integration matches NWS half-up rounding exactly: integer bucket [lo,hi] maps to reals [lo-0.5, hi+0.5); Kalshi strike semantics confirmed (less than C means <= C-1, greater than F means >= F+1, between is inclusive); the ladder partitions the real line so kernel mass sums to 1 by construction (confirmed 1.000 on every resolved record and live). Rounding bridge consistent: bias and margin use the float settlement, `round_nws` is display-only. `in_bucket` was dead code, removed.
- **Method zoo verdict at this data scale (~10 settlements per city):** the current engine already IS the standard from the forecasting literature: kernel-dressed multi-model ensemble (Roulston-Smith dressing, Wang-Bishop second-moment bandwidth). Plain Gaussian N(mean,psd): rejected, loses frontal-day bimodality the member cloud carries for free. Raw member counting: rejected in v4, stands. EMOS / NGR / quantile regression: needs hundreds of cases per station and collapses to Gaussian shape, revisit only at 1000+ pooled settlements. BMA per-model weights: this is Batch 5's question and `members_by_model` (batch 2) is its evidence base. Gradient boosting / distributional NNs: thousands of cases, Batch 12 gate stands. CRPS optimization: the one live alternative, as a FITTING criterion for sigma rather than a new model; per-event CRPS is now LOGGED (closed-form Gaussian approximation from mean/psd) so the CRPS-fit vs moment-matching experiment is runnable at the retune checkpoint (rule in FUTURE 2b).
- **P1 found, thin tails, guard shipped.** Buckets stated at 0-2% (avg 0.3%) realized 6.8% (n=118, Wilson lower bound 3.5%); the 2-5% bin realized 11.8% (n=34). Caveat stated: tail misses cluster inside busted ladders, so effective n is smaller and the magnitude is directional. Mechanism is split: early records were priced with the 1.1 degree default sigma (self-healing: learned pooled sigma is now 1.7-2.1) plus Gaussian SHAPE, which no amount of settled data can teach fat tails. Shipped: `TAIL_FLOOR` clamp (0.015) on edge and p_win computation only; displayed and logged mp stay raw so calibration keeps seeing the true model. The clamp can only shrink a stated edge (max ~1.5 points). Honest counterweight: actual tail plays are 7W-2L for +$29 (n=9), so this is forward insurance against a measured bucket-level mispricing, not a response to losses.
- Resolved buckets now carry `rep` (ordering midpoint), enabling ordered proper scores (RPS) retroactively in Batch 9.

## Section 6: Forecast Uncertainty  [Batch 4]  Status: [x] COMPLETE 2026-07-05

- **Double-counting question settled (Batch 3 carry-forward):** psd = sqrt(member variance + kernel variance) where kernel variance is DEFINED as realized MSE minus member variance, so total predictive variance is moment-matched to realized error variance. Not double counting; it is the Wang-Bishop construction working as intended.
- **Dispersion diagnostics (n=40 records with stored sigma):** overall mean(z)=-0.04, sd(z)=1.25, so applied spread underestimated realized error variance by ~56% in the early default-sigma era. By kind: HIGH sd(z)=0.84 (slightly conservative), LOW sd(z)=1.60 with mean(z)=+0.60 (LOW forecasts run warm and overconfident). These are precisely the errors the per-city bias correction and per-kind sigma learning are built to remove; the diagnostics say the learners are pointed at the right targets.
- **Spread-skill:** corr(member sd, |error|) = +0.14 at n=40: too noisy for any conclusion. Formal check written into the retune checkpoint (FUTURE 2b): needs n>=100 and a per-lead split.
- **Model disagreement:** per-model means now land automatically via `members_by_model` (batch 2); inter-model disagreement becomes computable history for the Section 19 no-trade classifier without further code.
- **Sizing verdict: NO explicit uncertainty multiplier on units.** Uncertainty already enters the only honest way: wider psd flattens the distribution, which shrinks |mp - mid| edges, which shrinks size through the existing edge bands. A second sd-based penalty double-counts when calibration is honest and papers over miscalibration when it is not. The calibration table remains the enforcement mechanism. (The retired `tier_for` sharpness weight stays retired.)
- Per-event `crps` and `psd` now stored on resolved records for the sigma experiments and future monitoring tiles.

---

## Section 7: Provider Weighting  [Batch 5]  Status: [x] COMPLETE 2026-07-05

- **Current weighting documented:** implicit member-count weights: ECMWF 51/143 = 36%, ICON 28%, GFS 22%, GEM 15%. Verdict: KEEP pooled equal-member weighting. Member count is a defensible prior (more members carry more distributional information) and equal-weight multi-model pools are notoriously hard to beat; the community evidence agrees (every quoted sharp in REDDIT_FINDINGS.md blends multiple models, one blends our exact six, none reports single-model wins).
- **Adaptive weighting is data-gated with explicit math:** distinguishing two models whose daily-extreme MAE differs by 0.3 degrees (paired-difference sd ~1.5) at 80% power needs ~200 paired settlements per comparison split. Pooled across 20 cities that is ~2 months of full-universe capture; per-city splits need most of a year. `members_by_model` (batch 2) is the ledger that makes this a query, not a project.
- **Eventual weighter spec (write-once, implement-later):** per-member kernel weights in `dressed_prob`, weight floor 10% and cap 45% per model so a hot streak cannot zero out or dominate, learned pooled-by-kind first, per-city only past ~100 settlements per cell, and every weight change is a MODEL_VERSION bump.
- Status of the early skill table: still empty because the audit build is NOT deployed (0 resolved records carry members_by_model). Populates automatically after commit.

## Section 8: Market Modeling  [Batch 5]  Status: [x] COMPLETE 2026-07-05

- **Microstructure measured, not assumed (80 ladders, 480 buckets, live):** spread p25/median/p75/p90 = 1/1/3/5 cents; OI p25/median/p75 = 142/488/1451; 61% of buckets clear MIN_OI=300. Reconciliation with the community's "liquidity is brutal": their pain is SIZE and market orders eating thin books; at paper scale, top-of-book with the cost gate's half-spread + fee + 1 cent cushion covers the p75 spread. Revisit at $100-unit scale (FUTURE section 2 already caps that path).
- **Penny-trap reconciliation:** the community's $0.10 minimum price rule is enforced here economically, not by knob: the 0.02<mid<0.98 gate, the half-spread term (a 1c/15c book fails PLAY_NET_EDGE by construction), and TAIL_FLOOR jointly kill the trade class they warn about. No knob change.
- **CLV analog SHIPPED (the batch's build item):** resolved plays now carry `close_mid` and `clv` = signed movement of the mid toward the position between the frozen entry board and the record's final actionable board (HIGHs: the morning-of 12:17 board; LOWs: the prior-evening 02:07 board). Evaluation rule, pre-registered: at 100+ clv-bearing plays, beat-close rate above ~52-53% with positive average clv is the early edge signal (the win/loss ledger needs thousands of plays to say the same thing). Verified by a network-free unit test and a live resolve; legacy single-log records correctly report clv=0.
- **Snapshot design verdict:** full per-run price time series deferred to the always-on-runner era (FUTURE 6.5); the two-point entry/close capture answers the decision-relevant question at ~40 bytes per play. Order-book imbalance, momentum, and mean-reversion studies from the brief are explicitly parked behind that infrastructure gate.
- Near-settlement efficiency assumption REINFORCED by community reports of 1-minute-data flash moves (REDDIT_FINDINGS.md Q1): mornings and mid-probability buckets remain the hunting ground.

---

## Section 9: Market Timing  [Batch 6]  Status: [x] COMPLETE 2026-07-05

- **Reasoned prior stands on measured lags (batch 2):** the 21:38 UTC board is the information peak for next-day markets (full 12z multi-model cycle in by ~20:12); the 02:07 board adds 18z GFS; the 12:17 board rides the overnight cycle. CLV (section 8) is now the instrument that TESTS this prior instead of arguing about it: if the market systematically moves toward our 21:38-frozen positions by the final board, the timing edge is real and measured.
- **INTRADAY_HIGH_CUTOFF=14 verdict: KEEP.** Daily maxima typically print 14:00-17:00 LST, so a 14:00 cutoff conservatively refuses bets once the outcome is partially realized. Deriving per-city cutoffs from time-of-max climatology adds complexity for a class of bets (same-day afternoon HIGHs) that nowcasting (FUTURE 5) will serve properly; the community's METAR-polling tool (~87% claimed signal accuracy, thin evidence) confirms that is where same-day money actually lives.
- **The community's "DST edge"** (standard-time settlement windows) is not an edge available to us: the LST windowing already prices it correctly. The two actual DST transition days stay no-bet per FUTURE known weaknesses.

## Section 10: Expected Value  [Batch 6]  Status: [x] COMPLETE 2026-07-05

- **Fee model verified and corrected (P2 in size, P1 in principle):** the series API states `fee_type quadratic, fee_multiplier 1` for this series (authoritative, stamped 2026-04-10). Old code rounded 0.07*p*(1-p) to the cent PER CONTRACT: undercharged ~0.47c/contract near 30c mids (gate too loose exactly where mid-probability plays live) and overcharged ~0.25c at 50c. Shipped: `fee()` returns the exact rate for the cost gate; `resolve_pending` applies the true trade-level round-up (ceil). Ceil can only overstate paper costs: conservative. Maker and settlement fees: none observed for this series; re-verify at live-order time.
- **Kelly audit:** at 1u = $10 = 2% of the $500 bankroll, current sizing runs ~1/6 to 1/13 of full Kelly across representative bands (e.g. entry .55 / p_win .66: f* = 24.4%, a 2u stake is 0.16 of that; entry .85 / p_win .90: f* = 33%, 2u = 0.12). Verdict: sane fractional-Kelly territory, no change, and consistent with the FUTURE section 2 scaling guardrails (1u stays 1-2% of CURRENT bankroll).
- **Vig removal: correctly absent.** Fair value comes from the calibrated model; the market price plus costs is only the hurdle. Ladder overrounds never enter pricing (re-verified: the bias guard's market mean is scale-invariant to uniform vig).
- **Probability-error propagation:** handled by the guard stack, not by formula: TAIL_FLOOR (batch 4) for shape error, SUSPECT_EDGE for implausible edges, WINPROB_CAP for stated-confidence ceilings, and the calibration table as the audit trail. Uncertainty-adjusted EV is already the psd pathway (batch 4 verdict).

---

## Section 11: Auto Learning  [Batch 7]  Status: [x] COMPLETE 2026-07-05

- **What already learns automatically (affirmed):** per-city/kind bias correction and kernel width, rolling 30 settlements by target date, shrinkage n/(n+5), activation at 5/8/15, verified in batch 3. That IS continuous recalibration at the right granularity for this data volume.
- **Drift detection SHIPPED as four display-only alarms** on the results header: (A1) recent Brier gap to market widening >+0.05 (needs 180+ buckets, recent = last 120); (A2) any probability decile off stated by >20 points at n>=25; (A3) rolling sd(z) outside [0.7, 1.4] over the last 40 psd-bearing records; (A4) learned correction jumping >1.0 degree between runs at n>=8 (new `calib_snapshot` state key). Coarse first-pass thresholds; retune at the 2b checkpoint.
- **Governance verdict:** automatic retraining beyond the existing learners is REJECTED. Alarms inform; knob changes happen only in owner sessions against pre-registered criteria (section 13's discipline) with a MODEL_VERSION bump. A system that silently retunes itself cannot be audited by its own track record.
- Adaptive provider weights: remains data-gated per section 7; the alarm framework will carry a per-model skill alert once `members_by_model` history exists.

## Section 12: Machine Learning  [Batch 7]  Status: [x] COMPLETE 2026-07-05

- **Verdict: not justified yet, and here is the honest why** (the brief demanded the explanation): (1) sample size: 40 records/day nominal, but one synoptic day correlates cities, so effective independent n is ~5-10/day; XGBoost/LightGBM/NN distributional models over ~15 features against a STRONG physical baseline need thousands of effective cases to beat it out of sample rather than memorize it. (2) The baseline is not naive: a bias-corrected, kernel-dressed 143-member multi-model ensemble is close to the efficiency frontier for station daily extremes; published post-processing gains over it are fractions of a degree and need seasons of training data. (3) Overfit asymmetry: a false ML "improvement" costs real calibration trust; a delayed true improvement costs a few basis points of edge for a few months.
- **Pinned revisit gate:** 3000+ resolved records spanning at least two seasons, walk-forward-by-date validation, adoption only on out-of-sample CRPS AND Brier improvement over the then-deployed baseline. Most plausible architecture when it comes: a small residual corrector (predict the bias residual from regime features) layered on the ensemble, not a replacement.
- **Feature ledger check (this section's real deliverable): COMPLETE, zero new code.** Every input a future model needs is already logged per record: lead, kind, city, member sd, sigma, per-model means (disagreement), NBM and HRRR deltas (ref), market mid/spread/oi (buckets), date. The audit's job was making sure the training data exists by the time the sample-size gate opens; it does.
- Stdlib-only constraint acknowledged: lifting it (sklearn on the Action) is a one-line mechanical change but a deliberate Batch 12 governance decision.

---

## Section 13: Backtesting  [Batch 8]  Status: [x] COMPLETE 2026-07-05

- **Bias sweep of the forward test (there is no backtester; the forward paper log is the instrument, audited against the brief's list):** look-ahead: closed by the play freeze; the one residual (market Brier baseline uses near-final prices) is conservative and documented. Survivorship: none; version stamps preserve every era. Settlement bias: none; Kalshi's own result/expiration_value settle everything. Calibration leakage: leak-free by construction (batch 3 ordering). Selection effects: now fully auditable end to end: bias-guard suppressions log their records, gate exclusions quarantine (this batch's amendment), TAIL_FLOOR and sizing/cap suppressions are reconstructible from stored buckets, and the realized guard is deliberately unlogged because its counterfactual would be a bet on partially known outcomes.
- **Determinism verified:** no randomness anywhere; the single set is sorted at creation; play ordering gained a ticker tiebreak this batch. Identical API inputs reproduce identical plays, so any future archived-snapshot replay is trustworthy.
- **Multiple-comparisons discipline PRE-REGISTERED** (the Results tab has 6+ breakdown tables; scanning them and tuning on the best cell is curve fitting): primary metrics are pooled CRPS and the whole-book model-vs-market Brier gap; a knob moves only if (i) motivated by an experiment or alarm already listed in FUTURE 2b, (ii) the supporting cell has n>=40 with a Wilson interval excluding the null, (iii) one knob family per checkpoint, (iv) the change lands in HANDOFF's new Decision Log with basis and version.
- **Unit harness matured this batch and immediately paid for itself:** it caught a same-minute pruning bug (cap pass deleting the previous run's frozen plays) before it ever reached the repo.

## Section 14: Risk Management  [Batch 8]  Status: [x] COMPLETE 2026-07-05

- **The measured risk picture, which rewrote the priors:** cross-city same-day error-sign concordance is 51% over 661 pairs, i.e. the "one air mass moves every city" fear is NOT in the data so far; cities are effectively independent. The real correlation sat INSIDE ladders: 31 of 44 played events stacked 2+ plays (max 5) on a single settlement number. And raw exposure was the dominant risk: 54.5u ($545) staked on one target date against a $500 bankroll.
- **Bootstrap at current sizing (n=103 plays):** ROI 90% CI (-33%, +34%), median max drawdown -$255, p95 -$461. At uncapped exposure, ordinary variance functionally ruins the paper bankroll inside a week; no edge conclusion is possible at this n and none is claimed.
- **SHIPPED: DAILY_UNIT_CAP=6.0 per target date and EVENT_UNIT_CAP=2.0 per ladder,** best plays first, overflow never logged, counterfactuals reconstructible, "cap trimmed N" chip on the header. Aligned with FUTURE section 2's own 4-6u guidance; the FUTURE scaling ladder and 1u=1-2%-of-bankroll rule re-affirmed against the bootstrap.
- **Kill criteria pre-registered (falsifiability):** at 150+ resolved plays under the audit build, stop scaling and return to the lab if the bootstrap 90% CI on fees-inclusive ROI sits entirely below -8%, or the model-vs-market Brier gap remains positive at 800+ non-gated buckets. Written into FUTURE section 2.
- Tail/black-swan exposure: bounded per event by EVENT_UNIT_CAP and per day by DAILY_UNIT_CAP; the worst single day is now -6u by construction (was -54.5u).

---

## Section 15: Weather Science  [Batch 9]  Status: [x] COMPLETE 2026-07-06

Research-mode session; report in the owner's chat (Rasp and Lerch 2018, Vannitsem et al. reviews, NBM/MOS docs, Allen et al. 2021). Ranked verdicts for THIS system:
- **Add-now tier: none as model inputs.** Every auxiliary surface variable evaluated (cloud cover, wind speed, dew point, snow cover, soil moisture, frontal timing, regime indices, upper-air/satellite) fails the same test at leads 0-2: the mechanism is already priced into the ensembles' 2m members, and the literature's gains from auxiliary predictors (mid-single-digit CRPS percent at best) materialize only through ML post-processing at thousands of training cases (Rasp and Lerch scale), which section 12 already gates at 3000+ records.
- **UHI and station siting:** absorbed by the per-station settlement-learned bias correction by construction; a separate predictor would double-count. Verdict: handled.
- **The two data routes that actually pay:** (1) station-calibrated and finer models: NBM and HRRR, logged since batch 2, promotion still gated on 50 ref-bearing settlements; (2) intraday observation truncation (nowcasting), the single highest-VoI item, consistent across the literature framing, the Reddit findings, and the FUTURE roadmap. SHIPPED the inert prerequisite (`STATION_IDS`, the verified CLI-to-ICAO map) and upgraded FUTURE section 5 into a staged implementation spec with a 30-event shadow gate and the midday-cron requirement. Not turned on: the current cron set has no run inside the 9am-2pm local window where truncation binds.
- Frontal-passage bust risk: the member cloud's bimodality carries it; the kernel preserves it (batch 4); no separate front detector justified. Snow/soil: winter-only relevance, parked in FUTURE with a November revisit note.

## Section 16: Advanced Statistical Ideas  [Batch 9]  Status: [x] COMPLETE 2026-07-06

Verdicts for all ten, sized to n~90 and stdlib:
- **RPS: ADOPTED as the ladder headline metric (SHIPPED).** Ordered integer buckets need a distance-aware proper score; per-bucket Brier scores a one-bucket miss and a five-bucket miss identically. Computed per resolved event (rep-bearing v6+ records), model vs mid-normalized market (devig for scoring only), rendered beside Brier. Unit-proven ordering: correct 0.05 < wrong-by-1 0.59 < wrong-by-2 1.16 vs flat market 0.40.
- **Reliability with Wilson 95% intervals: ADOPTED (SHIPPED).** Every calibration bin now shows its Wilson range and the Gap flags red only outside it: the anti-overreading tool for daily phone checks.
- **CRPS: already logging since batch 4;** stays the sigma-experiment currency. Log loss: skip (unbounded penalties at clamped tails mislead).
- **ECE: SKIP** at small n (binning artifacts dominate; the Wilson-barred reliability table supersedes it).
- **Bootstrap CIs: ADOPT, block-by-target-date** as the standard (a Batch 10 results tile). Batch 8's measured 51% cross-city concordance means naive and block agree here today, but block is the defensible default.
- **Hierarchical partial pooling: DEFER to 30+ settlements per city.** The current n/(n+5) shrinkage toward zero plus the pooled sigma IS crude partial pooling; full hierarchy earns its complexity only when per-city posteriors would differ from it materially.
- **EWMA / decaying-average bias (Cui et al., NWS adaptive MOS): PRE-REGISTERED 2b EXPERIMENT,** not switched. Literature supports both EWMA and windowed corrections; at n<=10 per city nothing in OUR data can prefer one, and the batch 8 governance rule (one knob family per checkpoint, n>=40 evidence) applies to the auditor's own research too.
- **Student-t dressing (df~5): the confirmed escalation path for the thin-tail finding,** still gated on the pre-registered 500-tail-bucket checkpoint; TAIL_FLOOR stays the interim guard.
- **Quantile mapping: SKIP** (member-wise QM needs long stable training archives; mean-and-spread correction is the right tool at this scale). **Copulas: SKIP** (measured independence across cities; within-event dependence already capped structurally).
- **Score decompositions: DEFER to 500+ buckets** (reliability/resolution split is noise below that).

---

## Section 17: Trading Engine  [Batch 10]  Status: [x] COMPLETE 2026-07-06

- Current engine is the owner's thumb at top-of-book; paper assumes taker-at-ask, which is CONSERVATIVE vs the community's maker-first reality (batch 6). Manual-era slippage instrument: bet-confirmation logging (priority 3 in the post-audit order); CLV covers market drift meanwhile.
- **Deliverable shipped: `LIVE_TRADING_SPEC.md`,** the binding contract for any future automation: entry gates (paper + 14-day shadow + always-on platform + secrets), idempotent client ids, maker-first with a 10-90c execution window and a 90-minute settlement no-resting buffer, pre-placement sanity bounds wired to the existing gate/alarm/staleness machinery, one-commit HALT kill switch, reconciliation-to-HALT, execution quality score, 50%-of-paper month-one sizing. Latency-dependent strategies declared out of scope by thesis.

## Section 18: Monitoring  [Batch 10]  Status: [x] COMPLETE 2026-07-06

- Coverage map vs the brief, all now live or data-gated-with-honest-empty-states: ROI + block-bootstrap 90% CI (deterministic seed), expected ROI = the stated-vs-realized cents-per-contract honesty tiles, calibration with Wilson intervals (batch 9), RPS headline (batch 9), CLV beat-the-close tiles, Forecast sources MAE table (per-model + NBM + HRRR: the promotion decision reads from here), API/data health strip + gate/cap chips (batches 1/7/8), drift alarms (batch 7), state size/record chips, new-plays-24h chip. Latency: not applicable on cron. Regime change: winter revisit note in FUTURE.
- **Telegram notifier shipped** (FUTURE item 4): fires per run only when both secrets exist, non-fatal on failure, includes top card, record, gated list, and first alert. Requires the owner to add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID repo secrets and paste the new run.yml.

---

## Section 19: New Feature Brainstorm  [Batch 11]  Status: [x] COMPLETE 2026-07-06

Triage test for all thirteen seeds: does it change a bet, a size, or a skip?
- **Killed as decoration:** market confidence score, market efficiency score (mid/oi/overround already display and change nothing), forecast volatility index (superseded by mean_hist), weather regime classifier (batch 15 verdict), portfolio optimizer (the exposure caps are the correct tool below a $5k bankroll; revisit only at multi-market live scale).
- **Already covered:** market anomaly detector (BIAS_TOL guard), automatic no-trade classifier (the integrity gate IS one; disagreement-based extension spec'd in FUTURE with a data-derived threshold rule), probability confidence interval (psd carries it; Wilson covers the bins).
- **Shipped cheap: `mean_hist`,** the run-by-run forecast revision trail (last 6 board means per record, ~150 bytes), which turns the surprise detector and the which-run-moved-the-forecast timing question into offline queries instead of features.
- **Spec'd for later:** surprise detector (alert when |mean jump| > 1.5 x psd between runs, from mean_hist), settlement-risk flag (station observations silent pre-settlement, bundled with nowcasting), execution quality score (LIVE_TRADING_SPEC section 7).

## Section 22: Value of Information (capstone addendum)  [Batch 11]  Status: [x] COMPLETE 2026-07-06

The post-audit roadmap. Every candidate kept, none collapsed; Impact and Effort labeled critical/moderate/negligible where the evidence supports it.

| # | Item | Expected impact | Effort | Prerequisite | Verdict |
|---|---|---|---|---|---|
| 1 | Intraday obs truncation (nowcasting) + midday cron | CRITICAL: the one same-day information source the market provably lags (literature + community) | Moderate | STATION_IDS (shipped); 30-event shadow gate | BUILD FIRST post-audit |
| 2 | NBM promotion decision | CRITICAL if NBM wins the sources table (station calibration is its whole design) | Low (anchor shift) | 50 ref-bearing settlements | DECIDE at 50, from the table |
| 3 | Bet-confirmation logging | MODERATE: makes tracked P&L equal taken P&L; unlocks slippage + shadow diffs | Low-moderate | none | Build second |
| 4 | EWMA bias + CRPS-fit sigma experiments | MODERATE: cleaner learners if they win held-out | Low | 100-settlement retune (2b) | Pre-registered |
| 5 | Student-t dressing | MODERATE: the shape fix TAIL_FLOOR insures against | Moderate | 500 tail buckets | Pre-registered escalation |
| 6 | HRRR short-lead blend | MODERATE at lead 0-1 only | Low | Same 50-settlement table | Decide with #2 |
| 7 | Private repo + Pages-via-Actions | MODERATE (privacy + deploy reliability) | Low | Batch 12 decision | Owner call, next batch |
| 8 | Always-on runner | CRITICAL for live, NEGLIGIBLE for paper | Moderate | Live intent | Pre-live only |
| 9 | Hierarchical pooling | NEGLIGIBLE until 30+/city | Moderate | data | Parked |
| 10 | Seasonal split + winter variables | NEGLIGIBLE until two seasons exist | Low | November | Parked |
| 11 | Multi-snapshot order-book capture | NEGLIGIBLE for the current thesis | Moderate | always-on runner | Parked |
| 12 | Additional ensemble providers | NEGLIGIBLE: re-serves the same global models | Low | none | Diminishing returns, skip |
| 13 | Extra surface variables as predictors | NEGLIGIBLE below thousands of cases | High | ML gate (3000+) | Skip until #14 |
| 14 | ML residual corrector | Unknowable before its gate | High | 3000 records, 2 seasons | Gated (batch 7) |
| 15 | Telegram pings, CLV, RPS, revision trail | already shipped | done | none | SHIPPED batches 5-11 |

The single-highest-return next build is #1; #2 is the highest-return DECISION and costs almost nothing because the evidence table already renders.

---

## Section 20: Software Architecture  [Batch 12]  Status: [x] COMPLETE 2026-07-06

- **Constraint audit: every deliberate constraint survives on merit.** Single file: KEEP (85 KB, and precisely what made 12 batches of surgical, str-replace-verifiable edits safe). Stdlib-only: KEEP, upgraded from taste to SECURITY CONTROL (zero third-party packages inside a contents:write workflow on a public repo = zero supply-chain attack surface); conscious lift points: the 3000-record ML gate or the live era, via Decision Log. JSON-in-git persistence: affirmed in batch 3 with the 3 MB archive policy. Caching, async, parallelism, containers: rejected at 3 runs/day with a 3-4 minute runtime; the Actions runner IS the container. Feature flags: the env-gated Telegram pattern is the house style. Retry/fault tolerance/observability: delivered across batches 1, 7, 8, 10 (loud exits, gate, alarms, strips, pings).
- **Security and privacy (the batch's owner decisions, clearance exercised):** repo stays PUBLIC through paper (exposure = paper betting history; Actions secrets stay hidden; raw access is the audit's own verification channel); PRIVATE is now LIVE_TRADING_SPEC entry gate 5, hard-required before any real order. Pages-via-Actions: DEFERRED one stable week post-deploy, then bundled with the privacy work (one variable at a time; the staleness banner guards meanwhile). Actions: major-tag pinning kept, SHA pinning listed for live-era hardening. Branch protection on main: recommended (Settings toggle, one click).
- **Testing SHIPPED: `test_nimbus.py`,** 14 network-free stdlib tests consolidating every hand-proven audit assertion, wired into CI ahead of board generation: a red suite publishes nothing. Versioning: MODEL_VERSION (behavior eras) + `cfg` CONFIG_HASH (knob fingerprint on every record and in the page header, shipped this batch) close the silent-knob-drift hole.

## Section 21: Think Like a Quant Fund  [Batch 12]  Status: [x] COMPLETE 2026-07-06

The scaled-down honest equivalents, most already built by earlier batches:

| Fund practice | Nimbus equivalent | Status |
|---|---|---|
| Experiment tracking | Decision Log (HANDOFF) + CONFIG_HASH per record | SHIPPED (b8, b12) |
| Model registry | MODEL_VERSION stamps on every play and record | SHIPPED (pre-audit + b1) |
| Forecast archive | records + mean_hist revision trail + model_runs provenance | SHIPPED (b2, b11) |
| Walk-forward optimization | pre-registered 2b retune protocol, one knob family per checkpoint | WRITTEN (b8) |
| Canary deploys / A-B | shadow mode spec + version-split analysis via stamps | SPEC'd (b10) |
| Post-trade analysis | CLV tiles + stated-vs-realized honesty tiles | SHIPPED (b5, b10) |
| Real-time anomaly detection | integrity gate + drift alarms | SHIPPED (b7, b8) |
| Research notebooks | the audit chats + this file as the lab notebook | LIVING |
| Feature stores, MLflow/W&B, HPO, microservices | declared NOT worth imitating at this scale (HPO is a curve-fitting machine at this n) | REJECTED with reasons |

The $10M-bankroll question answers itself in reverse: what a firm would build FIRST is exactly what this audit built: settlement-verified stations, leak-free measurement, pre-registered evaluation, exposure limits, kill criteria, and an audit trail. Alpha machinery comes after trust machinery.

---

## Section R: Reddit Deep Research (owner action, via ChatGPT)  [After Batch 4, ingest at Batch 6]  Status: [x] INGESTED 2026-07-05 (report archived as REDDIT_FINDINGS.md; cross-referenced into Sections 7-10, FUTURE 5-6, and known weaknesses; headline reconciliation: the community's favorite tail-fade strategy is exactly what our batch 4 tail measurement distrusts, TAIL_FLOOR is the bridge)

The owner will run a deep-research pass in ChatGPT (superior Reddit index) and paste findings back. The AI authors a detailed, copy-paste-ready prompt at the END of Batch 4. The prompt must request: links to every thread used, quoted comments, and per-viewpoint comment counts, with direct Reddit evidence separated from inference.

Scope the prompt will cover:
- Kalshi weather trader community intel: r/Kalshi and related subs, strategies people actually use, who the sharps are (the wethr.net crowd), and what edges they claim are gone vs alive.
- Settlement gotchas by city: station quirks, CLI report timing, disputes, known Kalshi settlement errors or rule changes.
- Fees and microstructure complaints: real fill quality, spread behavior, maker vs taker experiences at small size.
- Forecast tooling opinions: Open-Meteo reliability, HRRR vs global models for daily max/min, nowcasting practices.
- Kalshi API reliability reports and rate-limit experiences.
- Any public post-mortems of weather-betting models (what killed them).

Deliverable back into the audit: findings memo ingested at Batch 6, cross-referenced against sections 8, 9, 10, 15, and 17; anything actionable lands in FUTURE.md with priority.

---

*Maintenance rule: keep statuses current, keep severity tags on findings, and when an item ships move it into the HANDOFF.md changelog per the standing protocol. New ideas discovered mid-batch go to FUTURE.md immediately so they survive the session.*

## FINAL FINDINGS REGISTER (audit complete, 2026-07-06)

Every finding, its severity, and where it stands. Batch column = where found.

| # | Finding | Sev | Batch | Status |
|---|---|---|---|---|
| 1 | 7 of 20 HIGH ladders invisible (legacy ticker generations) | P0 | 1 | FIXED, verified live (33 -> 80 ladders) |
| 2 | Runner-UTC leads killed all next-day logging; LOW capture was a cron-drift race | P0 | 1 | FIXED (per-city clocks + 21:38 capture cron) |
| 3 | Every run overwrote logged plays (measurement leakage) | P0 | 1 | FIXED (freeze at first non-empty log); zero historical damage, verified |
| 4 | Calibration reconstruction sign error: loop stalls at ~1/3 of needed correction forever | P0 | 3 | FIXED pre-activation; simulation-verified; never fired live |
| 5 | Crashes exited 0 in CI; broken runs published as healthy | P1 | 1 | FIXED (red runs commit nothing) |
| 6 | Corrupt state silently reset the entire track record | P1 | 1 | FIXED (loud exit 3) + regression-tested |
| 7 | Houston priced at IAH, settles at Hobby (28 km) | P1 | 1 | FIXED; all 20 stations rules-verified |
| 8 | GitHub Pages served a one-run-stale board (+$56 shown vs -$53 real) | P1 | 1 | MITIGATED (16h self-banner); structural fix scheduled post-deploy |
| 9 | Kernel tails too thin: sub-2% buckets realized 6.8% (n=118, clustered) | P1 | 4 | GUARDED (TAIL_FLOOR); Student-t escalation pre-registered at 500 tail buckets |
| 10 | Uncapped exposure: 54.5u on one day vs $500 bankroll; 5-play single-ladder stacks | P1 | 8 | FIXED (6u/day + 2u/event caps); bootstrap p95 drawdown was -$461 |
| 11 | Gate destroyed the evidence needed to audit itself | P1 | 8 (owner-caught) | FIXED (quarantine); zero exclusions had occurred |
| 12 | Same-minute cap pruning could delete prior frozen plays | P1 | 8 (harness-caught) | FIXED pre-ship; now a committed regression test |
| 13 | Fee rounding wrong both directions (~0.5c near 30c mids) | P2 | 6 | FIXED (exact rate + trade-level ceil, series-API-verified) |
| 14 | Calibration lookback windowed by append order, not calendar | P2 | 3 | FIXED |
| 15 | logged_at lacked a timezone marker | P2 | 1 | FIXED (explicit UTC) |
| 16 | Dead code (in_bucket) | P2 | 4 | REMOVED |
| 17 | Play-sort tie nondeterminism | P2 | 8 | FIXED (ticker tiebreak) |

Trust verdict: the pre-audit historical dataset was sound (each record logged exactly once, settled authoritatively, stations correct except HOU's 5 records); every P0 was caught BEFORE it corrupted data, three of them within days of activating. The system now measures itself honestly enough to be worth improving.
