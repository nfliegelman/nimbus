# July External Weather Strategy Audit: Findings Report

**Status:** investigation report only. No behavior change is made or proposed for
immediate shipment. The single proposed patch (section 12) is strictly additive
instrumentation and is NOT implemented; it awaits explicit owner instruction.

**Executed against:** `audit/JULY_REDDIT_AUDIT.md` (the owner-supplied brief),
on repository state `5e895ac` (2026-07-28), `weather_state.json` at 964 resolved
records / 262 resolved plays, MODEL_VERSION `2026-07-25.v15-nowcast-live`,
CONFIG_HASH `5a84b45a`. All repository numbers below were recomputed read-only
in this session; all external observations were made live on 2026-07-28.
`weather_state.json` was not modified. `kalshi_weather.py` was not run.

**Revisions 2026-07-29 (language tightened, no finding changed):** four
statements below are narrowed so the record does not overstate the evidence.
(1) "The forecast layer is near-optimal / the leak is selection" is the
narrower claim that no tested challenger among the 8 pre-stated configs
(n=859, strict walk-forward) shows a meaningful improvement; an untested
forecast improvement could still exist. (2) The audit-era core book is -0.8
percent ON A 69-PLAY SAMPLE with a 90 percent block-bootstrap CI of [-19.8
percent, +19.2 percent]: consistent with breakeven, and also with meaningfully
negative or positive. (3) The registered gates are a path to EVIDENCE, not a
guaranteed path to profitability; "do not adopt" and "stop" are among their
honest outcomes. (4) Experiment ETAs must use each gate's own
binding-observation accrual rate, not total settlement volume; the computed
rates live in `audit/EXECUTION_REALISM_DESIGN.md` section 13.

**Companion documents:** `audit/REDDIT_FINDINGS.md` (2026-07-28 addendum
reviewed first, per its instruction), HANDOFF.md v6.19 through v6.24, FUTURE.md
dockets 1, 6, 7 and section 5. Several of the brief's "suspected gaps" were
closed by those versions in the days before this investigation ran; each such
claim is classified below as outdated rather than re-litigated.

---

## 0. Classification of the brief's load-bearing claims

| Brief claim | Classification | Evidence |
|---|---|---|
| Test suite: 46 tests, 0 failures | OUTDATED. Now 60 tests, 0 failures | Ran `python3 test_nimbus.py` this session: `Ran 60 tests ... OK` |
| 262 resolved plays, -$277.80, 40.46% win rate | REPRODUCED CURRENT FACT (unchanged since snapshot: no play settled between) | Section 2 |
| Stake $3,262.78 vs $3,320.00 discrepancy | REPRODUCED AND EXPLAINED: actual contract expenditure vs intended stake budget | Section 2.2 |
| Brier 0.1193/0.1013, RPS 0.5318/0.4020 | REPRODUCED (0.1194/0.1014 and 0.5323/0.4033 on today's slightly larger record) | Section 2.4 |
| Kind/side, lead, era, entry-band tables | REPRODUCED EXACTLY | Section 2.3 |
| Weather Bot v2: 103 trades, 59.2%, -$21.75 | VERIFIED CURRENT EXTERNAL FACT (live ledger observed 2026-07-28) | Section 1 |
| ~410% return claim | EXTERNAL CLAIM, NOT VERIFIABLE, materially undermined by the seller's own later bug admissions | Section 1.2 |
| 3-of-4 source agreement rule | EXTERNAL CLAIM; "agreement" is never mathematically defined in any public material | Section 5.1 |
| 95% rejection rate | EXTERNAL CLAIM, unverifiable; drifted from 90% (Apr) to 95%+ (current) | Section 1 |
| Source-agreement table (2/4 -61%, 3/4 -28%, 4/4 +1.5%) | REPRODUCED, and identified as an APPROXIMATION whose grouping is recipe-sensitive | Section 5.2 |
| `book0` schema `("ticker","mp","mid","yb","ya","oi","floor","cap","stype")` | VERIFIED CURRENT FACT (plus `hit` at resolve, plus record-level `at/mean/biased/lead`, plus `sd` since 2026-07-28) | Section 4 |
| `resolve_pending` drops `p_win` | OUTDATED: fixed 2026-07-28 (v6.19) with reconstruction fallback | HANDOFF v6.19 |
| `resolve_pending` drops `net`, spread cost, fee estimate | VERIFIED CURRENT FACT, with a measured live cost: the "stated edge" honesty tile has silently rendered +0.0c since it shipped | Section 4.2 |
| Exact historical provider probabilities reconstructable | CONTRADICTED: `members_by_model` stores only `{n, mean, sd}` per provider | Section 5.3 |
| Volume / depth / quote timestamps not retained | VERIFIED CURRENT FACT (open interest at decision time exists only in `book0`, 80 records) | Sections 4, 6 |
| Lead-0 aggregate (-51%) indicts the live nowcast | CONTRADICTED: all 33 lead-0 plays are legacy-era (v3-nimbus-calib); the v15 era's 6 plays are all lead 1 and none was priced through the nowcast floor | Section 2.5 |
| Six-play v15 era too small to judge | CONFIRMED, and sharpened: it is not only small, it is not even a nowcast sample | Section 2.5 |
| AIGEFS / AIFS availability | VERIFIED: both live on Open-Meteo's ensemble API; ALREADY LOGGED as evidence-only providers since v6.23 with a pre-registered adoption gate | Section 8 |
| `weather_state_archive.json` exists | NOT YET: policy amended and implemented v6.24, trigger 6 MB, live file 2.37 MB | HANDOFF 7b |

---

## 1. External evidence table (Deliverable 1)

All rows observed live 2026-07-28 unless noted. "Self-pub" means published by
the seller with no independent verification possible. Nothing was purchased.

| Claim | Source | Date | Verification status | Sample | $ risked | P&L | ROI | Fees treatment | Major caveat | Relevance to Nimbus |
|---|---|---|---|---|---|---|---|---|---|---|
| Weather Bot v2: 103 settled trades, 59.2% win rate, -$21.75 total | predictandprofit.io/results | ledger Apr 9 to Jul 28, 2026 | Observed live; self-pub auto-updated ledger with per-trade rows | 103 | not totaled (1-20 contracts/trade at cents) | -$21.75 | not computable (no capital base published) | not disclosed on ledger | pre-v2.2 rows were produced by accounting the author later called buggy | The only marked-to-reality external number: the flagship weather strategy is NET NEGATIVE on its own public record |
| Weather Bot v1 (retired): 12 trades, 25.0% win, +$1.42 | predictandprofit.io/results | same | Observed live; self-pub | 12 | tiny | +$1.42 | n/a | not disclosed | trivially small; retired | Win rate and P&L can disagree in both directions at this scale |
| Econ/inflation bot: 29 trades, 69% win, +$89.23 (+27 open marked "Win") | predictandprofit.io/results | same | Observed live; self-pub | 29 settled | not totaled | +$89.23 | n/a | not disclosed | open positions flatter the picture | Out of scope per brief; matters ONLY as the source of nearly all combined-account profit. Combined profit must not be read as weather profit |
| "Capital Deployed: $115.15" | predictandprofit.io | 2026-07-28 | Observed live | - | $115.15 at risk | - | - | - | - | The whole operation is micro-scale; smaller than Nimbus's paper book |
| ~410% return: $50 test balance to $255, ~180 trades, 63.4% win, quarter-Kelly | predictandprofit.io/blog/kalshi-weather-bot-profitability-math-2026 | post May 1, 2026 | EXTERNAL CLAIM; explicitly a "test balance"; never reconciled to the ledger | ~180 | $50 start | +$205 claimed | 410% of a $50 base | claims fees included ("realized 4.3pp after fees" vs modeled 7.1pp) | predates the v2.2 fill-accounting fix, i.e. computed while submitted orders were counted as fills | Do not use as an expected return. See 1.2 |
| 164-member ensemble (GFS 31 + AIGEFS 31 + IFS 51 + AIFS 51), "3 of 4 families agree", log line "required=3of4 -> PASS" | predictandprofit.io/how-it-works | current | Observed live; unverifiable without code | - | - | - | - | - | "agree" never mathematically defined anywhere public | Section 5.1 |
| Market-quality score: spread 30%, volume 20%, order-book imbalance 25%, model mispricing 25%, per-factor plus composite thresholds | predictandprofit.io/how-it-works | current | Observed live; thresholds withheld (in the $75 product) | - | - | - | - | - | no evidence the score predicts profit vs merely avoiding illiquidity | Section 6 |
| "rejects 95%+ of opportunities" | predictandprofit.io/how-it-works | current | Self-pub; no logs | - | - | - | - | - | earlier post said "approximately 90 percent"; figure drifted upward | Denominator (markets? sides? runs?) never stated |
| Min edge 0.10 (raise to 0.12 proposed), min price 0.20, ensemble confidence >= 0.30 from 50/50, fee <= 25% of expected return, spread <= ~$0.05 | blog posts "why-i-filter-out-90-percent", "month-1-results", "kalshi-weather-bot-profitability-2026" | Apr 2026 | Self-pub | - | - | - | - | fee formula quoted matches Kalshi's 0.07*C*P*(1-P) | thresholds asserted, not evidenced | Nimbus's cost gate is the economic equivalent (section 3) |
| 2-model convergence filter: GFS and AIGEFS within 0.15 of each other AND same side of 0.50; volume fell from 15-20 to 3-5 positions/week | blog "three-filters-kalshi-weather-bot-blowup" | May 3, 2026 | Self-pub | - | - | - | - | - | author: "P&L is still a small sample size" | The closest thing to a public agreement definition, and it is 2-source, not 3-of-4 |
| Fill-accounting bug: submitted order POSTs counted as trades, corrupting budget, P&L, and positions; fixed v2.2 "Only confirmed fills become trades" | blog "predict-and-profit-v2-2-reliability-release" + /changelog | May 16, 2026 | Self-pub admission | - | - | impact on prior ledger not quantified | - | - | ALL pre-v2.2 numbers (incl. the 410% post) were produced under this bug | The genuinely valuable external lesson: separate intended, submitted, and filled. Nimbus is paper, so its analog is the intended-vs-executable gap (section 6) |
| Stale-forecast trap: GFS upload windows create artificial model-market gaps; "the edge disappears once the bot catches up" | blog "weather-model-latency-traps" | Apr 2, 2026 | Self-pub | - | - | - | - | - | no dollar loss attributed | Nimbus already schedules runs off measured cycle-availability lags (audit batch 2); the residual open question is signal-to-board staleness measurement (section 7) |
| Reliability failures: silent API failure "drains your trading account", position dict-key bug causing repeat entries, silent AIGEFS ingestion crash, 2-week silent regression | blog posts Apr-Jun 2026 | Apr-Jun 2026 | Self-pub admissions | - | - | - | - | - | pattern of silent failures in live money paths | Corroborates Nimbus's loud-exit, gate, and test-before-publish design choices |
| Book $9.99 (31-member GFS era), source $75 ("Full Python Bot v2.3") | predictandprofit.io pricing section; Gumroad title | current | Observed live (Gumroad body JS-blocked; price confirmed on the site) | - | - | - | - | - | book documents the oldest architecture | Public materials are a sales funnel; the repo is a 3-commit README |
| "running 24/7 since early 2025"; a losing-trade anecdote dated Jan 14, 2025 | Gumroad snippet; blog "what-happens-when-the-bot-is-wrong" | current / Apr 12, 2026 | CONTRADICTED by the seller's own changelog (v1.0 March 2026) and ledger start (Apr 9, 2026) | - | - | - | - | - | unresolved chronology gap | Treat all pre-ledger history claims as unsupported |
| Developer's Reddit posts (initial returns, bankroll, city failures) | searched; blog confirms posts exist on r/algotrading etc. | - | NOT FOUND in this session's searches; no thread or username surfaced | - | - | - | - | - | absence of evidence, stated as such | The Mar/May 2026 stfarm quotes in REDDIT_FINDINGS sections 1, 3, 5 remain the archived Reddit evidence |

### 1.1 Weather-only isolation (brief item 6)

The public /results ledger tags each trade by bot, so weather-only performance
is separable and is the -$21.75 / 103-trade v2 row plus the +$1.42 / 12-trade
retired v1 row. Combined-account positivity comes from the econ bot (+$89.23)
plus unsettled positions optimistically marked "Win". Verdict: **the current
public stfarm weather strategy shows no evidence of after-fee profitability**
(brief question 1). ROI cannot be computed rigorously because cumulative dollars
risked and the capital base are not published.

### 1.2 What the ~410% measured (brief item 7)

Per the seller's own May 1 post: a $50 dedicated test balance grown to $255
across roughly 180 trades over an unspecified "multi-month window" with
quarter-Kelly sizing, claimed fees-inclusive. Not reconcilable with the live
ledger (which starts 2026-04-09 and shows -$21.75 on the current bot), not
independently verifiable, produced before the v2.2 fill-accounting fix, and
silent on deposits/withdrawals and realized-vs-open composition. Whether it was
weather-only cannot be confirmed. It did not persist: the ledger that follows
it is flat-to-negative. Classification: **external claim, unusable as an
expected-return input**. The interesting fact is not the number but that the
seller's later, more honest instrumentation walked it back.

---

## 2. Nimbus performance reproduction (Deliverable 2)

All figures recomputed this session from `weather_state.json` (964 resolved
records, quarantined records excluded exactly as `compute_report` excludes
them). The test suite passed 60/60 first.

### 2.1 Headline book

- Resolved plays: **262**, wins 106, **win rate 40.46%**
- Net P&L, fees inclusive (per-trade ceil): **-$277.80**
- Dollars actually risked (sum of contracts x entry): **$3,262.78**, ROI **-8.51%**
- Intended stake (sum of frozen `stake` budgets): **$3,320.00**, ROI on that base -8.37%
- CLV-bearing plays: 119, average CLV **+0.019**, beat-the-close 58/119

### 2.2 The stake-denominator discrepancy (brief item 3)

Both numbers are correct and mean different things:

- **$3,320.00 is intended stake**: the frozen `stake` field, `units x BASE_UNIT_USD`,
  the budget the sizing engine allocated.
- **$3,262.78 is actual contract expenditure**: `contracts x entry` where
  `contracts = int(stake // entry)`. Integer rounding leaves an average of
  about 22 cents per play unspent ($57.22 total). That residue is never at
  risk and never settles.
- `compute_report` (kalshi_weather.py line ~1422) uses **actual expenditure**
  as the ROI denominator, so **-8.51% is the dashboard's own convention** and
  the correct risked-dollar ROI. The -8.37% figure divides by budget rather
  than by risk. Neither denominator was chosen for flattery; the difference is
  1.7% of stake and does not change any conclusion. Legacy and current records
  use the same accounting (verified: the formula is applied at resolve time
  uniformly).

### 2.3 Segments (fees-inclusive, actual-expenditure ROI)

By model version (reproduces the brief's table exactly):

| Version | Plays | Win% | Staked | P&L | ROI |
|---|---:|---:|---:|---:|---:|
| blank/legacy | 23 | 34.8 | 320.17 | -132.59 | -41.4% |
| v3-nimbus-calib | 156 | 35.9 | 1749.44 | -50.65 | -2.9% |
| v11-audit12 | 3 | 66.7 | 34.48 | +23.06 | +66.9% |
| v12-capseed | 28 | 50.0 | 399.21 | -2.18 | -0.5% |
| v13-nowcast-shadow | 46 | 52.2 | 641.57 | -53.93 | -8.4% |
| v15-nowcast-live | 6 | 33.3 | 117.91 | -61.51 | -52.2% |

By kind and side: HIGH Buy NO 124 plays -0.2%; HIGH Buy YES 90 plays -11.5%;
LOW Buy NO 36 plays -35.6%; LOW Buy YES 12 plays +7.5%. By stored lead: lead 0,
33 plays -51.4%; lead 1, 86 plays -9.7%; missing/legacy lead 143 plays +1.9%.
By city: extremes are SATX +93.5% (n=26, +$317.59) and HOU +57.3% (n=23)
against MIA -72.9% (n=8), DEN -69.3% (n=6), DC -66.9% (n=14); at these ns the
city table is dominated by variance and by the legacy engine's frozen mistakes.
Entry bands: entries at or below 0.20 are 86 plays, -$232.61; every band above
0.20 combined is +$45 to -$45 depending on the cut. Stated-p_win bands
(via `play_pwin` reconstruction): the p_win <= 0.30 band is 71 plays -25.1%;
the > 0.90 band is 27 plays +15.5%; the 0.80-0.90 band is 52 plays -26.8%,
which is the single largest dollar leak (-$192) outside the cheap tail and is
already tracked as the mid-band/belly-sharpness question (FUTURE docket 3).

Net-edge bands **cannot be computed historically**: `net` is dropped at
settlement (section 4.2). Gross `edge` bands were computed as a proxy and show
no monotone pattern. Open-interest bands **cannot be computed historically**:
decision-time OI exists only inside `book0` (80 records, 6 plays, of which only
3 join cleanly). This is not a data request the record can answer; it is a gap
the instrumentation already shipping (book0) closes prospectively.

Era-controlled reads of the losing segments (brief item 18):

- **LOW Buy NO persists across eras**: legacy 11 plays -37.9%, audit-build 25
  plays -34.6%. Direction is stable but n=25 with a bootstrap CI spanning
  roughly -60% to -5%: real enough to keep watching, too thin to gate on.
  The registered docket 6 replay slate already contains the honest tests
  (NO-only, MIN_ENTRY floors, p_win floors) and needs no new candidate.
- **HIGH Buy YES is mostly a legacy artifact**: legacy 76 plays -12.1%
  (the cheap-tail YES longshots the audit already diagnosed), audit era 14
  plays -8.5%, small and dominated by the pre-committed cheap-entry cell.
- **Lead 0 is entirely legacy**: all 33 lead-0 plays carry
  `v3-nimbus-calib`. Zero lead-0 plays exist under the audit build. The
  -51.4% lead-0 cell says nothing about nowcasting, which shipped to live
  pricing only on 2026-07-25.

### 2.4 Brier and RPS vs market (brief item 4)

Reproduced: Brier model 0.1194 vs market 0.1014 over 5,784 buckets; RPS model
0.5323 vs market 0.4033 over 860 events. What these prove and do not prove:

- Both model `mp` and market `mid` in resolved `buckets[]` are the record's
  LAST refresh, i.e. the final actionable board. For a next-day market that
  board has seen overnight model cycles; for a same-day HIGH it has seen most
  of the day's observations. The comparison therefore measures "yesterday
  morning's forecast pipeline vs a price formed with information the model
  never had at decision time". Checkpoint 1 quantified the gap's mechanism
  (final board beats the model by 0.43 deg point MAE on obs-informed
  information) and the project retired the "Brier below market" gate on
  2026-07-16, with owner approval, for exactly this structural reason.
- What final-board scoring DOES prove: the market's closing distribution is
  sharper than the model's distribution. That is expected for any forecaster
  that stops ingesting data before the market stops trading.
- What it does NOT prove: that the model was wrong at the moment the play
  froze, or that selection is miscalibrated. The decision-time instruments are
  CLV (entry board vs final board: +0.019 average, a small favorable drift)
  and the calibration table (sd(z) near 1.0), both healthy.
- A true decision-time market comparison (model vs the mid on the SAME board
  the play froze on) is now possible prospectively via `book0` and the board
  `tape`, and retrospectively for the 80 book0-bearing records. It is the
  right future replacement for the final-board Brier headline and needs no new
  data collection.

### 2.5 The v15 era and the nowcast (brief item 18)

The six v15-era plays (2W-4L, -$61.51) are all lead-1, all Buy NO, frozen on
next-day boards. The nowcast floor applies only to same-day (lead 0) HIGH
pricing, so **none of the six was priced through the nowcast**. The v15 cell is
not merely too small to judge the nowcast promotion; it contains zero nowcast
trades. The nowcast's own instrument remains its paired shadow tally (promotion
evidence: 55 binding events, CRPS 1.28 vs 1.58, RPS majority 38-4), which
continues to accumulate. No action is warranted, and none is proposed.

---

## 3. Feature comparison matrix (Deliverable 3)

"External" reflects the public claims observed 2026-07-28 (paid code not
inspected, so external entries are claims, not verified implementations).

| Feature | External project (claimed) | Nimbus (verified in code/state) | Meaningfully different? | Evidence | Recommended action |
|---|---|---|---|---|---|
| Forecast sources | GFS ens + AIGEFS + ECMWF IFS ens + AIFS ENS | GFS ens + ECMWF IFS ens + ICON EPS + GEM ens (pricing); NBM + HRRR reference; AIGEFS + AIFS ENS logged evidence-only since v6.23 | Partially: the AI pair | how-it-works page; kalshi_weather.py ENSEMBLE_MODELS, AI_ENSEMBLE_MODELS | Keep the registered FUTURE 5 gate; add a replacement-stack race row when proposing (section 8) |
| Member count | "up to 164" | ~143 pricing members + 82 evidence members | No (headcount is not skill; Nimbus weights by measured MSE) | v14 skillpool | none |
| Bias correction | none described | per city/kind rolling-30 learned from settlements, shrunk, sign-verified | Yes, Nimbus richer | calib_params | none |
| Probability calibration | none described (raw ensemble fractions implied) | kernel dressing, Wang-Bishop sigma, tail clamp, calibration table with Wilson bars | Yes, Nimbus richer | audit batches 3-4 | none |
| Provider-specific probabilities | implied by "families agree" | NOT stored: only per-provider {n, mean, sd} summaries | YES: this is a real Nimbus gap for consensus testing | state census this session | Worth additive logging (section 5.4) |
| Source agreement rule | "3 of 4 families agree", undefined; public 2-model version: GFS vs AIGEFS within 0.15 and same side of 0.50 | none (pooled skill-weighted cloud; disagreement enters via spread and the bias guard) | Yes in mechanism; unproven in value | section 5 | Prospective shadow only, after provider-probability logging exists (section 11.1) |
| Trade rejection | min edge 0.10-0.12, min price 0.20, confidence floor, fee <= 25% of EV, composite quality score, "95% rejected" | cost gate (net edge after spread+fee+1c >= 0.04), MIN_OI, lead cap, bias guard, realized guard, tail clamp, integrity gate, exposure caps, suspect-edge cap | Same family, different composition; Nimbus's is settlement-audited | section 4 of HANDOFF | none now; docket 6 replay is the honest venue for stricter gates |
| City calibration | "city-level overconfidence" named as a known problem, no mechanism public | per city/kind learned bias and sigma, city_skill gate on 2u | Yes, Nimbus richer | calib_params | none |
| Open interest | volume-weighted quality score | MIN_OI=300 hard floor; OI frozen in book0 since v14 | Partially | code | Log-only extension via order book (section 6) |
| Volume | 20% of quality score | NOT captured | Yes: Nimbus lacks it | state census | Worth additive logging (section 6) |
| Spread | 30% of quality score, skip > ~$0.05 | half-spread charged inside net edge (economic, not a filter); spread implicitly bounded by the cost gate | Different mechanism, same economics; Nimbus's is priced rather than thresholded | score() | none; a spread cap variant can join docket 6 later if evidence warrants |
| Order-book depth | implied by imbalance factor | NOT captured (top-of-book only) | Yes: neither side proves depth matters at paper scale | section 6 | Worth additive logging, prospective |
| Order-book imbalance | 25% of quality score | NOT captured | Yes | - | Log with depth; no rule |
| Slippage | not modeled publicly | not modeled (paper assumes full fill at quoted top) | Same gap on both sides | section 6.2 | Estimated-fill fields once depth is logged |
| Forecast recency | S3-direct pulls, upload-window kill switch | run schedule derived from measured per-model availability lags; run provenance (`model_runs`) logged per record | Equivalent-or-better already | audit batch 2 | none |
| Quote recency | websocket claimed | run-stamp granularity (`logged_at`, `book0.at`, tape rows) | Yes at live scale, immaterial at 3 boards/day paper | section 7 | timestamps already adequate for paper; revisit at live gate |
| Signal recency | recheck before submission claimed | frozen-board design makes signal = board; no submission exists yet | Different problem shape (paper) | section 7 | measure board-to-cron-intent delay only |
| Fill confirmation | v2.2: only confirmed fills become trades (after the bug) | paper: no fills exist; LIVE_TRADING_SPEC already mandates reconciliation-to-HALT | Nimbus spec'd it before trading, external learned it after | LIVE_TRADING_SPEC | none |
| Fees | 0.07*C*P*(1-P), fee <= 25% EV filter | identical formula, exact rate in gate, per-trade ceil in P&L, verified vs series API | Equivalent | audit batch 6 | none |
| Sizing | quarter-Kelly claimed | edge bands + winprob cap + suspect cap + lead cap + proven-city gate (~1/6 to 1/13 Kelly measured) | Roughly equivalent conservatism | audit batch 6 | none |
| Exposure limits | per-series caps, daily loss kill switch | DAILY_UNIT_CAP 6u / EVENT_UNIT_CAP 2u seeded vs frozen history; kill criteria pre-registered | Nimbus richer and measured | batch 8 | none |
| Nowcasting | none | same-day observed-max flooring, shadow-gated then promoted (v15) | Yes, Nimbus ahead | v6.15 | none |
| Settlement | never mentions stations, CLI window, LST | station-verified, CLI/LST windowing, settlement-sourced wins | Yes, Nimbus ahead: this is the community's named bot-killer | batch 1 | none |
| Proper scoring | none | Brier, RPS, CRPS, calibration bins, sd(z) | Yes, Nimbus ahead | compute_report | none |
| CLV | none | per-play close_mid + clv, CI on average, money-gate leg | Yes, Nimbus ahead | v5.7 | none |
| Replay | none public | book0 selection replay + forecast backtester + board tape, all walk-forward | Yes, Nimbus ahead | v6.12, v6.20 | none |
| Experimental governance | none visible | pre-registration, gates, Decision Log, MODEL_VERSION eras, one knob per commit | Yes, Nimbus ahead | CLAUDE.md | none |
| Accounting honesty | learned via v2.2 bug | intended stake vs actual expenditure both stored; fees ceil conservative; BUT stated-edge tile broken by `net` loss | One real Nimbus defect found here | section 4.2 | THE proposed patch (section 12) |

The brief's central distinction ("Nimbus has the stronger forecasting engine;
the external project emphasizes deciding when not to trade") survives
half-intact. Nimbus's forecast, calibration, settlement, and measurement layers
are verifiably ahead. But the external project's rejection layer is not
evidently better either: its filters are asserted, its ledger is negative, and
its one public agreement definition is a 2-model band check. What the external
record genuinely contributes is (a) a negative result at micro scale that
corroborates how hard this market is after fees, and (b) the fill-accounting
post-mortem, whose paper-era analog (decision-time field preservation and
executable-fill realism) is where Nimbus's real measured gaps sit.

---

## 4. Current-state schema audit (Deliverable 4)

State paths: `weather_state.json` = `{predictions: {key: record}, resolved:
[record], calib_snapshot: {...}}`. Archive file not yet created (trigger 6 MB,
file 2.37 MB). Census this session: 964 resolved (860 carry members_by_model /
model_version-era fields; 104 oldest lack them), 81 pending, 262 resolved
plays, 80 records with book0, 0 with tape yet (shipped hours ago), 0 with
frozen book0.sd yet, 40 pending records carrying the AI evidence providers.

### 4.1 What each layer retains

- **Pending prediction:** code, kind, target, event_ticker, logged_at,
  first_logged, lead, mean, sd, psd, bias_corr, sigma, model_version, cfg,
  biased, offset, model_runs, members_by_model, ref, mean_hist, buckets[]
  (ticker, bid, sub, floor, cap, stype, mp, mid, yb, ya, oi; refreshed every
  run), plays[] (ticker, bid, sub, side, entry, **net**, edge, tier, units,
  stake, **p_win**, mp, mid; frozen), plays_lead / plays_logged_at /
  plays_model_version, optional book0 (+sd since 2026-07-28), tape, nowcast,
  nowcast_floor, gated.
- **book0:** `{at, mean, biased, lead, sd (new), buckets:[{ticker, mp, mid,
  yb, ya, oi, floor, cap, stype}]}`, write-once at the genuinely first healthy
  board, graded all-or-nothing with `hit` at resolve. Confirms the brief's
  guessed schema, plus the record-level scalars the brief did not know about.
- **Resolved record:** code, kind, target, lead, actual, mean, bias, sd, psd,
  bias_corr, sigma, crps, model_version, cfg, first_logged, model_runs,
  members_by_model, ref, mean_hist, buckets[{mp, mid, hit, rep}], plays[],
  optional nowcast scalars, book0 (graded), tape, plays_logged_at, gated.
- **Resolved play:** code, kind, target, sub, side, entry, tier, units, stake,
  contracts, won, pnl, margin, actual, mp, mid, edge, lead, p_win (retained
  since 2026-07-28; reconstructed via `play_pwin` for the 262 already
  settled), close_mid, clv, model_version.

### 4.2 Decision-time information lost at settlement (brief item 13)

Comparing the frozen pending play against the resolved play, `resolve_pending`
currently DROPS:

1. **`net`** (the post-cost net edge the play was sized on). Consequence,
   measured this session: `compute_report`'s stated-vs-realized honesty tile
   computes `edge_stated = sum(net x contracts) / total contracts` over
   resolved plays, and since NO resolved play has ever carried `net`, the live
   dashboard has rendered "**+0.0c stated edge /contract**" beside
   edge_real -1.5c since the tile shipped (v5.11, 2026-07-06). The tile's unit
   test passes because its fixture hand-writes `net` onto a synthetic resolved
   play (test_nimbus.py line ~84): a fixture/schema mismatch, the same failure
   class as the v6.19 `p_win` gap, caught the same way (reading the consumer
   against the stored schema). The tile is the project's designated
   overconfidence instrument; today it reads as "the model claims no edge",
   which is false: the model claims roughly +4 to +8c on the plays it takes,
   and nobody can currently see whether that claim is honest.
2. **`ticker` and `bid`** (bucket identity). Resolved plays are joinable to
   buckets only through `sub` string matching or price equality; the 3-of-6
   book0 join failure this session was exactly this.
3. The **cost decomposition behind `net`** (half-spread, fee estimate, 1c
   buffer) is not stored anywhere per play, at pending OR resolved stage. It
   is reconstructable exactly for book0-bearing records (yb/ya/oi are in the
   snapshot) and NOT reconstructable for the 256 plays before book0.
4. **Decision-time OI** for the play's bucket: in book0 only.
5. Already fixed in the days before this investigation (no action needed):
   `p_win` (v6.19), `plays_logged_at` (v6.20), decision-board sd (v6.22),
   entry-board prices for timing (tape, v6.20).

Fields required per experiment: consensus needs per-provider probabilities
(section 5.4, prospective); market quality needs volume/depth/imbalance
(section 6, prospective, new fetch); recency needs no new fields at paper
cadence beyond what exists (section 7); net-edge band analysis needs `net`
retention (section 12, one line plus tests).

Backward compatibility: every reader already uses `.get` with fallbacks (7b
contract), so additive retention is schema-safe by construction; the only
consumer that must change behavior is the honesty tile itself, which must
restrict its denominator to net-bearing plays or it will dilute toward zero
forever as mixed-era plays accumulate (detailed in section 12).

---

## 5. Source-consensus feasibility analysis (Deliverable 5)

### 5.1 What the external "3 of 4 agreement" means (brief item 9)

Not determinable. The public site prints the rule and a sample log line
("required=3of4 -> PASS") but never defines "agree": not as
expected-temperature proximity, not as bucket choice, not as directional
support, not as fee-adjusted edge. The only public, mathematically stated
agreement rule is the May 3 blog's TWO-model filter: GFS and AIGEFS bucket
probabilities within 0.15 of each other and on the same side of 0.50. That is
a probability-band + direction rule on raw ensemble fractions, with no fees,
no executable price, and no calibration. Distinguishing the brief's five
candidate meanings is therefore impossible from public material, and any
Nimbus experiment must define agreement independently. Per the brief's own
section 9.4 menu, the defensible primary definition is **cost-adjusted
support**: provider p minus executable price minus estimated cost clears the
gate's required edge for the selected side.

### 5.2 The earlier exploratory table: reproduced, and shown to be fragile

The brief's table reproduces EXACTLY on today's state, which also identifies
the recipe the earlier analysis used: per provider, a Gaussian
N(mean + record bias_corr, sqrt(provider sd^2 + record sigma^2)) integrated
over the play's bucket, "support" = probability on the play's side of the
market mid, over the 119 plays on records carrying all four provider
summaries:

| Support | Plays | Win% | Staked | P&L | ROI |
|---|---:|---:|---:|---:|---:|
| 0 of 4 | 1 | 0 | 9.96 | -10.62 | -106.6% |
| 1 of 4 | 3 | 33 | 34.32 | +26.18 | +76.3% |
| 2 of 4 | 26 | 15.4 | 305.63 | -187.64 | -61.4% |
| 3 of 4 | 39 | 48.7 | 535.27 | -147.68 | -27.6% |
| 4 of 4 | 50 | 56.0 | 711.98 | +10.77 | +1.5%, 90% CI [-23.2%, +26.6%] |

Fragility check, run deliberately: removing the dressing sigma from the
provider Gaussian reshuffles the groups (4-of-4 becomes n=43 at +15.6%; 3-of-4
becomes n=44 at -36.8%). The monotone-looking gradient survives, but cell
membership and magnitudes move materially under a defensible alternative
recipe. This is the concrete demonstration of the brief's warning: the table
is an approximation over summary statistics, not a replay of provider
probabilities, and it must not be promoted to evidence. It also blends eras
(119 plays span legacy and audit builds) and inherits every confound of the
lifetime book.

### 5.3 Can exact historical consensus be reconstructed? No.

`members_by_model` stores `{n, mean, sd}` per provider per record. It does not
store member lists, per-provider bucket probabilities, per-provider calibration
state, or per-provider predictive spread. The pricing path pools calibrated
members across providers before dressing, so provider-level dressed
probabilities were never computed, let alone stored. Exact provider-specific
YES/NO fee-adjusted edges therefore CANNOT be reconstructed for any historical
record. Classification: the brief's hypothesis 3 is confirmed. Any honest
consensus experiment requires prospective logging.

### 5.4 Minimum prospective instrumentation

At each play-freezing board (or more simply, alongside book0 at the first
healthy board), compute and store per provider, per ladder bucket, the dressed
bucket probability using the SHARED city/kind calibration (shared bias
correction, shared sigma): the brief's section 9.5 first-test option 2, chosen
because per-provider calibration state does not exist and fitting four
mini-models on current per-city ns would be overfit machinery. Proposed shape
(nested, versioned, additive):

```
book0.source_mp = {gfs025: [p1..pk], ecmwf_ifs025: [...], icon_seamless: [...],
                   gem_global: [...]}   # positionally aligned with book0.buckets
book0.source_mp_v = 1
```

Cost: 4 providers x ~8 buckets x ~7 bytes, roughly 250 B per record, well
inside the amended archive budget. From this plus book0's yb/ya/oi and the fee
helper, every agreement definition in the brief's menu (directional,
cost-adjusted, probability-band) is computable offline at replay time, so the
DEFINITION does not have to be frozen into the logging, only into the
experiment registration. Missing-provider behavior: a provider absent from the
pricing fetch logs no vector, and the replay counts support over present
providers with the absence recorded (the same convention the integrity gate
uses). This family is deliberately NOT part of the section 12 patch: one
instrumentation family per commit.

---

## 6. Market-quality instrumentation plan (Deliverable 6)

### 6.1 What Kalshi's read-only API offers (verified live 2026-07-28)

Documentation now lives at docs.kalshi.com (the old readme.io redirects there);
`openapi.yaml` is machine-readable. Verified by live unauthenticated calls
against `api.elections.kalshi.com/trade-api/v2` this session:

- **Single order book:** `GET /markets/{ticker}/orderbook`, NO auth required in
  practice (the guide says none; a live unauthenticated call returned 200
  despite the OpenAPI security block), `depth` param 0-100 (0 = all levels).
  Response: `{"orderbook_fp": {"yes_dollars": [[price, qty], ...],
  "no_dollars": [[price, qty], ...]}}`. Both sides are BID books: a yes bid at
  X is the no ask at 1-X, so the NO entry price and its resting size derive
  directly from the yes book and vice versa. NO timestamp in the response:
  capture time must be stamped client-side.
- **Batch order books:** `GET /markets/orderbooks?tickers=A&tickers=B`, up to
  100 tickers per call, unauthenticated (live-verified). All ~640 weather
  buckets would take ~7 calls per run; the priced ladders only, far fewer.
- **Market objects** (GetMarkets / nested in events) now carry `volume_fp`,
  `volume_24h_fp`, `open_interest_fp`, and top-of-book sizes
  `yes_bid_size_fp` / `yes_ask_size_fp`. Volume and best-quote quantity are
  therefore nearly free: no extra endpoint. The old `liquidity` field is
  deprecated (hardwired "0.0000"); no server-side depth aggregate or
  imbalance exists, so those are client-side computations.
- **Fixed-point migration (April 2026):** current market and book responses
  use `*_dollars` / `*_fp` STRING fields; the legacy integer-cent fields are
  absent from the endpoints tested. Any new capture code must parse these,
  and the design phase of a depth patch must first confirm which field
  generation the events endpoint Nimbus already consumes is serving (the
  running cron proves the current parser works; the point is only that new
  fields must not assume integer cents).
- **No historical order books exist** on any endpoint (confirmed against the
  full spec). Depth data begins the day Nimbus starts recording it; the brief's
  prohibition on fabricating history is structurally enforced.
- **Websocket `orderbook_delta` requires an API key** (free, but the handshake
  is always authenticated). Classification: live-era tooling, already noted in
  FUTURE 6; not needed at 3 boards/day paper cadence.
- **Fees re-verified:** `GET /series/KXHIGHNY` returns `fee_type: "quadratic"`,
  `fee_multiplier: 1`; the current fee schedule PDF (Feb 2026 edition,
  archived copy) states taker `ceil(0.07 x C x P x (1-P))` per trade and maker
  fees (0.0175 factor) only on flagged series, which weather is not. Nimbus's
  audit batch 6 fee model remains exactly right.
- **Rate limits:** token-bucket for authenticated keys (Basic sustains ~20
  reads/sec); unauthenticated limits are undocumented. At ~7 extra requests
  per run this is negligible.

What Nimbus could therefore capture prospectively, per the brief's item 14
list: volume (free field), best-price quantity (free field), multi-level depth
(batch endpoint), spread (already held), order-book imbalance (computed),
estimated average fill price and slippage for the intended contract count
(computed by walking the book), quote timestamp (client stamp at fetch),
executable fraction at the quoted price (computed). Authenticated order
placement is not required for any of it and is not proposed.

### 6.1b Proposed capture design (log-only, no rule)

Extend the decision-board snapshot rather than invent a parallel structure: at
the same moment `book0` is written (a market's genuinely first healthy board),
fetch the batch order books for that ladder's tickers and store beside it an
optional versioned block per bucket: `{vol, v24, bq, aq, d1, d2, d3, imb}`
(volume, 24h volume, best-bid and best-ask resting size, depth within 1c and
2c and top-3 levels on the relevant side, imbalance), plus one record-level
`mq_at` client stamp and `mq_v: 1`. Write-once, never on gated boards, absent
on fetch failure (the isolated-fetch pattern v6.23 established: a depth outage
must never touch the pricing fetch). Estimated fill price and executable
fraction are computed at replay time from the stored levels, not stored.
Cost must be measured at design time; a bounded variant (capture depth only
for buckets within 2 strikes of the modal bucket) exists if the full-ladder
cost threatens the archive budget. Thresholds: NONE. The registered analysis
is section 11.2, and the sequencing rule from the brief holds: this family
ships in its own commit, after the section 12 patch and the provider-
probability family, not alongside them.

### 6.2 How much paper P&L assumes top-of-book fills (brief item 15)

All of it, structurally: every paper play fills `int(stake // entry)` contracts
at the quoted top of book (`ya` for YES, `1 - yb` for NO) with no depth
constraint. Median 31 contracts per play, mean 73, max 333. The only
depth-adjacent guard is MIN_OI >= 300 on OPEN INTEREST, which is cumulative
positions, not resting size at the quote. For the three plays joinable to
decision-time OI, contract counts were 25-40 against OI of 353-1894: fills of
that size at top-of-book are plausible but unproven, and the audit batch 5
measurement (median spread 1c, median OI 488 across 480 live buckets) supports
plausibility at CURRENT paper size while saying nothing about depth at the
quote. Historical order-book depth does not exist and must not be fabricated;
no retro-adjustment of paper P&L is proposed. The honest statement for the
record: paper P&L is an upper bound on executable P&L, tightest at small size,
and the gap becomes measurable only after depth logging ships.

---

## 7. Signal-recency instrumentation plan (Deliverable 7)

Separating the brief's six staleness types against what already exists:

| Staleness type | Current instrument | Gap |
|---|---|---|
| Forecast staleness (model cycle age at board time) | `model_runs` logs newest init per provider per record; crons scheduled from measured availability lags (batch 2) | derived metric only: no stored "forecast_age_minutes"; computable offline from model_runs vs logged_at for every record since v5. NO new logging needed |
| Market-quote staleness (quote age at decision) | quotes are fetched in-run, seconds before scoring; `book0.at` and tape row stamps record board identity to the minute | at 3 boards/day the quote is always fresh relative to the board; sub-minute quote aging is a live-era concern, spec'd in LIVE_TRADING_SPEC |
| Signal staleness (edge computed vs acted on) | plays freeze on the same run that computes them; the owner may act later (known weakness, frozen-board vs live-board) | bet-confirmation logging (FUTURE 4) is the fix and is already on the roadmap; nothing new to propose |
| Execution staleness | no execution exists (paper) | LIVE_TRADING_SPEC sanity bounds already require re-check before any future order |
| Workflow-start delay (cron drift) | measured repeatedly (batch 1, checkpoint 1: +1.0 to +4.4h), crons moved off-hour, 16h stale-board banner | drift is measured ad hoc, not logged per run. Cheap additive option: store scheduled-vs-actual delta in the health strip dict already persisted per run |
| Superseded forecast runs | the redundant-run question was asked twice and DECLINED with mechanism (2026-07-16, 2026-07-28); mean_hist logs the revision trail | none |

Verdict: Nimbus's recency posture is already instrumented at the granularity
paper trading can use. The brief's `signal_timing` schema (11.3) is largely
derivable from existing fields (`model_runs`, `logged_at`, `book0.at`, `tape`,
`mean_hist`, `close_mid`); the only strictly-new cheap field is the per-run
cron drift delta, and the market-move-since-signal fields become computable
from the tape as it accumulates. Recommendation: NO new recency logging family
now; register a read-only "edge decay across tape boards" analysis once the
tape holds 150+ multi-board records (it shares the docket 7 gate), and revisit
hard recency rules only at the live-trading gate where they belong.

---

## 8. Alternative-provider challenger plan (Deliverable 8)

Availability, verified live 2026-07-28 (independent of the v6.23 session's own
verification, and agreeing with it):

- **AIGEFS**: operational since 2025-12-17 (GraphCast-based, NOAA), 31
  members, 4 cycles/day, 6-hourly steps to 384h, 0.25 deg. Served by
  Open-Meteo's ensemble API as `ncep_aigefs025` (31 member series returned on
  a live call today).
- **ECMWF AIFS ENS**: operational since 2025-07-01, v2 since 2026-05-12, 51
  members, 6-hourly to 360h, open data CC-BY-4.0. Served by Open-Meteo as
  `ecmwf_aifs025` on the ensemble API (51 member series returned today).
- Caveats that must ride with any adoption decision: native output is
  6-HOURLY, interpolated to hourly by Open-Meteo, which smooths the diurnal
  peak that daily-extrema settlement depends on; peer-reviewed evidence
  (Science Advances, 2026) that AI models underpredict record heat and
  overpredict cold records; Open-Meteo retains only a ~92-day rolling member
  archive, so no deep retrospective backtest is possible and the record must
  be accumulated forward; both feeds have short operational track records
  (AIFS v2 era began 2026-05-12); free tier is 10k calls/day, and the two
  extra fetches cost ~160 calls/day against ~320 already used.

Status in Nimbus: the brief's item 17 is ALREADY EXECUTED in its evidence
stage. v6.23 (2026-07-28) ships both providers as isolated, evidence-only
fetches into `members_by_model`, unit-tested to be invisible to pricing, the
integrity gate, the docket 4 tally, and book0. FUTURE 5 registered the
adoption gate BEFORE any AI-bearing settlement existed: at 150+ settlements
carrying both providers, the `member-count + AI providers` row in
`backtest_models.py` must beat the champion on full-sample MAE with a 90%
bootstrap CI excluding zero AND keep a positive advantage on targets after
2026-07-28. Calibration, settlement windows, observations, cities, horizons,
and scoring are held constant by construction (the backtester replays every
config through the identical roll30-bias walk-forward and scores CRPS with the
champion's logged sigma). Consensus filtering is not combined with it.

One genuine gap between the brief's design and the registered experiment: the
brief's challenger REPLACES ICON and GEM (stack = GFS + IFS + AIGEFS + AIFS),
while the registered race rows are pool-PLUS-AI and each-AI-alone. The
replacement stack is a one-line additional SLATE row in `backtest_models.py`.
Recommendation: propose registering that row (registration date = date added,
recorded in FUTURE, per the slate's own rule) at the same time the 150-
settlement gate first reads, NOT now: adding it today would change nothing
until the same data exists, and the slate discipline says candidates are added
when named, with their date. If the owner prefers it named immediately, it is
a two-line docs+code change safe to bundle with any future commit; it does not
belong in the section 12 patch (different family).

Expected value, stated honestly: `backtest_models.py` on 859 events shows the
pricing pool at 1.708 MAE with the adopted skill-pool at 1.693 and every
single-provider config at 1.798 or worse; no tested challenger improves on
the pricing pool meaningfully, so remaining upside is being pursued in
selection (revision note, top of file). The AI providers' plausible contribution
is diversity (a genuinely different model core), not raw skill, and the
diminishing-returns classification in the post-audit priority list stands
until the gate says otherwise.

---

## 9. Ranked recommendations (Deliverable 9)

Ranked by expected value per unit of risk-and-effort. Columns: EV = expected
value; Test = testability; Hist = historical data availability; Prosp =
prospective data need; Burden = implementation burden; Rel = reliability risk;
Overfit = overfitting risk; Freq = expected trade-frequency reduction.

| # | Recommendation | Verdict | EV | Test | Hist | Prosp | Burden | Rel | Overfit | Freq |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Retain `net` (+ticker,+bid) on resolved plays; fix the honesty-tile denominator | PROPOSE NOW (section 12) | High: repairs a live, silently-wrong governance instrument | Immediate (tests + byte-diff) | n/a (defect is current) | none | ~10 lines + 3 tests | none | none | none |
| 2 | Log per-provider dressed bucket probabilities beside book0 | Worth additive logging, own commit after #1 | Medium-high: unlocks the ONLY honest consensus test | Replayable offline once logged | none (proven impossible retroactively) | ~250 B/record | small | low (pure computation from data already fetched) | none until a rule is registered | none |
| 3 | Consensus shadow experiment (champion vs 3-of-4 vs 4-of-4 cost-adjusted) | Preregister AFTER #2 ships (draft in 11.1) | Medium: the 4-of-4 approximation is interesting, unproven | Gated, paired, prospective | approximation only (fragile) | needs #2 | replay-side only | none | controlled by preregistration | 4-of-4 could cut plays by half or more; measured as part of the verdict |
| 4 | Order-book depth + volume logging at the decision board | Worth additive logging, own commit, sequenced after #2 | Medium: quantifies the top-of-book fill assumption before stakes rise | Bands analyzable once logged | none, and must not be fabricated | one extra GET per priced ladder (~80/run vs current ~400 quota) | moderate (new endpoint dependency, isolated fetch pattern exists) | low | none until a gate is registered | none as logging |
| 5 | AI replacement-stack race row (GFS+IFS+AIGEFS+AIFS) in backtest_models | Register when the FUTURE 5 gate first reads | Low-medium | Same harness as docket 4 | AI summaries accumulate since 2026-07-28 | none extra | 2 lines | none | slate-controlled | none |
| 6 | Per-run cron-drift delta in the health record | Optional, tiny | Low | trivial | drift measured ad hoc already | none | 2 lines | none | none | none |
| 7 | Edge-decay-across-tape analysis | Already implied by docket 7; no new work | Medium (timing verdict) | replay at 150+ taped plays | tape starts now | none | none (tooling exists) | none | slate-controlled | possible, priced by the docket 7 verdict |
| 8 | Spread cap / market-quality composite score as a selection rule | REJECT for now | Low: Nimbus already prices the spread inside net edge; a threshold duplicates the cost gate | docket 6 already covers the family | book0 has yb/ya | - | - | - | high if tuned on the lifetime book | high |
| 9 | Recency hard rules (reject on $0.04 move, half-edge decay) | REJECT for paper era | Low at 3 boards/day | untestable until tape matures | none | - | - | - | high | medium |
| 10 | Quarantine LOW-Buy-NO / HIGH-Buy-YES / lead-0 segments | REJECT (retrospective cell scan; docket 6 slate already contains the honest versions; lead-0 cell is 100% legacy) | - | - | - | - | - | - | maximal | high |
| 11 | Adopt external market-quality weights (30/20/25/25) or thresholds | REJECT (no evidence they predict profit; seller's own ledger is negative) | - | - | - | - | - | - | - | - |
| 12 | Purchase the $75 source for study | REJECT per brief; also unnecessary (public materials describe nothing Nimbus lacks except unverified thresholds) | - | - | - | - | - | - | - | - |

---

## 10. Strongest case against each recommendation (Deliverable 10)

1. **`net` retention + tile fix.** Strongest objection: the tile fix changes
   rendered output without new settlements, so "reporting is altered". Answer:
   the current output is a false statement (the model does not claim 0.0c);
   repairing a wrong instrument is the one reporting change the honesty
   philosophy mandates, the change is displayed with its n and coverage split,
   and the v6.19 precedent (measurement corrected, gate unchanged, correction
   documented in FUTURE) is exact. Residual risk approaches zero: no decision
   path reads resolved-play `net`.
2. **Provider-probability logging.** Objections: (a) it grows state ~250
   B/record against a file already forcing archive policy; (b) shared-
   calibration provider probabilities are NOT what four independent shops
   would publish, so "agreement" measured this way partially inherits the
   pool's own errors; (c) providers are correlated (same physics, shared
   observations), so 4-of-4 may just proxy "market already agrees", selecting
   efficiently-priced boards where net edge is small. All three are real; (a)
   is budgeted by the amended 7b policy, (b) is the least-overfit option and
   is stated in the registration, (c) is exactly what the paired experiment
   measures rather than assumes.
3. **Consensus shadow.** Objections: the reproduced gradient is
   recipe-fragile (shown in 5.2); unanimity may cut trade count severely
   (the approximation retains 50 of 119); the retained set may concentrate in
   obvious boards with thin residual edge; and a filter that improves ROI by
   shrinking the book can still reduce total P&L. The registration therefore
   makes retained-vs-rejected P&L, opportunity cost, and frequency reduction
   primary outputs, not footnotes, and pre-commits to NOT adopting on ROI
   alone.
4. **Depth/volume logging.** Objections: at 11-333 contracts the book rarely
   binds, so the data may prove what audit batch 5 already suggested
   (irrelevant at paper scale); the extra endpoint is a new failure surface;
   and depth features invite post-hoc threshold shopping. Mitigations: the
   isolated-fetch pattern (v6.23) contains the failure surface; the logging
   ships with NO rule attached; and the stated purpose is the live-era gate,
   where LIVE_TRADING_SPEC already requires execution realism. If paper-scale
   analysis shows fills unconstrained, that is a successful negative result.
5. **AI replacement-stack row.** Objections: AI extrema smoothing is
   documented in the literature; the 6-hourly native cadence undersamples the
   settlement quantity; ICON is currently the strongest measured provider, so
   dropping it needs strong evidence; and the row can only be judged on the
   same 150-settlement clock as the additive row, so registering it early buys
   nothing. Hence: register at gate-read time.
6. **Cron-drift logging.** Objection: measured drift is already characterized
   and bounded by design (off-hour crons, staleness banner); two more lines of
   state per run may never be read. Fair; that is why it is ranked optional.
7. **Edge-decay tape analysis.** Objection: it duplicates docket 7's
   instrument. Answer: it IS docket 7's instrument; the recommendation is
   merely not to build anything new.
8. **Rejections (8-12).** The counterargument to rejecting is always "the
   external bot does it". The evidence standard answers it: the external
   ledger is negative, the thresholds are unverified, and every rejected item
   either duplicates an economically equivalent Nimbus mechanism (spread is
   PRICED, not thresholded), is already covered by a registered experiment
   (docket 6 floors and side filters), or would be a retrospective cell scan
   the governance forbids.

---

## 11. Preregistration drafts (Deliverable 11)

Drafts only. None of these is registered by this report; registration happens
by writing the entry into FUTURE.md with owner approval, after the enabling
instrumentation ships.

### 11.1 Source-consensus shadow (draft)

- **Hypothesis:** champion plays supported by at least 3 of 4 (separately: 4
  of 4) pricing providers under cost-adjusted support have higher
  fees-inclusive ROI than the unfiltered champion book.
- **Support definition (fixed now):** provider k supports the selected side
  of play i iff, using k's logged shared-calibration bucket probabilities
  (book0.source_mp), p_k minus executable entry minus (half-spread + fee(mid)
  + 0.01) >= PLAY_NET_EDGE for that side. Support counts run over providers
  present; a record missing any provider vector is excluded from BOTH arms
  and counted.
- **Arms:** champion (reference); champion AND support >= 3; champion AND
  support = 4. No other variants; ties impossible by construction.
- **Registration date:** the date the FUTURE entry lands (target: with the
  logging commit).
- **Gate:** 150+ champion plays carrying source_mp, same threshold family as
  dockets 6 and 7.
- **Primary metric:** fees-inclusive ROI of retained plays, 90% bootstrap CI
  (block-by-target-date), champion as reference.
- **Secondary:** retained-vs-rejected P&L split, opportunity cost of skipped
  winners, avoided losses, trade-frequency reduction, average CLV, win rate,
  city/side concentration.
- **Analysis:** paired by construction (each arm is a subset of the same
  champion book over the same period).
- **Adoption rule:** an arm may be PROPOSED for adoption only if its ROI CI
  excludes the champion's point ROI on the full sample AND the advantage
  persists on targets after registration; adoption ships as its own
  single-knob commit with MODEL_VERSION bump and Decision Log row.
- **Rejection rule:** CI includes champion ROI at the gate, or frequency
  reduction exceeds 60% without a CI-excluded advantage: the arm closes with
  finality.
- **Unhealthy ladders:** gated records never enter (they carry no plays).

### 11.2 Market-quality bands (draft, logging first, NO rule)

- **Instrumentation:** at the book0 board, per priced ladder: market volume,
  best-bid/ask quantity per bucket, depth within 1c and 2c, top-3-level
  depth, imbalance = yes-side depth / total at best, quote timestamp,
  intended contracts, estimated average fill price walking the book,
  executable fraction at top-of-book. Version field `mq_v: 1`.
- **Registered analysis (read-only):** at 150+ plays carrying the block,
  report fees-inclusive ROI, CLV, and estimated slippage by PRE-DECLARED
  quartile bands of spread, depth-to-intended-size ratio, and imbalance.
  Quartiles computed on the first 150, then frozen.
- **Explicitly NOT registered:** any selection rule. A gate proposal requires
  a second registration naming one variable and one threshold, justified by
  the band read, and must quantify frequency reduction.

### 11.3 Signal recency (draft, derived-metrics only)

- **No new logging.** At 150+ taped multi-board plays (docket 7's gate),
  compute per play: net-edge at tape[0] vs each later board (re-derived from
  taped yb/ya/mid and the fee helper), fraction of edge remaining at the
  next board, and the relation between edge decay and realized pnl/CLV.
  Report by lead and kind. This shares docket 7's data and adds no arm to
  it; any rule proposal goes through its own registration afterward.

### 11.4 Alternative-provider stack (draft addendum to the FUTURE 5 gate)

- At the first read of the FUTURE 5 gate (150+ AI-bearing settlements), add
  one race row to `backtest_models.py`: `gfs025 + ecmwf_ifs025 +
  ncep_aigefs025 + ecmwf_aifs025` member-count weighted with roll30 bias (the
  brief's replacement stack), registration date = the date added. Adoption
  standard identical to FUTURE 5's existing text (full-sample CI excluding
  zero AND positive prospective advantage). The 6-hourly-native and
  extrema-smoothing caveats are recorded as named risks the gate read must
  address (compare signed bias and tail calibration, not MAE alone).

---

## 12. The proposed first patch (Deliverable 12): retain `net` on resolved plays and repair the stated-edge honesty tile

**Chosen because** it is the only candidate that repairs a MEASURED, currently
wrong output (the +0.0c stated-edge tile), costs ~10 lines, adds zero fetch
surface, follows an exact in-repo precedent (v6.19 p_win retention), and is
prerequisite to the net-edge band analysis the brief asked for and the record
cannot currently answer. It is deliberately ONE instrumentation family
(selection-time field preservation), per the brief's own phase 4 rule.

- **Files and functions:**
  - `kalshi_weather.py`, `resolve_pending()`: add `"net": pl.get("net")`,
    `"ticker": pl.get("ticker")`, `"bid": pl.get("bid")` to the resolved-play
    dict (three key copies from the frozen pending play, exactly the v6.19
    shape).
  - `kalshi_weather.py`, `compute_report()`: the honesty tile numerator is
    unchanged; the DENOMINATOR becomes contracts over net-bearing plays only,
    and the report gains `edge_stated_n` (plays counted). If zero plays carry
    `net`, `edge_stated` is omitted (the tile renders its existing "pending"
    style rather than a false 0.0). No reconstruction fallback is possible or
    attempted: `net` is not recoverable for the 262 settled plays (the
    half-spread is gone with the decision book except for the 6 book0-era
    plays) and a partial backfill would mix exact and fabricated values.
  - `kalshi_weather.py` render: the tile shows its n (e.g. "stated edge
    /contract (n plays)"), so the era split is visible, mirroring how the
    replay tool prints its sd-proxy split.
- **New schema fields:** resolved play gains OPTIONAL `net`, `ticker`, `bid`.
  7b note required (same sentence pattern as the 2026-07-28 p_win note).
- **Backward compatibility:** all readers already `.get` these fields; old
  records simply lack them; `edge_stated` handles absence by omission. No
  state migration, no rewrite of `weather_state.json`, ever.
- **Tests to add (test_nimbus.py):**
  1. A play driven through `resolve_pending` with a mocked settlement carries
     `net`, `ticker`, `bid`, and `p_win` on the resolved record (pipeline
     test, not a hand-built fixture: this is the test shape that would have
     caught both this defect and the v6.19 one).
  2. `compute_report` on a mixed state (one legacy play without `net`, one
     new play with it) reports `edge_stated` equal to the new play's value
     with `edge_stated_n == 1`, not a diluted average.
  3. `compute_report` on the current-schema state (no play carries `net`)
     omits `edge_stated`, and the rendered tile does not display "+0.0c".
- **Sandbox equivalence procedure:** (a) `python3 -m py_compile` on all four
  scripts; (b) full test suite; (c) `compute_report` diff on the committed
  state before and after the change: every key byte-identical EXCEPT the
  documented removal of the false `edge_stated: 0.0` (this is the one
  intended difference and is quoted in the changelog entry, the v6.19
  "equivalence proven, not assumed" pattern with its one delta named);
  (d) the CLAUDE.md sandbox double-run via the copy-to-scratch procedure (or
  the PR validation workflow where the session environment blocks the APIs),
  confirming zero freeze violations, no unintended plays, both boards
  rendering, and `weather_state.json` byte-unchanged; (e) em dash sweep.
- **MODEL_VERSION:** UNCHANGED. No forecasting, pricing, selection, sizing, or
  settlement behavior moves; this is a recording-and-measurement change, the
  v6.12/v6.19/v6.20/v6.22 precedent class. CONFIG_HASH unchanged (no knob).
- **Documentation:** HANDOFF changelog entry + 7b schema note + a Decision Log
  row ("measurement only", quoting the tile defect), and a FUTURE note only if
  the owner wants the net-band analysis registered as a read-only checkpoint
  item.
- **Why it cannot alter behavior:** `resolve_pending` runs before scoring and
  writes only the resolved archive; no code path reads resolved-play `net`,
  `ticker`, or `bid` for any forecast, price, selection, sizing, or settlement
  decision (verified by grep across `kalshi_weather.py`, `replay_selection.py`,
  and `backtest_models.py`: the only consumer is the honesty tile numerator
  that already expects the field). Calibration learns from record-level
  `bias`/`sd`/`sigma`, untouched. The selection replay reads `book0`,
  untouched. Settlement math (`won`, `contracts`, `fees`, `pnl`) is untouched.
  The tile change affects a display aggregate only.

**Explicitly out of this patch** (each its own future family, in order):
provider-probability logging (section 5.4), order-book depth (section 6),
the AI replacement-stack row (section 11.4).

---

## Appendix: the brief's 22 questions, one line each

1. External weather strategy profitable after fees? No evidence of it; its own ledger reads -$21.75 on 103 trades.
2. What did ~410% measure? A $50 test balance to $255, ~180 trades, pre-fill-fix accounting, never reconciled to the ledger.
3. Independent events behind public results? Not published; ledger rows are per-trade, capital base absent.
4. GitHub vs book vs website vs paid? 31-member GFS (book/launch) -> 62 (repo README, v1.0) -> 164 claimed (v2.0+); paid v2.3 unverifiable.
5. What does 3-of-4 agreement mean? Publicly undefined; only a 2-model band+direction rule is published.
6. Can Nimbus reproduce exact historical consensus? No: only provider {n, mean, sd} summaries exist.
7. Minimum prospective instrumentation? Per-provider shared-calibration bucket probabilities beside book0 (~250 B/record).
8. Does book0 support realistic execution analysis? It supports exact repricing and top-of-book replay; depth/fill realism needs new logging.
9. How much paper P&L assumes top-of-book fills? 100% by construction; plausible at 11-333 contracts, unproven.
10. Is open interest adding selection value? Unknown; decision-time OI is joinable for 3 plays; historically untestable, replayable via book0 going forward (MIN_OI 1000 is already a docket 6 candidate).
11. Would volume/depth add information beyond spread+OI? Plausibly at larger size; log-only first.
12. Losses from forecasting vs selection? No tested forecast challenger (8 configs, n=859) improves on the champion meaningfully, while the measured dollar losses concentrate in cheap-tail adverse selection at the play filter (registered as docket 1); an untested forecast improvement remains possible in principle.
13. Legacy vs current losses? Legacy engine -$183 of the -$278; audit-era core book -$8.73 (69 plays); audit cheap cell -$85.83 (14 plays).
14. HIGH Buy NO near break-even prospectively? Yes: -0.2% lifetime, and the audit-era core book overall is -0.8% on 69 plays (90% block-bootstrap CI [-19.8%, +19.2%]: a small sample consistent with breakeven, not proof of it).
15. LOW Buy NO still poor after controls? Direction persists in the audit era (-34.6%, n=25); too thin to act; covered by registered slate.
16. Lead-0 mostly pre-nowcast? Entirely: 33 of 33 plays are legacy-era.
17. Is decision-time field loss impairing diagnosis? Yes, measurably: the stated-edge tile has read a false +0.0c since 2026-07-06; net-edge bands are uncomputable.
18. AIGEFS/AIFS obtainable reliably? Yes (verified live), with 6-hourly-native and extrema-smoothing caveats; already logging since v6.23.
19. Would replacing ICON/GEM improve CRPS enough? Unknown; ICON is currently the strongest measured provider; test via the 11.4 race row at the gate.
20. Is the external advantage rejection rather than prediction? Unproven either way: its rejection stack is asserted, its ledger negative. The transferable idea is instrumentation honesty, not any specific filter.
21. Highest-value zero-behavior-change patch? Section 12: retain `net` and repair the honesty tile.
22. Evidence sufficient to promote a new rule? The standard already in force: pre-registered gate, full-sample CI excluding the champion, prospective persistence, one knob per commit, owner approval.
