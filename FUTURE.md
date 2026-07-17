# Nimbus: Future Inclusions Log

**Purpose:** the running list of planned improvements, known weaknesses, and the path to automated trading. For the owner and for any AI assistant working on this project. When an item ships, move it to the HANDOFF.md changelog. When a new idea comes up in a chat, add it here so it survives the session.

**Post-audit priority order (audit batch 11, from the AUDIT_TODO section 22 table):** 1 nowcasting + midday cron: SHIPPED IN SHADOW checkpoint 1 day (2026-07-13, v13); the open step is the 30-event CRPS+RPS promotion gate, 2 NBM promotion decision: DECIDED checkpoint 1 (not adopted, pool wins by 0.311 deg, CI excludes zero), 3 bet-confirmation logging, 4 EWMA + CRPS-sigma experiments: RUN checkpoint 1 (both incumbents kept), 5 Student-t tails at 500 tail buckets (349 as of 2026-07-13, realized 2.0%, healthy), 6 privacy/deploy: DECIDED batch 12 (public through paper, private = live gate 5; Pages-via-Actions deferred again 2026-07-13 to owner-at-computer), 7 always-on runner pre-live. Explicit diminishing-returns list: more ensemble providers, extra surface variables, per-bucket CIs, portfolio optimization.

**Note (2026-07-04):** a full technical audit is in progress; `AUDIT_TODO.md` is the working list. Several items below are expected to be re-prioritized by the audit's value-of-information table (AUDIT_TODO section 22). Ideas surfaced during the audit land here as usual.

Priorities are ordered. Do not skip ahead: several items are gated on settled history that does not exist yet.

---

## 1. Now through ~100 settled bets (nothing to build, just watch)

The calibration engine needs food before anything else matters. During this period the owner's only jobs:

- [ ] Paper trade and let settlements accumulate. Bias corrections activate at 5 settled events per city, learned kernel widths at 8, the pooled width at 15.
- [ ] Watch the **Calibration** table on the Results tab. This is the single most important readout. If the 60-70% row actually hits ~60-70%, the model is honest and profit follows from the cost gate. If it misses badly, nothing else matters until it is fixed.
- [ ] Watch the **Learned corrections** table. Any city with a persistent shift above ~1.5 degrees probably has wrong station coordinates. Fix its lat/lon in `CITIES` to Kalshi's actual settlement station (the CLI station, usually the airport ASOS; NYC is Central Park). The correction handles it either way, but fixing the coordinate is cleaner.
- [ ] Watch the **By edge size** table. If 25%+ edges win less often than 8-15% edges, the plausibility cap is earning its keep and thresholds may need tightening.

## 2. Unit scaling plan (the owner's stated intent, with guardrails)

The owner wants to move toward ~$100 units, possibly betting only the 2-3 highest-probability cards per day. The plan is sound ONLY if units scale with bankroll and the by-win-probability table earns it first. Rules any AI should hold the line on:

- 1u should stay near 1-2% of CURRENT bankroll. $100 units mean a $5,000-$10,000 bankroll, not a $500 one. Raise `BANKROLL` and let `BASE_UNIT_USD` follow; never hardcode a dollar unit that breaks the percentage.
- Scale in steps after the paper gate passes (Brier below market, green P&L, 100+ bets): roughly $500 -> $1,250 -> $2,500 -> $5,000 bankroll, doubling only after 50+ live bets at the current level stay green.
- Selective high-confidence mode is approved only when the "By win probability" table (shipped v5) shows the 80%+ row with positive ROI over 30+ plays AND stated-vs-actual within ~5 points. High-probability plays win small and lose big; overconfidence there is invisible in win rate.
- Concentrating in 2-3 bets/day raises daily variance: cap total daily exposure around 4-6u early on. (SHIPPED audit batch 8: DAILY_UNIT_CAP=6.0 per target date plus EVENT_UNIT_CAP=2.0 per ladder, after measuring a 54.5u day and 5-play single-ladder stacks.) Note the model keeps learning from ALL cities regardless of which plays the owner actually bets, so selective betting never starves calibration.
- At $100+ units, liquidity starts to matter: 100-140 contracts can eat through resting depth on thin ladders. Manual mitigation: place limit orders at the board price and accept partial fills rather than market-ordering through the book. `MIN_OI` may need raising (300 -> 1000+) at that size.

**Kill criteria (pre-registered, audit batch 8):** at 150+ resolved plays under the audit build, STOP scaling and return the model to the lab if the bootstrap 90% CI on fees-inclusive ROI sits entirely below -8%, or the model-vs-market Brier gap is still positive at 800+ non-gated buckets. Passing is not proof of edge; failing is proof enough to halt.

## 2b. Retune checkpoint (after ~100 settled bets)

- [ ] Revisit `PLAY_NET_EDGE`, `EDGE_2U`, `EDGE_1_5U`, `WINPROB_CAP`, `TIER` colors against the by-edge and by-unit tables. This is a with-AI session: bring the repo files plus a copy of `weather_state.json` so the numbers drive the tune.
- [ ] Decide whether the high-confidence bucket (p_win >= 65%) is the best ROI or just the best win rate. If ROI concentrates in mid-probability plays instead, adjust what gets surfaced first.
- [ ] Consider tightening `MAX_LEAD_DAYS` from 4 to 2-3 if the lead-3+ rows underperform.
- [ ] **Spread-skill check** (audit batch 4): corr(logged member sd, |realized error|) overall and per lead, needs n>=100. Early read at n=40 was +0.14, too noisy. A real positive relationship would justify surfacing sd more prominently; a null one simplifies the display.
- [ ] **Tail audit** (audit batch 4): at 500+ buckets stated under 2%, if the Wilson lower bound of realized frequency still exceeds 2%, escalate from the TAIL_FLOOR clamp to a shape fix (Student-t kernel or sigma inflation beyond |z|>2) and retune TAIL_FLOOR. If realized frequency falls back inside the stated range as learned sigma matures, consider relaxing the clamp instead.
- [x] **EWMA bias experiment** (audit batch 9): compare the decaying-average bias correction (Cui et al. style, weight ~0.05-0.10) against the rolling-30 window on held-out settlement MAE per city/kind; adopt only if it wins at 100+ settlements. Literature supports both; our data cannot yet prefer either. **RUN at checkpoint 1 (2026-07-13, n=259 walk-forward):** rolling-30 won (MAE 1.802 vs EWMA 1.857 at 0.05 and 1.822 at 0.10). Rolling-30 KEPT. A 0.2 decay edged it by 0.009 deg but sits outside the registered range; if desired, register 0.15-0.25 as a checkpoint 2 experiment rather than adopting off a post-hoc scan.

- [ ] **CHECKPOINT 2 DOCKET (pre-registered 2026-07-13, owner session; experiments only, no knob moved today):**
  1. **Cheap-entry economics.** Motivating observation, stated with its era split so nobody later mistakes it for a clean signal: plays entered at 0.20 or below are 4/72 (-$147) on the legacy engine and 0/6 (-$63) on the audit build; every other entry band combined is 74/125 (+$309). The legacy portion is explained by the already-fixed tail overconfidence, so the open question is only whether the audit build still misprices cheap entries. GATE: 40+ audit-era plays with entry <= 0.20 OR p_win <= 0.30. TEST: realized ROI and stated-vs-realized win rate in that cell, Wilson bound vs breakeven at the average entry. REMEDIES NAMED IN ADVANCE (choose at most one if the bound clears): raise PLAY_NET_EDGE for entries below 0.20, add a MIN_ENTRY floor, or tighten the WINPROB_CAP bottom rung. Scanning other cells to rescue the hypothesis is forbidden.
  2. **EWMA decay 0.15-0.25** vs rolling-30, same walk-forward protocol as checkpoint 1, gate 350+ total settlements. Registered because 0.2 edged rolling-30 by 0.009 deg OUT OF RANGE at checkpoint 1; this makes it an honest in-range test instead of a post-hoc adoption.
  3. **Mid-band calibration read (read-only, no knob attached).** Stated 0.40-0.60 buckets realized 0.38 vs stated 0.46 at n=104 on the audit build; recheck at n>=250 with Wilson bars. If still hot after nowcasting promotes (or fails its gate), it becomes evidence for the Student-t escalation already registered at 500 tail buckets.
- [ ] **Hierarchical pooling revisit** (audit batch 9): at 30+ settlements per city, test partial pooling of bias/sigma across cities against the current shrink-toward-zero; adopt only on held-out improvement.
- [ ] **Sigma fitting experiment** (audit batch 4): refit per-city/kind and pooled sigma by minimizing the logged CRPS instead of Wang-Bishop moment matching; adopt only if pooled CRPS improves out of sample.

## 3. Play freezing, then a midday refresh run (SHIPPED, audit batch 1)

- [x] Both halves shipped 2026-07-04 in audit batch 1: plays freeze at their first non-empty log, and a third 14:43 UTC capture cron runs just after Kalshi lists next-day markets at 14:00 UTC. See HANDOFF v5.4 changelog. Residual honest caveat: a play frozen on an earlier board can differ from the board the owner actually taps; the real fix is bet-confirmation logging (item 4 below).

## 4. Quality-of-life

- [ ] **Bet-confirmation logging** (added by audit batch 1). The tracker currently scores the first board that showed each play; the owner may act on a later board. A tiny "I took this" tap per card (persisted via a query param, an issue comment, or a committed file) would make tracked P&L exactly equal taken P&L. This is the clean fix for the frozen-board vs live-board divergence.
- [ ] **Pages deploy via Actions** (added by audit batch 1). Deploy-from-branch was observed serving a board one run stale. Deploying docs/ with actions/deploy-pages inside our own workflow makes deploy failures visible as red runs and also unlocks a private repo later (privacy decision, Batch 12).
- [x] **Phone notification of the day's board.** SHIPPED audit batch 10 (Telegram, secrets-gated, non-fatal). The "what changed since yesterday" line shipped as the new-plays-24h header chip. The owner already runs a Telegram bot via Google Apps Script for work tasks; the same pattern works here. Simplest version: the Action posts a short summary (n plays, top card, link to the page) to a Telegram bot after the morning run. Secrets go in GitHub Actions repo secrets, never in code.
- [ ] **Plain-English glossary** box on the Results tab (what Brier means, what a calibration table is, what shift/width are). One paragraph each.
- [ ] **"What changed since yesterday"** line on the bets page (new plays, dropped plays, corrections that moved).

## 5. Bigger forecasting upgrades (only after the model proves itself on paper)

- [ ] **Intraday nowcasting for same-day highs.** THE top value-of-information item (batch 9 literature verdict + community validation in REDDIT_FINDINGS.md Q3). **Checkpoint 1 evidence (2026-07-13) sharpened the case:** the final board's market-implied mean beats the model by 0.43 deg point MAE (1.41 vs 1.84, n=259) even while the model's own calibration is clean (sd(z)=1.00, corrections worth +0.22 deg) and the model beats raw NBM and HRRR. That residual gap IS the intraday-observation advantage this item exists to close; it is the single measured weakness left in the system. Staged spec, prerequisites now shipped:
  - Station map: SHIPPED as `STATION_IDS` in code (batch 9), derived from the batch 1 CLI verification.
  - Mechanics: SHIPPED IN SHADOW at checkpoint 1 (2026-07-13, v13). Between 9 and 14 LST, `shadow_pass` pulls `api.weather.gov/stations/{id}/observations` since 07:00 LST, computes the running observed max, truncates every calibrated member (member := max(member, running_max)), and reprices the ladder from the truncated cloud into a write-once PAIRED snapshot beside the untruncated one. Grading attaches at resolve (rps_u/rps_t, crps_u/crps_t on the resolved record); the Results header shows the running tally.
  - Midday cron: SHIPPED, 16:10 UTC, SHADOW-ONLY (`NIMBUS_SHADOW_RUN=1` keyed off the schedule payload): it freezes no plays and refreshes no boards, so trading behavior and every existing measurement are untouched. Normal runs also collect when a city sits in the window (east snapshots on the morning cron, west at midday).
  - GATE READ 2026-07-16 at n=40 graded events: **FAILED AS REGISTERED, NO PROMOTION.** Overall RPS truncated 0.574 vs untruncated 0.573 (truncated better on only 8 of 40); CRPS 1.362 vs 1.409 (better on 15 of 40, most others tied). Mechanism: truncation BINDS (moves the mean by >0.15 deg) on only 9 of 40 days; the other 31 are ties because the running max sat below the whole member cloud. On the 9 binding days the signal is promising but thin: CRPS 1.388 vs 1.584, point error 1.98 vs 2.20 deg, per-event RPS 6 better / 1 worse / 2 tied. Plays stay on untruncated pricing. Shadow collection continues at zero cost.
  - RE-REGISTERED GATE (2026-07-16, decided before any further data): promotion reconsidered only at **25+ BINDING events** (mean shift >0.15 deg, threshold fixed now), requiring truncated to win mean CRPS AND the per-event RPS majority within the binding subset. At ~2-3 binding events/day fleet-wide this reads in roughly 6-8 weeks. If the binding subset also fails at that n, the feature is removed rather than left running.
- [x] **HRRR + NBM blending decision.** Reference LOGGING shipped in audit batch 2: every record now stores NBM and HRRR CLI-day values (`ref`) so their skill vs the pooled ensemble is measurable from settlements. **DECIDED at checkpoint 1 (2026-07-13): NOT adopted.** On 258 paired settlements the pooled ensemble beat raw NBM by 0.311 deg MAE (95% CI [0.126, 0.495]) and beat raw HRRR by more (2.40 vs 1.84 overall). The audit's adoption gate (advantage CI excluding zero at 150+ pairs) is met in the WRONG direction, so this closes with finality rather than deferring. `ref` logging stays on: it is nearly free and a seasonal regime could reopen the question in winter.
- [ ] **Lead-aware calibration.** Learn bias and width separately for lead 0-1 vs 2-4 once each city has ~30+ settlements. The plumbing (lead is stored on every resolved record) already exists.
- [ ] **Winter variables revisit** (audit batch 9): snow cover and soil moisture only matter for cold-season extremes; reassess in November alongside the seasonal split below.
- [ ] **Seasonal awareness.** Rolling 30-settlement window already adapts slowly to season; revisit whether an explicit summer/winter split earns anything after a few months of data.
- [ ] **Kalshi CLV analog** (added during audit kickoff, mirrors RidgeSeeker's CLV-first philosophy). Snapshot each play's market price at the last run before settlement and report beat-the-close rate and average price movement on the Results tab. A model that consistently beats the closing price is proving edge even before P&L converges. Depends on play freezing (item 3 above) so the entry price is stable; design lands in AUDIT_TODO section 8.

## 6. The path to automated trading (spelled out, in order)

Do not start this until the Results tab shows model Brier below market Brier AND green P&L over 100+ resolved bets. Automation multiplies whatever the model is, including its mistakes.

1. **Read-write API access.** Kalshi issues API keys (RSA key pair) for order placement. Store the private key in GitHub Actions secrets or the runner's environment. Never in the repo, never in `weather_state.json`.
2. **Shadow mode first.** The bot COMPUTES the exact orders it would place (ticker, side, price, count) and logs them without sending. Run this for 2+ weeks and compare shadow orders to what the owner would have tapped. This catches sizing bugs with zero dollars at risk.
3. **Maker orders, not market orders.** (Reinforced by community consensus in REDDIT_FINDINGS.md Q5: maker-only, minimum price ~$0.10, skip books with >10% spread; use the websocket order-book feed, not REST polling; apply for Kalshi's Advanced API tier if hitting 429s.) At 4-14 cent edges, crossing the spread eats 1-3 cents per trade. Post resting limit orders inside the spread and accept partial fills. This alone can be the difference between profitable and not at this scale.
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
- **Competition.** Confirmed and sharpened by REDDIT_FINDINGS.md: wethr.net is the community's standard analytics hub (paid tier sees data 3 minutes faster), and traders report 1-minute-data flash moves near settlement (do not leave resting orders then, live era). Nimbus's edge window is mornings and mid-probability buckets; assume near-settlement prices are efficient.
- **Forecast staleness at run time.** A 7am board is stale by noon. Mitigated by the midday refresh (item 3) and eventually nowcasting (item 5).
- **Station mismatch.** RESOLVED for now: audit batch 1 verified all 20 cities against Kalshi's own rules text (CLI products) on 2026-07-04 and fixed the one mismatch (Houston settles at Hobby, config said IAH). Residual risk is Kalshi changing a settlement station; re-verify if rules text changes.
- **Schedule reliability.** Measured, not just theoretical: in July 2026 the 12:00 UTC cron fired at 13:26 and the 02:00 UTC cron at 05:51 (+1.4h and +3.8h). Crons now sit off the hour and the pages self-flag past 16h, but GitHub remains best-effort: acceptable for paper, not for live orders. Schedules also pause after 60 days without repo activity.
- **Frozen board vs live board.** Plays freeze at their first non-empty log; the owner may bet a later, slightly different board. Conservative direction (the tracker scores the model's earliest call), but real. Fix: bet-confirmation logging (section 4).
- **State file scaling.** Policy ratified in audit batch 3 (HANDOFF section 7b): growth is ~1.5 MB/month; at 3 MB, resolved records older than 120 days split into `weather_state_archive.json`, merged at load for reporting, calibration keeps reading the live file. Implement only when the threshold trips; do not introduce a database.
- **DST transition days.** Two days a year the LST settlement window behaves oddly. Lowest priority; consider simply not betting those two days.
- **Rule risk.** Kalshi can change fees, bucket structure, or settlement sources. The parser reads strike fields rather than titles, which helps (a community post-mortem lost money misreading B-tickers as thresholds), but any structural change needs a code touch. Reassuring datapoint: the Reddit pass found no voided weather markets or post-hoc settlement amendments as of mid-2026.

---

*Maintenance rule: any AI making changes should read this file along with HANDOFF.md, and move shipped items into the HANDOFF changelog.*
