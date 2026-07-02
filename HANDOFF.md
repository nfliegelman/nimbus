# Nimbus (Kalshi Weather Edge): AI Handoff / Technical Spec

**Purpose of this file:** you are an AI assistant helping the owner (a hobbyist prediction-market bettor, not a professional developer) modify this program. This document tells you what the program is, how it is built, and which decisions are deliberate so you do not undo them while helping. Read it fully before proposing changes. The `README.md` is for the owner (setup instructions). `FUTURE.md` is the running list of planned improvements, known weaknesses, and the automation roadmap; read it too, and move shipped items from there into this changelog. This file is for you.

**Doc version:** 2026-07-02 (v4.1). Update the changelog at the bottom whenever you change the code.

---

## 0. THE ONE RULE THAT PREVENTS CONFUSION

Every time you change the code, hand the owner back BOTH the updated `kalshi_weather.py` AND an updated `HANDOFF.md` with a new changelog entry, and tell them to commit both together. This file is only accurate if it is kept in sync. The most common failure is code changing while this doc goes stale, which leaves the next AI confused. Do not let that happen.

---

## 1. Prime directives (read first)

1. **Do not rebuild from scratch.** This code is the product of many careful iterations against live Kalshi and forecast data. Prefer surgical edits. If you believe a rewrite is warranted, say so explicitly and explain the tradeoff before doing it.
2. **Honesty over polish is the core philosophy.** The tool exists to surface real edges and output "no bets today" when there is not one. Never add logic that manufactures signals, inflates sizes, or fabricates data to look busier. A sit-out day is a correct, valuable output. Roughly 3 of the deepest failures in this project's history were fake edges that looked real (see section 4); every guard exists because one of them bit us.
3. **Never use em dashes** anywhere: not in code, comments, UI text, or your chat replies to the owner. The owner forwards output to other people and em dashes read as AI-authored. Use commas, colons, or parentheses. Empty cells use a plain hyphen or a middot.
4. **Real data only.** Every probability shown must trace to an actual ensemble forecast, and every win/loss must trace to Kalshi's official settlement. If a source is unavailable, skip honestly rather than estimating and presenting it as fact.
5. **Serve the underlying goal, not just the literal request.** If a smarter framing or a split solution better serves what the owner actually cares about, propose it. Ask clarifying questions when they improve the result. The owner explicitly values this.

---

## 2. What the program does

`kalshi_weather.py` is a single Python script that, on each run:
1. Pulls open Kalshi daily high/low temperature markets across 20 US cities (`Climate and Weather`, series `KXHIGHT*` and `KXLOWT*`).
2. Builds a fair-value probability for every temperature bucket from a pooled multi-model ENSEMBLE (Open-Meteo GFS + ECMWF + ICON + GEM, ~143 members). Members are first CALIBRATED: shifted by a per-city bias correction learned from Kalshi settlements, then each member is dressed with a Gaussian kernel whose width is learned from realized errors (Wang-Bishop second-moment matching). Bucket probability = average kernel mass inside the bucket's real interval [floor-0.5, cap+0.5), matching NWS half-up rounding. Daily highs/lows are taken over the NWS Climate Report day (Local STANDARD Time year-round, so 1:00 AM to 12:59 AM clock time during DST), because that is the exact window Kalshi settles on.
3. Flags edges (model prob minus Kalshi price, after spread and fee), guarded (section 4).
4. Sizes each play in UNITS (2u / 1.5u / 1u / no bet) from a confidence score plus a win-probability cap (section 5).
5. LOGS predictions, then RESOLVES past ones using Kalshi's own settled `result` and `expiration_value` (authoritative win/loss and margin of victory).
6. Writes two dashboards into `docs/` for GitHub Pages: `index.html` (today's bets) and `results.html` (performance tracker with inline SVG charts, per-city and per-unit breakdowns, Brier vs market, margins, raw table).
7. Persists everything to `weather_state.json`.

Runs on **GitHub Actions** (cloud) twice daily and publishes to **GitHub Pages**. Also runs locally (opens a browser). One file, auto-detecting via the `CI` env var. Running in the cloud is WHY the owner's office firewall is a non-issue: fetches happen on GitHub's network, the owner only ever views github.io pages.

---

## 3. File structure (single file: kalshi_weather.py)

Top to bottom:

| Section | What it does |
|---|---|
| CONFIG knobs | `BANKROLL`, `BASE_UNIT_USD`, `UNIT_MAP`, `WINPROB_CAP`, `MIN_OI`, `PLAY_NET_EDGE`, `MAX_LEAD_DAYS`, `BIAS_TOL`, `INTRADAY_HIGH_CUTOFF`, `ENSEMBLE_MODELS`, `TIER_CUTS`, paths |
| `CITIES` | code -> (lat, lon, tz, label). Coords set to each city's NWS resolution station |
| helpers | `fget`, `fnum`, `parse_date_code`, `round_nws`, `bucket_range`, `in_bucket`, `margin_deg`, `bucket_rep`, `fee`, `pstdev` |
| data fetch | `pull_weather_markets`, `fetch_members` (ensemble), `fetch_settled_event` (Kalshi settlement) |
| tiers/sizing | `city_skill`, `tier_for`, `units_of`, `size_play` |
| engine | `score` (builds rows + plays, logs predictions) |
| resolution | `resolve_pending` (Kalshi settlement -> win/loss, margin, bias) |
| reporting | `compute_report` (Brier, calibration bins, per-city bias, per-city/per-unit P&L, cumulative series) |
| render | `CSS`, small helpers, `render_bets` (index.html), `render_results` (results.html), `svg_line`, `svg_bars` |
| `main()` | load state, resolve, score, report, save, render both dashboards |

The dashboards are server-rendered HTML strings (Python builds the HTML; the only client JS is tab switching). No build step, no framework, no external chart library (charts are hand-rolled inline SVG, on purpose, so nothing depends on a CDN the office network might block).

---

## 4. The guards (DELIBERATE, do not remove)

Every one of these prevents a fake edge that looked real during development. If you find yourself removing a guard to produce more plays, you are going the wrong way.

- **Timing guard (`realized`).** A same-day LOW is already realized (the low prints at dawn), and a same-day HIGH is realized after `INTRADAY_HIGH_CUTOFF` local hours (default 14). Realized markets are never scored as edges; you cannot forecast weather that already happened. Local hour is derived from Open-Meteo's `utc_offset_seconds` (no `zoneinfo`/`tzdata` dependency, which matters on Windows).
- **Bias guard (`biased`).** If the model's mean temp is offset from the market's implied mean by more than `BIAS_TOL` (2.0 deg F), the whole city is suppressed from plays. A center-of-mass disagreement is almost always my station coordinates not matching Kalshi's resolution station, not real alpha. Real edge lives in the SHAPE of the distribution once the means line up. The per-city bias panel on the Results tab is how the owner learns which cities need coordinate fixes.
- **Single-winner buckets.** Kalshi temp buckets are exhaustive and mutually exclusive, so model probabilities across a ladder sum to ~1. This program only handles temp ladders. Do NOT copy this logic onto multi-winner or nested markets (album releases, "before date X" ladders) where probabilities do not sum to 1; that manufactured huge fake edges in earlier prediction-market work.
- **Favorite-longshot direction.** Retail overpays for unlikely YES outcomes. Buying a YES longshot is the trap; taking the NO side of an overpriced longshot is the good, high-win-probability fade. The win-probability cap (section 5) encodes this so a big edge on a low-YES-probability bucket cannot get a big size.
- **Cost gate.** A bucket is only a play when net edge (model prob minus price, minus half-spread minus Kalshi fee minus 1c buffer) clears `PLAY_NET_EDGE`, open interest clears `MIN_OI`, lead is within `MAX_LEAD_DAYS`, and price is not at the 0/100 rails.
- **LST settlement window.** Daily highs/lows are computed over the NWS Climate Report day (Local Standard Time year-round). During DST that day is 1:00 AM to 12:59 AM local clock. This lives in `fetch_members` and is a settlement-correctness guard, not a style choice.

### 4b. The calibration engine (DELIBERATE, self-learning)

`calib_params(state)` learns, per (city, kind), from settled results:
- **Bias correction (`corr`)**: negative of the rolling mean RAW forecast bias (last `BIAS_LOOKBACK` settlements), shrunk by `n/(n+BIAS_SHRINK_K)`, zero until `BIAS_MIN_N` settlements exist. RAW bias is reconstructed as logged `bias` plus the `bias_corr` that was applied at log time, so the learning target stays stable as corrections evolve. This is the honest fix for station-coordinate offsets: it comes from Kalshi's own settlements, so it works WITH the bias guard (a corrected city naturally stops tripping `BIAS_TOL`), it never manufactures edge.
- **Dressing sigma (`sigma`)**: Gaussian kernel width per Wang-Bishop second-moment matching: kernel variance = variance of realized bias-corrected errors minus mean raw member variance, clamped to [`DRESS_SIGMA_MIN`, `DRESS_SIGMA_MAX`]. Falls back to a pooled global sigma (needs 15+ settlements), then `DRESS_SIGMA_DEFAULT`. Raw member counting into 1-degree buckets is sampling noise past the first decimal; the kernel is what makes bucket probabilities smooth and honest.
- `dressed_prob` computes bucket probability as average kernel mass in [floor-0.5, cap+0.5), matching NWS half-up rounding. Ladder probabilities still sum to ~1.
- Every prediction logs `bias_corr`, `sigma`, member `sd`, predictive `psd`, and `model_version`; `resolve_pending` copies `sd`/`bias_corr`/`sigma` into resolved records so the loop closes. Old records without these fields are read defensively.
- The Results tab shows a Calibration table (forecast prob vs realized frequency by decile) and a Learned corrections table (shift, width, n per city). Those two tables are the tuning instruments; do not remove them.

---

## 5. Unit sizing (DELIBERATE, four guardrails)

`size_play(net, p_win, proven)` returns (units, reason). Sizing is driven by EDGE MAGNITUDE, then capped. Do not collapse these.

1. **Edge bands** set the base from net edge (model prob minus price, after spread and fee): `>= EDGE_2U (0.14)` gives 2u, `>= EDGE_1_5U (0.08)` gives 1.5u, `>= PLAY_NET_EDGE (0.04)` gives 1u, below gives no bet.
2. **Plausibility cap (`SUSPECT_EDGE`, 0.20).** A net edge above 20 points is almost always the model being wrong or a thin/stale market, NOT free money. It is capped to 1u and flagged. This is the single most important lesson the owner learned (from a real "52% edge" that was noise): a bigger edge is not a green light past a point, it is a red flag. Do NOT invert this to size UP on huge edges.
3. **Win-probability cap (`WINPROB_CAP`).** `p_win` is the model prob the POSITION wins (`mp` for YES, `1 - mp` for NO). Win < 42% of the time trims to 1.5u, < 30% to 1u; 2u needs p_win >= 0.55. A long price is already its own reward. This is why fading an overpriced YES longshot via NO (high p_win) can size up while buying the YES longshot (low p_win) cannot.
4. **Lead cap (`LEAD_CAP_DAYS`).** Plays 3+ days out are capped at 1u. Forecast skill decays fast with lead; this restores the lead discipline the old tier system had.
5. **Proven-city gate.** 2u also requires the city to appear in `city_skill` (>= 20 resolved buckets with a positive Brier edge). Until then 2u is locked to 1.5u. Early on nothing is proven, so 1.5u is effectively the ceiling. Intended.

`SUSPECT_EDGE`, `EDGE_2U`, `EDGE_1_5U`, `WINPROB_CAP`, `PLAY_NET_EDGE`, `LEAD_CAP_DAYS` are tunable constants at the top of the file; retune them from the by-edge and by-unit tables on the Results tab as data accumulates. `tier_for`/`units_of` remain defined but no longer drive sizing (the S/A/B tag shown is derived from the final unit size). `city_skill` still uses realized Brier, not tier.

## 6. Data sources and quirks

- **Kalshi** (`api.elections.kalshi.com/trade-api/v2`): no auth needed for reads. `events?...&with_nested_markets=true` for open markets; `markets?event_ticker=...&status=settled` for settlement. Settled markets expose `result` ("yes"/"no") and `expiration_value` (the actual settled temperature). Buckets carry `floor_strike`, `cap_strike`, `strike_type` ("less"/"between"/"greater"); parse those, not the title text.
- **Open-Meteo ensemble** (`ensemble-api.open-meteo.com`): free, no key, `models=gfs025,ecmwf_ifs025,icon_seamless,gem_global` pooled for ~143 members. Returns hourly per-member temps localized to the requested `timezone` in local CLOCK time. Do NOT group by `t[:10]` directly: `fetch_members` shifts timestamps back to Local Standard Time (using `utc_offset_seconds` minus the city's fixed standard offset in `STD_OFFSET_H`) before picking daily highs/lows, because NWS Climate Reports (Kalshi's settlement source) use LST year-round. Removing that shift silently breaks LOW markets during DST. `utc_offset_seconds` is also used for the timing guard.
- **City -> station coordinates** in `CITIES` are approximate (airport or Central Park). A wrong coordinate shows up as a persistent per-city bias on the Results tab and is auto-suppressed by the bias guard. Fixing a city means correcting its lat/lon to Kalshi's actual resolution station.
- **`CI` flag:** when `os.environ["CI"] == "true"` (GitHub Actions sets this), the script does not open a browser or wait for input. Keep it cloud-runnable and non-interactive.
- **Python version:** the workflow pins 3.12. Backslashes inside f-string expressions are a SyntaxError on 3.11 and earlier; avoid them (use a named constant like `DOT`) so the file stays portable. This exact bug broke a run once.

---

## 7. Outputs and persistence

Each run writes:
- `docs/index.html` (today's bets) and `docs/results.html` (tracker). GitHub Pages serves `/docs`.
- `weather_state.json`: `{"predictions": {...}, "resolved": [...]}`. Predictions are logged only for non-realized markets (genuine forecasts). Resolved records hold per-bucket hit, per-play win/pnl/margin, and forecast bias.

On GitHub the workflow commits these back so state persists across ephemeral runs and time off. Do not move persistence to anything needing a database or paid service; the commit-back pattern is deliberate and free.

**NEVER delete or overwrite `weather_state.json`**; it is the entire track record, and the zip handed to the owner deliberately excludes it. Every logged bet is stamped with `MODEL_VERSION` and stores its own edge, so retunes start a new version alongside old results rather than invalidating them. New report fields must read old records defensively (`.get`, guard `None`) so an upgrade never breaks or loses history. Git commit history of the state file is the backup of record.

---

## 8. Frontend conventions

- Dark, mobile-first, CSS variables at the top of the `CSS` string.
- **Today's bets are pick CARDS**, not a table. Each card leads with the exact Kalshi range (`88\u00b0 to 89\u00b0`) and a large color-coded side: **YES is green, NO is red, matching Kalshi's own colors** so the owner taps the right button. The unit size, price, and win probability sit on a bar under it; the supporting data (model, market, edge, net, OI) is one small line below. This layout exists specifically because the owner was mis-tapping yes/no; keep the range and side the visual focus.
- Two views: `index.html` (bets) and `results.html` (tracker), linked by the nav. Charts are inline SVG (`svg_line`, `svg_bars`), no external library.
- Grade/size colors: 2u gold, 1.5u green, 1u amber, no-bet grey. Keep consistent.
- No em dashes in any string.

---

## 9. Validate before handing back

1. `python -c "import py_compile; py_compile.compile('kalshi_weather.py', doraise=True)"` passes.
2. `CI=true python kalshi_weather.py` runs and writes both `docs/index.html` and `docs/results.html` with no error (it may legitimately produce zero plays; that is fine).
3. No backslash inside any f-string expression (3.11 safety), and zero em dashes introduced.
4. You did not remove a guard (section 4), remove the win-probability cap, make S/A more common, or break commit-back persistence.
5. You updated this file's changelog and told the owner to commit both `kalshi_weather.py` and `HANDOFF.md` together.

---

## Changelog

- **v4.1 (2026-07-02), docs only:** Added `FUTURE.md`, the future inclusions log (planned improvements, known weaknesses, retune checkpoints, and the step-by-step path to automated trading). No code changes; `kalshi_weather.py` is unchanged from v4. Key process notes captured there: plays should eventually be frozen at first log before any extra cron runs are added, and live order execution should move off GitHub Actions to an always-on runner when the time comes.

- **v4 (2026-07-02), renamed Nimbus:** Added the calibration engine: (1) per-city rolling bias correction learned from Kalshi settlements with shrinkage (`BIAS_MIN_N`, `BIAS_LOOKBACK`, `BIAS_SHRINK_K`); (2) Gaussian kernel dressing of ensemble members with per-city width from Wang-Bishop second-moment matching (`DRESS_SIGMA_*`), replacing raw member counting for bucket probabilities; (3) fixed the settlement window: daily highs/lows now computed over the NWS CLI day in Local Standard Time year-round (during DST the day is 1AM to 12:59AM clock time), which the old clock-day grouping got wrong, mainly hurting LOW markets. Expanded the ensemble to 4 models (~143 members, added ICON + GEM). Restored lead discipline: plays 3+ days out capped at 1u (`LEAD_CAP_DAYS`). Plays now sort by win probability within each size and carry a high-confidence tag at `HICONF_PWIN`. Fixed a bug where `model_version` was never written into logged predictions. Results tab gained Calibration and Learned corrections tables. Rebranded UI and console to Nimbus; file names unchanged.

- **v3 (2026-07-01):** Replaced tier-driven sizing with edge-band sizing plus a plausibility cap (`SUSPECT_EDGE`): a net edge above 20% is sized DOWN to 1u and flagged, because outsized edges are model or liquidity errors, not opportunity. Kept the win-probability and proven-city caps. Stamped every logged bet with `MODEL_VERSION` and stored per-bet edge so history survives tunes and can be compared. Added time-windowed win rates (past day, past week, overall) and a win-rate-by-edge table to the Results tab. Report functions now read old records defensively so upgrades never lose past data.

- **v2 (2026-07-01):** Added the win-probability cap (`WINPROB_CAP`, `size_play`) so a large edge on a low-win-probability bet is capped at 1u instead of 1.5u+; capped plays show a "longshot cap" flag. Redesigned today's bets from a dense table into pick CARDS that lead with the exact temperature range and a large color-coded YES/NO (green/red, matching Kalshi) to stop yes/no mis-taps. Day headline now reflects max UNITS rather than tier. No change to the guards, ensemble math, settlement, or persistence.
- **v1 (2026-07-01):** Initial GitHub-deployable build. Ensemble fair value (GEFS + ECMWF), timing and bias guards, tier system (edge x lead x sharpness x city track record, S locked until a city is proven), Kalshi-settlement resolution with margin of victory, edge dashboard + results tracker (SVG charts, per-city and per-unit breakdowns, Brier vs market), twice-daily GitHub Actions with commit-back persistence. Python pinned to 3.12 after an f-string backslash SyntaxError on 3.11.

---

*When you finish a change: bump the doc version, add a changelog entry saying what changed and why, update any section above that no longer matches the code, and remind the owner to commit both `kalshi_weather.py` and `HANDOFF.md` together.*
