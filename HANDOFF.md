# Kalshi Weather Edge: AI Handoff / Technical Spec

**Purpose of this file:** you are an AI assistant helping the owner (a hobbyist prediction-market bettor, not a professional developer) modify this program. This document tells you what the program is, how it is built, and which decisions are deliberate so you do not undo them while helping. Read it fully before proposing changes. The `README.md` is for the owner (setup instructions). This file is for you.

**Doc version:** 2026-07-01 (v2). Update the changelog at the bottom whenever you change the code.

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
2. Builds a fair-value probability for every temperature bucket from a pooled multi-model ENSEMBLE (Open-Meteo GEFS + ECMWF, ~80 members). Each member's daily high/low is rounded the way the NWS daily report rounds, then counted into buckets. That count / total = model probability.
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

---

## 5. Tier and unit sizing (DELIBERATE, the win-prob cap is the guardrail)

Two stages. Do not collapse them.

**Stage 1: tier** (`tier_for`) = an effective-edge score = net edge x lead-time skill x ensemble sharpness x city track record.
- `lead_w`: next-day/same-day 1.0, then decays (0.8, 0.6, 0.45).
- `sharp_w`: tighter ensemble (smaller sd) scores higher.
- `hist_w`: once a city has >= 20 resolved buckets, its realized Brier-edge multiplies the score (a proven city gets boosted, a losing one demoted).
- Thresholds `TIER_CUTS` map the score to S/A/B/C. **A city cannot earn S until it is proven** (>= 20 resolved buckets); until then S is capped to A. B should be the common tier, S/A rare. If you are making S/A more common, you are going the wrong way.

**Stage 2: win-probability cap** (`size_play`). Tier sets the ceiling, then `WINPROB_CAP` caps units by `p_win` (the model probability the POSITION wins: `mp` for YES, `1 - mp` for NO):
```
WINPROB_CAP = [(0.55, 2.0), (0.42, 1.5), (0.00, 1.0)]
```
So a bet you win < 42% of the time is capped at 1u no matter how big the edge, and 2u requires p_win >= 0.55. **This is the guardrail the owner explicitly asked for:** edge alone was pushing 1.5u onto scary low-probability YES longshots. A long price is already its own reward; do not double down on variance. Capped plays carry a visible "longshot cap" flag on the card and are still shown at 1u (the owner wants to keep taking them, just small). Do NOT remove this cap or raise the low tier back to edge-only sizing without an explicit request.

`UNIT_MAP` maps tier -> unit ceiling (S 2u, A 1.5u, B 1u, C none). All of `UNIT_MAP`, `TIER_CUTS`, and `WINPROB_CAP` are tunable constants at the top of the file; expect to retune them as the tracker calibrates.

---

## 6. Data sources and quirks

- **Kalshi** (`api.elections.kalshi.com/trade-api/v2`): no auth needed for reads. `events?...&with_nested_markets=true` for open markets; `markets?event_ticker=...&status=settled` for settlement. Settled markets expose `result` ("yes"/"no") and `expiration_value` (the actual settled temperature). Buckets carry `floor_strike`, `cap_strike`, `strike_type` ("less"/"between"/"greater"); parse those, not the title text.
- **Open-Meteo ensemble** (`ensemble-api.open-meteo.com`): free, no key, `models=gfs025,ecmwf_ifs025` pooled for ~80 members. Returns hourly per-member temps already localized to the requested `timezone`, so `t[:10]` is the local date. Also returns `utc_offset_seconds`, used for the timing guard.
- **City -> station coordinates** in `CITIES` are approximate (airport or Central Park). A wrong coordinate shows up as a persistent per-city bias on the Results tab and is auto-suppressed by the bias guard. Fixing a city means correcting its lat/lon to Kalshi's actual resolution station.
- **`CI` flag:** when `os.environ["CI"] == "true"` (GitHub Actions sets this), the script does not open a browser or wait for input. Keep it cloud-runnable and non-interactive.
- **Python version:** the workflow pins 3.12. Backslashes inside f-string expressions are a SyntaxError on 3.11 and earlier; avoid them (use a named constant like `DOT`) so the file stays portable. This exact bug broke a run once.

---

## 7. Outputs and persistence

Each run writes:
- `docs/index.html` (today's bets) and `docs/results.html` (tracker). GitHub Pages serves `/docs`.
- `weather_state.json`: `{"predictions": {...}, "resolved": [...]}`. Predictions are logged only for non-realized markets (genuine forecasts). Resolved records hold per-bucket hit, per-play win/pnl/margin, and forecast bias.

On GitHub the workflow commits these back so state persists across ephemeral runs and time off. Do not move persistence to anything needing a database or paid service; the commit-back pattern is deliberate and free.

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

- **v2 (2026-07-01):** Added the win-probability cap (`WINPROB_CAP`, `size_play`) so a large edge on a low-win-probability bet is capped at 1u instead of 1.5u+; capped plays show a "longshot cap" flag. Redesigned today's bets from a dense table into pick CARDS that lead with the exact temperature range and a large color-coded YES/NO (green/red, matching Kalshi) to stop yes/no mis-taps. Day headline now reflects max UNITS rather than tier. No change to the guards, ensemble math, settlement, or persistence.
- **v1 (2026-07-01):** Initial GitHub-deployable build. Ensemble fair value (GEFS + ECMWF), timing and bias guards, tier system (edge x lead x sharpness x city track record, S locked until a city is proven), Kalshi-settlement resolution with margin of victory, edge dashboard + results tracker (SVG charts, per-city and per-unit breakdowns, Brier vs market), twice-daily GitHub Actions with commit-back persistence. Python pinned to 3.12 after an f-string backslash SyntaxError on 3.11.

---

*When you finish a change: bump the doc version, add a changelog entry saying what changed and why, update any section above that no longer matches the code, and remind the owner to commit both `kalshi_weather.py` and `HANDOFF.md` together.*
