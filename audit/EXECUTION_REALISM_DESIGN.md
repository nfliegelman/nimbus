# Execution-Realism Instrumentation: Design, Preregistration Draft, and Patch Plan

**Status: DESIGN ONLY. Nothing in this document is implemented, and nothing in
it may be implemented without explicit owner instruction.** Produced 2026-07-29
on repository state `227e94d`, as the read-only design phase requested after
the July external audit (`audit/JULY_REDDIT_AUDIT_FINDINGS.md` sections 6 and
11.2). No forecasting, probability, selection, sizing, exposure, or registered
experiment is touched by this design, and the proposed instrumentation is
explicitly forbidden from changing any of them.

## 0. The problem being instrumented

Every historical and current paper result assumes the full intended contract
count fills at the recorded top-of-book price (`ya` for YES, `1 - yb` for NO).
Median play size is 31 contracts, mean 73, maximum 333, against ladders whose
measured median open interest is a few hundred contracts. Whether those fills
were realistic is UNKNOWABLE for the past: historical order-book depth does not
exist on any Kalshi endpoint and must never be fabricated. The design below
records enough at decision time, prospectively, to answer it going forward,
while leaving the idealized paper convention fully intact as its own series.

Four result layers are distinguished, and only the first exists today:

1. **Idealized top-of-book paper P&L** (the current convention; unchanged,
   forever, for comparability).
2. **Depth-constrained immediate-fill P&L** (shadow series computed from the
   frozen depth snapshot; fills capped by displayed size, price walked down
   the book).
3. **Resting-limit-order simulated P&L: DECLARED NOT HONESTLY MODELABLE at the
   current cadence.** Three REST snapshots a day cannot establish queue
   position, time priority, or whether displayed size ahead of a hypothetical
   order was consumed. "The market later traded through the price" does not
   imply a resting order would have filled, and 1-minute candlesticks cannot
   repair that inference. This layer is deferred to the live era, where the
   authenticated websocket `orderbook_delta` stream plus real fill
   reconciliation (already specified in LIVE_TRADING_SPEC) make it honest.
   Recording this refusal here is deliberate, so a later session does not
   quietly bolt on a flattering fill assumption.
4. **Unfilled opportunities** (the residual of layer 2: intended minus
   fillable contracts, priced at nothing, reported as counts and dollars).

## 1. Kalshi endpoints and fields (verified live 2026-07-28)

- **Batch order books:** `GET /trade-api/v2/markets/orderbooks?tickers=A&tickers=B`,
  up to 100 tickers per call, no authentication required in practice
  (live-verified; the OpenAPI security block disagrees with both the guide and
  observed behavior, so implementation must not ASSUME auth-free forever and
  must fail soft if a 401 ever appears). Response per ticker:
  `{"orderbook_fp": {"yes_dollars": [[price, qty], ...], "no_dollars": [[price, qty], ...]}}`.
- **Both sides are BID books.** A yes bid at price X is the no ask at 1 - X.
  Therefore: YES executable ask = 1 - best `no_dollars` price; NO executable
  ask = 1 - best `yes_dollars` price; quantity available to a YES taker at
  the best price = quantity on the best `no_dollars` level, and symmetrically.
  This derivation must be unit-tested, not assumed, because it is the single
  easiest thing to get silently backwards.
- **Single book fallback:** `GET /markets/{ticker}/orderbook?depth=N` (0-100
  levels; same shape).
- **Market objects** (already fetched via the nested events endpoint) carry
  `volume_fp`, `volume_24h_fp`, `open_interest_fp`, `yes_bid_size_fp`,
  `yes_ask_size_fp`: volume, OI, and top-of-book sizes come free with the
  existing pull IF the current parser surfaces them.
- **No server timestamp exists in the orderbook response.** The observation
  time is the client fetch stamp, recorded explicitly.
- **No historical order books exist** on any endpoint (confirmed against the
  full OpenAPI spec). Collection starts the day the patch ships.

## 2. Fixed-point parsing requirements

Kalshi migrated (April 2026) to string fields: prices as `*_dollars` with up
to 4 decimals (e.g. "0.4200"), quantities as `*_fp` with 2 decimals (e.g.
"816.00", fractional contracts possible). Requirements:

- Parse with `float()` and round prices to 4 decimals, quantities to 2, at
  ingestion; store as JSON numbers, not strings.
- Never parse assuming integer cents; never index characters.
- **Pre-implementation check, mandatory:** confirm which field generation the
  events endpoint the model already consumes is serving (`fget`/`fnum` paths
  in `pull_weather_markets`). The running cron proves the current parser
  works today; the depth code must match whatever it actually receives, and a
  regression test must pin both string and numeric inputs.
- Depth arithmetic (cumulative sums, VWAP) uses floats with results rounded
  to 4 decimals; fillable-contract counts round DOWN (a partial contract does
  not fill).

## 3. Rate-limit and batch implications

- All ~640 weather bucket tickers fit in 7 batch calls; the design fetches
  only ladders being priced on this run's boards, so the worst case is ~7
  extra requests per run, 3 runs a day. Negligible against any plausible
  unauthenticated throttle (authenticated Basic tier sustains ~20 reads/sec;
  unauthenticated limits are undocumented).
- Calls are made once per run, after the market pull, before scoring, with the
  same single-retry-then-absent behavior as the AI fetches. No polling, no
  websocket, no authenticated call of any kind.

## 4. Nimbus files and functions affected

- `kalshi_weather.py`:
  - NEW `fetch_orderbooks(tickers)`: isolated fetcher on the v6.23
    `fetch_ai_members` pattern: its failure, slowness, or disappearance can
    never touch the pricing fetch or abort a run. Returns
    `{ticker: {at, yes: [[p, q], ...], no: [[p, q], ...]}}`, top 5 levels per
    side, or `{}` on failure.
  - `score()`: two attachment points, both write-once:
    1. When `book0` is written (a market's genuinely first healthy board),
       attach `book0.depth` (schema below) from the same run's book fetch.
    2. When plays FREEZE this run, attach `exec0` (schema below) to each
       frozen play dict. The freeze board is the execution-relevant board and
       is not always the `book0` board; both snapshots matter and they are
       labeled distinctly.
  - `resolve_pending()`: carry `exec0` through to the resolved play (one
    `.get` copy, the v6.19/v6.26 pattern); `book0.depth` rides inside
    `book0` automatically.
  - Health strip: a `depth_missing` counter when a priced ladder had no book
    response, so silent degradation is visible.
- `replay_selection.py`: NEW read-only mode `--fills depth` computing the
  layer-2 shadow series from stored snapshots for champion and slate configs;
  prints the idealized series beside it and the count of plays lacking
  snapshots (never silently dropped).
- `test_nimbus.py`: tests in section 8.
- `HANDOFF.md` 7b: schema note. `FUTURE.md`: the preregistration entry
  (section 10 below) once the owner approves it.

## 5. Proposed immutable schema (additive, versioned, write-once)

On `book0` (per bucket, positional against `book0.buckets`):

```
book0.depth = {
  "at":   "2026-07-30T12:19Z",          # client fetch stamp (no server ts exists)
  "qage": 41,                            # seconds between market pull and book fetch
  "v":    1,                             # schema version
  "rows": [ [ [yp1,yq1],[yp2,yq2],... ], # top<=5 YES-bid levels, best first
            ...one entry per bucket, same order as book0.buckets... ],
  "nrows":[ [ [np1,nq1],... ], ... ]     # top<=5 NO-bid levels
}
```

On each frozen play (and carried to the resolved play):

```
exec0 = {
  "at": "...", "qage": 41, "v": 1,
  "bp": 0.42,      # best executable price for the play's side (from opposite bid book)
  "bq": 120.0,     # quantity displayed at that best price
  "d1": 260.0, "d2": 410.0, "d5": 900.0,   # cumulative contracts within 1c/2c/5c of best
  "vol": 1010.86, "oi": 1894.0,            # market volume and open interest at observation
  "imb": 0.63,     # yes-side share of displayed depth within 5c (0..1)
  "ic": 35,        # intended contracts (int(stake // entry), the idealized count)
  "fc": 35,        # contracts fillable at the recorded entry price
  "vwap": 0.4270,  # est. average fill price walking the book for ic contracts
  "slip": 0.0070,  # vwap minus entry, per contract
  "slipt": 0.24,   # total estimated slippage dollars for the filled quantity
  "pf": 35,        # contracts filled in the depth-constrained model (may be < ic)
  "uf": 0          # unfilled contracts (ic - pf)
}
```

Derived quantities (`d1/d2/d5`, `vwap`, `slip`, `fc`, `pf`, `uf`, `imb`) are
stored at capture time rather than recomputed later, because they are cheap,
they freeze the calculation the version stamp describes, and the raw levels
that produced them are retained on `book0.depth` for audit. Growth estimate:
`book0.depth` roughly 300-500 B per record (5 levels x 2 sides x 8 buckets,
compact), `exec0` roughly 150 B per play at ~3-4 plays/day. Net add roughly
0.9-1.4 MB/month against the amended 6 MB / 45-day archive policy: within
budget, and the archive absorbs it by design. If measurement at implementation
time exceeds this envelope, the pre-declared fallback is 3 levels per side,
never dropping the derived fields.

## 6. Backward compatibility

- Every field is optional and read through `.get`, per the 7b contract. The
  262 already-settled plays and all current pending records simply lack the
  fields forever; no backfill, no rewrite of `weather_state.json`, ever.
- The idealized P&L pipeline does not read any new field, so historical and
  future idealized results remain one unbroken, comparable series.
- Reports and the replay tool print how many plays carry `exec0` and how many
  do not, the same coverage-split convention as `book0` and frozen sd.

## 7. Failure behavior when a book is unavailable

- `fetch_orderbooks` failure (network, 4xx/5xx, schema surprise, auth change):
  return `{}` for the affected tickers; pricing, gating, logging, freezing,
  and rendering proceed exactly as today; the affected records simply lack
  depth fields; the health strip shows `depth_missing: N`.
- A partially parseable response is discarded whole for that ticker (better
  absent than wrong; a half-book would silently corrupt `fc`/`vwap`).
- Depth fetch never runs for gated ladders (degraded data must not become a
  decision snapshot) and never retries more than once per run.

## 8. Tests (network-free, realistic multi-level books)

1. NO/YES derivation: given a fixture book with yes bids [[0.40, 100], [0.39,
   50]] and no bids [[0.55, 80], [0.52, 200]], assert the YES taker's best
   executable is 0.48 with 80 available and the NO taker's best is 0.60 with
   100 available (hand-computed, both directions).
2. VWAP walk: intended 150 contracts against levels supporting 80 at best and
   200 one cent worse: assert `fc`, `pf`, `vwap`, `slip`, `slipt` to 4
   decimals, hand-computed.
3. Partial fill: intended 300 against 120 total displayed within 5c: `pf` is
   120, `uf` is 180, and the depth-constrained P&L prices only 120.
4. Exact-fit fill at best: `slip` is 0 and `vwap` equals entry.
5. Empty and missing books: no fields written, run proceeds, health counter
   increments, and a record without `exec0` flows through `compute_report`
   and the replay untouched.
6. Fixed-point parsing: string inputs ("0.4200", "816.00") and numeric inputs
   both parse; a malformed level discards the whole ticker.
7. Write-once: a second run must not overwrite `book0.depth` or a frozen
   play's `exec0` (same invariant tests as book0 and the tape).
8. Resolve carry: `exec0` survives settlement via the pipeline test (drive
   `resolve_pending` with a mocked settlement, assert the field), not via a
   hand-built resolved fixture: the v6.26 lesson.
9. Isolation: with `fetch_orderbooks` raising, `score()` output (rows, plays,
   book0, tape) is bit-identical to a run without the fetcher (the v6.23
   wild-fixture pattern).

## 9. Sandbox equivalence procedure

1. `python3 -m py_compile` on all four scripts; full test suite.
2. `compute_report` on the committed state before and after: byte-identical
   by full JSON comparison (no new key can appear, because no stored play
   carries the fields yet).
3. `replay_selection.py` default mode on the committed state: champion
   selections identical ticker-for-ticker, side, entry, units, and P&L to the
   pre-patch run (the champion row must reproduce reality or every challenger
   number is fiction).
4. CLAUDE.md sandbox double-run (copy tree, delete `.git`, `CI=true` twice):
   both runs exit 0, zero freeze violations, zero unintended plays, boards
   render, `weather_state.json` and `docs/` in the working tree untouched;
   new records in the SANDBOX state carry `book0.depth`/`exec0` with plausible
   values while all pre-existing records are unchanged.
5. Em dash sweep; CONFIG_HASH verified unchanged (no knob is added to
   `_KNOB_NAMES`: this is instrumentation, not behavior).
6. MODEL_VERSION: UNCHANGED (recording-schema precedent class v6.12 / v6.19 /
   v6.20 / v6.22 / v6.26).

## 10. Preregistration draft: evaluating execution realism (NOT yet registered)

To be entered in FUTURE.md only with owner approval, wording fixed before any
data exists:

- **Hypothesis:** idealized top-of-book paper P&L materially overstates
  depth-constrained immediate-fill P&L at current play sizes.
- **Gate:** 150 resolved plays carrying `exec0` (accrual estimate: ~3-4
  frozen plays/day, so roughly 6-8 weeks after ship).
- **Primary metrics, all fees-inclusive:** (a) median and distribution of
  `fc / ic` (executable fraction at entry); (b) the paired difference between
  idealized ROI and depth-constrained ROI over the same plays, with a 90
  percent block-bootstrap CI by target date.
- **Secondary:** slippage per contract distribution; unfilled-dollar total;
  the same splits by side, kind, entry band, and city; count of plays with no
  snapshot.
- **Pre-declared bands:** quartiles of `bq / ic` computed on the first 150
  plays, then frozen (no re-cutting).
- **Explicitly attached to NO rule.** This experiment produces a measurement,
  not a gate. Any depth-based selection rule requires its own later
  registration naming one variable and one threshold justified by this read,
  and must report expected trade-frequency reduction.
- **Reading obligations:** if the executable fraction is ~1.0 and the ROI gap
  CI includes zero, the registered conclusion is that paper results are
  execution-realistic AT CURRENT SIZE, recorded with the size caveat, and the
  instrumentation simply keeps running as the sizes grow.

## 11. Proposed additional manual-money-gate condition (PROPOSAL ONLY)

The manual-money gate is owner-governed; this section is a drafted amendment
that takes effect ONLY if the owner explicitly approves its exact text. It is
not registered, and the operative six-condition gate in FUTURE section 2 is
untouched by this document.

> Proposed condition 7: at the time the other six conditions are evaluated,
> the execution-realism read (section 10) is READABLE (150+ exec0-bearing
> resolved plays) AND the depth-constrained fees-inclusive ROI over those
> plays is positive. If the 150-play gate has not filled, condition 7 is
> simply "not yet", exactly like the play-count condition.

Trade-off stated plainly: this delays real money by roughly the same 6-8
weeks the other unfilled conditions already imply (the 100-play condition and
the cheap-entry verdict are on comparable clocks), and it protects against
scaling into a paper edge that exists only at the top of thin books. The
counterargument is in section 12; the owner can also reasonably decide the
existing six conditions plus half-of-paper live sizing already cover this
risk at small stakes.

## 12. Strongest arguments against this instrumentation

1. **It may measure a non-problem at current size.** Median play is 31
   contracts; audit batch 5 measured median spread 1c and 61 percent of
   buckets clearing MIN_OI 300. If displayed depth routinely covers 31-73
   contracts, the read will conclude "fills fine at paper scale", a result
   already suspected. Answer: that is a cheap, valuable negative that becomes
   load-bearing the moment sizes scale, which is exactly when it cannot be
   measured retroactively. But the cost argument is real and this is the
   main reason the patch is instrumentation-only with no rule attached.
2. **New failure surface.** A second Kalshi endpoint, a fixed-point parser,
   and a health counter are more code in the one script that must never
   break. Mitigation is the proven isolation pattern, but "more code, same
   blast radius" is inherently true.
3. **State growth.** Roughly +1 MB/month accelerates archive churn; the
   archive policy absorbs it, but the file that must never be corrupted gets
   bigger and busier.
4. **Observation-time mismatch.** The book is fetched minutes after the
   market pull; on a moving morning the recorded depth is not the decision
   instant's depth. `qage` records the gap honestly, but the snapshot is an
   approximation and a motivated reader could over-trust it.
5. **Threshold-shopping bait.** Logged depth features invite a future session
   to scan for the band that back-explains losses. The preregistration's
   no-rule clause and the band-freezing provision exist precisely for this,
   but the temptation cost is real.
6. **The money-gate proposal could over-gate.** At small live sizes with
   maker-first execution (already mandated by LIVE_TRADING_SPEC), taker-side
   depth constraints partially misdescribe the actual execution plan. That
   is the strongest reason to treat section 11 as optional and separable.
7. **Auth-status fragility.** The batch endpoint is auth-free today in
   practice while the spec says otherwise; if Kalshi flips it, coverage
   silently ends until noticed (the health counter is the mitigation, not a
   fix).

## 13. Language revisions applied to the findings report (same commit)

Requested tightening, applied to `audit/JULY_REDDIT_AUDIT_FINDINGS.md` so the
record does not overstate the evidence:

1. "The leak is not forecasting" class statements narrowed to: no tested
   forecast challenger (8 pre-stated configs, n=859, strict walk-forward) has
   shown a meaningful improvement, so remaining upside is being pursued in
   selection; an untested forecast improvement could still exist.
2. The core book is described as "-0.8 percent on a 69-play sample, 90
   percent block-bootstrap CI [-19.8 percent, +19.2 percent]": consistent
   with breakeven, and also with meaningfully negative or positive.
3. Registered gates described as the path to EVIDENCE, not a guaranteed path
   to profitability; several honest outcomes are "do not adopt" or "stop".
4. Experiment completion estimated from each gate's own binding-observation
   accrual, not total settlement volume: money-gate play count ~4-5 days to
   100 (83 now, ~3.9 audit plays/day); kill-criterion count ~2.5 weeks to
   150; cheap-entry cell ~5-6 weeks to 40 (14 now, ~0.7/day); selection
   replay ~7 weeks to 150 replayable plays (~3/day since book0 coverage
   began); bet-timing tape similar, starting 2026-07-28; AI-provider gate
   roughly 4-6 days after AI-bearing records reach full coverage
   (~40 settlements/day, logging began 2026-07-28); settled nowcast-priced
   plays accrue only when an edge first appears on a same-day morning board,
   which has been RARE (zero audit-era lead-0 plays so far), so that
   evaluation has no meaningful ETA and must not be given one.
