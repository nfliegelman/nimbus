# Nimbus Live Trading Specification (audit batch 10, Section 17 deliverable)

**Status: DESIGN ONLY. No order-placement code exists or may exist until every gate below passes.** This document is the binding contract any future implementation must satisfy. It expands FUTURE.md section 6 into testable requirements. Change it only with a Decision Log entry in HANDOFF.md.

## 0. Entry gates (all required before the first live order)
1. Paper gate: model Brier AND RPS below market over 100+ resolved non-gated events, green fees-inclusive P&L, and the batch 8 kill criteria NOT tripped.
2. Shadow gate: 14+ consecutive days of shadow mode (section 4) with zero unexplained diffs.
3. Platform gate: execution moved OFF GitHub Actions to an always-on runner (VPS, Fly.io, Railway, or a Pi). Actions cron drift of 1-4 hours is measured fact and disqualifying for live orders. GitHub Pages stays as the display layer only.
4. Secrets gate (part 1): Kalshi RSA private key lives ONLY in the runner's environment or Actions secrets. Never in the repo, never in weather_state.json, never in any log.
5. Privacy gate (audit batch 12 verdict): the repo goes PRIVATE (or state and orders move to private storage) before the first live order exists. Public-repo paper trading was consciously accepted (see HANDOFF Decision Log); public live positions and fills are not.

## 1. Intent generation
- Intents derive ONLY from frozen plays (plays_logged_at present). The live engine never invents plays the tracker did not log.
- One intent per (target, ticker, side). Resizing an existing position is a new decision requiring a new day's board, not an amendment.
- Client order id: first 20 hex chars of sha1("{target}|{ticker}|{side}|{plays_logged_at}"). Reruns regenerate identical ids; the API's idempotency then makes double-placement impossible.

## 2. Order policy: maker first
- Post a resting limit INSIDE the spread at min(model_fair - 2c, best_ask - 1c) for YES (mirrored for NO). Never cross the spread at entry.
- Reprice at most twice, each move at most 1c toward the market, then leave it or cancel. Accept partial fills; never chase.
- Minimum price 10c and maximum 90c for any entry (community-validated execution floor; the paper cost gate approximates this economically, live orders enforce it explicitly).
- No resting orders within 90 minutes of a market's expected settlement window (flash-move protection, REDDIT_FINDINGS.md Q1).

## 3. Sanity bounds (checked immediately before EVERY placement)
Refuse and log if ANY holds:
- |current mid - mid at scoring time| > 4c, or the board that produced the intent is older than 45 minutes.
- The ladder was gated this run, the city appears in cities_failed, or any drift alarm is active.
- The stale-board condition (>16h) would show on the dashboard.
- Daily or event unit caps would be exceeded counting already-filled quantity.
- The kill switch (section 5) is set.

## 4. Shadow mode (mandatory first phase)
- Compute exact intents (ticker, side, limit price, contract count, client id) and append them to orders_log.json WITHOUT sending. orders_log.json never ships in handbacks and never enters docs/.
- Daily diff: shadow intents vs the owner's actual taps (bet-confirmation log when it exists, manual notes until then). 14+ clean days required.

## 5. Kill switch
- A file named HALT at the repo root, OR env NIMBUS_HALT=1, blocks ALL placement. Checked before every order, not per run. Anyone with repo write access can stop trading from a phone in one commit.
- Reconciliation failure (section 6) writes HALT automatically.

## 6. Reconciliation
- Every cycle pulls actual fills/positions from the Kalshi portfolio API and diffs against orders_log.json intents. ANY mismatch (unknown fill, quantity drift, orphan order): cancel all resting orders, write HALT, send the Telegram alert, require manual clearance.

## 7. Sizing and scale
- Live sizing starts at 50% of paper sizing for the first calendar month, fees-inclusive.
- Bankroll-percentage sizing (and any BANKROLL raise) only after live fees-inclusive ROI is positive AND the FUTURE section 2 gates pass at the current level.
- Execution quality score logged per fill: (fill price - board mid at intent time), reviewed at each retune checkpoint.

## 8. Explicitly out of scope until revisited
Market orders, order-book sniping, sub-minute reaction to model releases, multi-account anything, and any behavior that depends on beating the wethr.net crowd on latency. Nimbus's edge thesis is mornings and mid-probability buckets, not speed.
