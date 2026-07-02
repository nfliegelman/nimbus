# Nimbus: Future Inclusions Log

**Purpose:** the running list of planned improvements, known weaknesses, and the path to automated trading. For the owner and for any AI assistant working on this project. When an item ships, move it to the HANDOFF.md changelog. When a new idea comes up in a chat, add it here so it survives the session.

Priorities are ordered. Do not skip ahead: several items are gated on settled history that does not exist yet.

---

## 1. Now through ~100 settled bets (nothing to build, just watch)

The calibration engine needs food before anything else matters. During this period the owner's only jobs:

- [ ] Paper trade and let settlements accumulate. Bias corrections activate at 5 settled events per city, learned kernel widths at 8, the pooled width at 15.
- [ ] Watch the **Calibration** table on the Results tab. This is the single most important readout. If the 60-70% row actually hits ~60-70%, the model is honest and profit follows from the cost gate. If it misses badly, nothing else matters until it is fixed.
- [ ] Watch the **Learned corrections** table. Any city with a persistent shift above ~1.5 degrees probably has wrong station coordinates. Fix its lat/lon in `CITIES` to Kalshi's actual settlement station (the CLI station, usually the airport ASOS; NYC is Central Park). The correction handles it either way, but fixing the coordinate is cleaner.
- [ ] Watch the **By edge size** table. If 25%+ edges win less often than 8-15% edges, the plausibility cap is earning its keep and thresholds may need tightening.

## 2. Retune checkpoint (after ~100 settled bets)

- [ ] Revisit `PLAY_NET_EDGE`, `EDGE_2U`, `EDGE_1_5U`, `WINPROB_CAP`, `TIER` colors against the by-edge and by-unit tables. This is a with-AI session: bring the repo files plus a copy of `weather_state.json` so the numbers drive the tune.
- [ ] Decide whether the high-confidence bucket (p_win >= 65%) is the best ROI or just the best win rate. If ROI concentrates in mid-probability plays instead, adjust what gets surfaced first.
- [ ] Consider tightening `MAX_LEAD_DAYS` from 4 to 2-3 if the lead-3+ rows underperform.

## 3. Play freezing, then a midday refresh run

Known quirk to fix before adding more runs: each run OVERWRITES the logged prediction for a target day with the freshest forecast. Good for measuring the model, but if the owner bets the 7am board and the 9pm run re-logs different plays, the tracker can diverge from what was actually bet.

- [ ] **Freeze plays at first log.** Buckets may refresh (calibration wants the freshest probabilities), but the `plays` list for a given city/kind/date should be written once and never overwritten. Small change in `score()`.
- [ ] **Then** add a third cron around 16:00 UTC (~11am Dallas) so same-day HIGH picks use the newest model runs before the 2pm cutoff. One line in `run.yml`. Do not add this before freezing, it makes the overwrite problem worse.

## 4. Quality-of-life

- [ ] **Phone notification of the day's board.** The owner already runs a Telegram bot via Google Apps Script for work tasks; the same pattern works here. Simplest version: the Action posts a short summary (n plays, top card, link to the page) to a Telegram bot after the morning run. Secrets go in GitHub Actions repo secrets, never in code.
- [ ] **Plain-English glossary** box on the Results tab (what Brier means, what a calibration table is, what shift/width are). One paragraph each.
- [ ] **"What changed since yesterday"** line on the bets page (new plays, dropped plays, corrections that moved).

## 5. Bigger forecasting upgrades (only after the model proves itself on paper)

- [ ] **Intraday nowcasting for same-day highs.** This is the highest-value future feature and the closest thing to what professionals do. Between ~9am and 2pm local, pull live observations from the settlement station (NWS API: `api.weather.gov/stations/{ID}/observations`), truncate every ensemble member at the running max already observed, and re-price. The market is often slow to fold in the fact that, say, 91 has already printed. Requires mapping each city to its exact CLI station ID first.
- [ ] **HRRR for short leads.** HRRR is the sharpest same-day/next-day model. Open-Meteo exposes it. Blend it in for lead 0-1 only.
- [ ] **Lead-aware calibration.** Learn bias and width separately for lead 0-1 vs 2-4 once each city has ~30+ settlements. The plumbing (lead is stored on every resolved record) already exists.
- [ ] **Seasonal awareness.** Rolling 30-settlement window already adapts slowly to season; revisit whether an explicit summer/winter split earns anything after a few months of data.

## 6. The path to automated trading (spelled out, in order)

Do not start this until the Results tab shows model Brier below market Brier AND green P&L over 100+ resolved bets. Automation multiplies whatever the model is, including its mistakes.

1. **Read-write API access.** Kalshi issues API keys (RSA key pair) for order placement. Store the private key in GitHub Actions secrets or the runner's environment. Never in the repo, never in `weather_state.json`.
2. **Shadow mode first.** The bot COMPUTES the exact orders it would place (ticker, side, price, count) and logs them without sending. Run this for 2+ weeks and compare shadow orders to what the owner would have tapped. This catches sizing bugs with zero dollars at risk.
3. **Maker orders, not market orders.** At 4-14 cent edges, crossing the spread eats 1-3 cents per trade. Post resting limit orders inside the spread and accept partial fills. This alone can be the difference between profitable and not at this scale.
4. **Hard risk rails, in code, before the first live order:**
   - max exposure per market, per city, per day (e.g. 1 play per city/kind/day, max 6u/day total)
   - a kill switch: one env var or repo file that halts all order placement
   - idempotency: every intended order gets a client ID derived from (date, ticker, side) so a rerun can never double-place
   - sanity bounds: refuse any order whose price moved more than X cents from scoring time
5. **Platform move.** GitHub Actions is the right platform for the current paper phase (free, firewall-proof, commit-back persistence) but the WRONG platform for live orders: scheduled runs can be delayed by many minutes and are paused after 60 days of repo inactivity. When real orders flow, move execution to a small always-on runner (a $5/month VPS, Fly.io/Railway free tier, or a Raspberry Pi at home) and keep GitHub Pages purely for dashboards.
6. **Reconciliation.** Every run pulls actual fills from the Kalshi portfolio API and diffs them against intended orders. Any mismatch halts trading and flags the dashboard.
7. **Scale rule.** Live sizing starts at half of paper sizing for the first month. Bankroll percentage sizing only after fees-inclusive ROI is positive live.

## 7. Known weaknesses (honest list, keep it current)

- **Fees vs edge at small size.** Kalshi's fee is largest near 50 cents. At a sub-$500 bankroll, fees plus spread eat a large share of a 4-8 cent edge. The cost gate accounts for this, but it means thin months even when the model is right. This is skill-building scale, not income scale.
- **Competition.** These markets have sharp regulars with live station feeds (the wethr.net crowd). Nimbus's edge window is mornings and mid-probability buckets; assume near-settlement prices are efficient.
- **Forecast staleness at run time.** A 7am board is stale by noon. Mitigated by the midday refresh (item 3) and eventually nowcasting (item 5).
- **Station mismatch.** Approximate coordinates vs the exact CLI station remains the biggest silent accuracy risk. The bias guard suppresses it and the learned shift corrects it, but per-city coordinate verification is the real fix.
- **Schedule reliability.** GitHub can delay cron runs several minutes and pauses schedules after 60 days without repo activity. Acceptable for paper; not for live orders.
- **State file scaling.** `weather_state.json` in git is fine for years of daily records at this volume. If it ever exceeds a few MB, archive old resolved records to a second file; do not introduce a database.
- **DST transition days.** Two days a year the LST settlement window behaves oddly. Lowest priority; consider simply not betting those two days.
- **Rule risk.** Kalshi can change fees, bucket structure, or settlement sources. The parser reads strike fields rather than titles, which helps, but any structural change needs a code touch.

---

*Maintenance rule: any AI making changes should read this file along with HANDOFF.md, and move shipped items into the HANDOFF changelog.*
