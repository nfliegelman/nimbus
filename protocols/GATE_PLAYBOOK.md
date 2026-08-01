# Gate Execution Playbook

**Purpose:** every armed gate in this project already has its decision made in
writing. This playbook makes gate-time work MECHANICAL: what to read, the
exact threshold, the pre-committed action, and the exact steps to execute it.
It exists so that any future session, on any model, or the owner following
along by hand, can execute a gate without needing judgment beyond honest
reading. If a situation is not covered here or in FUTURE.md, the answer is
NOT improvisation: record the reading, change nothing, and wait for an owner
decision.

**Session preamble for any AI executing this playbook (paste or point it
here):** read `CLAUDE.md`, `HANDOFF.md` (sections 0b, 4, 7b, Decision Log),
and `FUTURE.md` first. Absolute rules: never run `kalshi_weather.py` in the
working tree (sandbox procedure is in CLAUDE.md); never edit
`weather_state.json` or `docs/`; no em dashes anywhere; one knob family per
commit; every behavior change ships with a MODEL_VERSION bump, a HANDOFF
changelog entry, and a Decision Log row IN THE SAME COMMIT; validation before
any commit is `python3 -m py_compile kalshi_weather.py`, `python3
test_nimbus.py` (all tests green), the sandbox double-run, and the em dash
sweep. The PR validate workflow re-runs all of it and gates the merge.

**Standard read commands** (read-only, safe in the working tree):

    python3 replay_selection.py                    # selection race, full slate
    python3 replay_selection.py --since <date>     # prospective leg
    python3 backtest_models.py                     # forecast race incl. AI rows

Gate tallies (cheap cell, money gate, CLV, kill legs, nowcast, challenger)
render live on `docs/results.html` every run; the raw record is
`weather_state.json` (merge `weather_state_archive.json` via `reporting_view`
semantics once it exists, per HANDOFF 7b).

---

## Gate 1: cheap-entry tripwire (FUTURE docket 1) - THE MOST LIKELY FIRST ACTION

- **Status feed:** the "cheap cell" tile on results.html; gate is 40 audit-era
  plays with entry <= 0.20 OR p_win <= 0.30 (16/40 as of 2026-07-31, pace
  ~0.7/day, expect the read around late August 2026).
- **Pre-committed remedy (owner-approved 2026-07-16, no fresh judgment
  permitted):** if at 40 plays the cell's fees-inclusive ROI is negative AND
  the Wilson 90 percent upper bound on its hit rate sits below breakeven plus
  3 points at the cell's average entry, then MIN_ENTRY 0.20 ships
  automatically. If the condition does not hold, the cell stays open and
  re-reads at 80. No alternative remedies, no re-scan, no threshold edits.
- **Wilson check snippet** (k wins of n, avg entry e; breakeven is e):

      python3 -c "import math;k,n,e=1,40,0.11;z=1.645;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;m=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;print('upper',round(c+m,4),'vs breakeven+3pts',round(e+0.03,4))"

- **EXECUTION IS PRE-WIRED.** `kalshi_weather.py` carries a dormant
  `MIN_ENTRY = 0.0` knob already threaded through the cost gate and
  unit-tested inert. The entire remedy is:
  1. Set `MIN_ENTRY = 0.20`.
  2. Add `"MIN_ENTRY"` to `_KNOB_NAMES` (CONFIG_HASH moves, correctly).
  3. Bump `MODEL_VERSION` to `<date>.v16-minentry` (or next free number).
  4. Changelog entry + Decision Log row quoting the gate reading and the
     2026-07-16 pre-commitment; note the docket 6 MIN_ENTRY replay rows as
     corroboration but the tripwire executes on its own terms regardless.
  5. Full validation, PR, merge on green.

## Gate 2: manual-money gate (FUTURE section 2, six conditions)

- **Status feed:** the "Path to production" block renders all six conditions
  live. No code executes at this gate: when all six read MET, the owner may
  begin manual money per the approved scaling ladder ($500 -> $1,250 ->
  $2,500 -> $5,000, doubling only after 50+ green live bets at a level, units
  at 1-2 percent of bankroll). An AI session's only job is to verify the six
  readings against the raw state and say so plainly. Amending any condition
  requires explicit owner approval quoted verbatim; a general expression of
  trust does not count (CLAUDE.md).

## Gate 3: kill criteria (pre-registered, amended 2026-07-16)

- At 150+ audit-build plays: STOP scaling and return to the lab if the 90
  percent bootstrap CI on fees-inclusive ROI sits entirely below -8 percent,
  OR at 150+ clv-bearing plays the 90 percent CI on average CLV sits entirely
  below zero. **Firing is pre-committed:** the correct execution is to say it
  fired, halt any scaling talk, and open a lab review; softening or deferring
  a fired kill is forbidden to every session including the owner's
  enthusiasm of the day.

## Gate 4: selection race (FUTURE docket 6, 31 candidates)

- **Gate:** 150+ replayable champion plays (19/150 as of 2026-07-31, ~3/day,
  expect mid-September 2026).
- **Read:** full slate plus `--since 2026-07-25 / -28 / -29` per candidate's
  registration date (dates are recorded in FUTURE docket 6 and in the SLATE
  comments; sensitivity rows print with an `s` tag and are not promotable).
- **Adoption standard (strengthened 2026-07-29, verbatim in FUTURE docket 6):**
  full-sample paired uplift >= 2c/contract with the date-blocked 90 percent
  CI excluding the champion; prospective uplift >= 1c/contract with CI
  excluding zero; 60+ plays in the changed cell; drawdown <= 120 percent of
  champion; sign stable across HIGH/LOW and calendar halves. A winner ships
  as its own single-knob commit with MODEL_VERSION bump; a prospective
  failure retires the candidate permanently. If no candidate clears, the
  champion stands and that is a successful outcome.

## Gate 5: bet-timing replay (FUTURE docket 7)

- 150+ plays with a 2+ board tape (4/150 as of 2026-07-31; slow feed). Same
  adoption discipline as gate 4; skipped-play counts are part of the verdict.

## Gate 6: source-consensus shadow (FUTURE docket 8)

- 150+ champion plays carrying `book0.source_mp` (4/150 as of 2026-07-31,
  ~2-3/day; expect late September to October 2026). Support definition,
  arms, metrics, and the 60-percent-frequency-reduction rejection clause are
  fixed in the registration; read with the docket 4 walk-forward discipline.

## Gate 7: AI providers (FUTURE section 5)

- 150+ settlements carrying both `ncep_aigefs025` and `ecmwf_aifs025`
  (80/150 as of 2026-07-31, ~40/day: reads within days).
- **Read:** `python3 backtest_models.py`, the `member-count + AI providers`
  row. **Adopt only if** it beats the champion on full-sample MAE with the
  90 percent CI excluding zero AND holds a positive advantage on targets
  after 2026-07-28. Otherwise the providers stay evidence-only and the
  question closes until a season boundary. At first read, also register the
  replacement-stack row (gfs + ecmwf_ifs + both AI, dropping icon + gem) per
  the findings report section 11.4, registration date = date added.

## Gate 8: rain model race (FUTURE 5b, 13 candidates)

- First read at 200 graded city-days (46/200 as of 2026-07-31, ~15/day:
  expect around 2026-08-10). Metrics fixed at registration: Brier vs market
  mid primary; log loss and BSS vs walk-forward climatology secondary;
  Wilson reliability deciles; every CI date-blocked (rain is frontally
  correlated across cities, so effective n is closer to days than city-days
  and no verdict may be read from a city-day CI).
- A TRADING PROPOSAL is allowed only at 400+ graded city-days with the
  champion-designate (or a 200-read winner that kept winning prospectively)
  beating the market mid with the date-blocked CI excluding zero AND
  Wilson-bounded calibration. Trading itself then needs its own spec, owner
  approval, and a MODEL_VERSION bump. If the CI includes zero at 400:
  continue evidence-only, re-read at 800, close at a season boundary if
  still null. An early read where the market leads (as at 46 city-days) is
  NOT a verdict and must not trigger early shutdown or early tuning.

## Gate 9: calibration upgrades that unlock on data volume

- **Lead-aware calibration** and **hierarchical partial pooling** (FUTURE 2b
  and 5) unlock at 30+ settlements per city/kind (HIGH pairs reached 30 on
  2026-07-31; LOW pairs days behind). These are EXPERIMENTS to run, not
  changes to make: walk-forward comparison against the incumbent per the 2b
  protocol, adopt only on held-out improvement with a CI excluding zero,
  one knob family per commit. The EWMA-style decays and CRPS-fit sigma are
  CLOSED questions; do not re-run them without a new registration.

## Gate 10: nowcast era and mid-band watch (FUTURE dockets 3, 5)

- Nowcast is LIVE (v15). Its paired shadow tally keeps accumulating; no gate
  is pending unless calibration degrades (watch sd(z) and the mid-band read
  at 250+ audit-era buckets in the 0.40-0.60 band, which feeds the already
  registered Student-t escalation decision).

---

## Standing prohibitions that bind every executor

No retrospective cell-scanning; no threshold chosen after seeing results; no
combining knob families; no acting on cells under ~30-40 samples; no
softening a fired kill criterion; no editing money-gate or kill text without
verbatim owner approval; no auto-switching champions on trailing scoreboards
(the promotion rules ARE the switching mechanism); a "do not adopt" outcome
is a success, record it and close the gate. When in doubt: record the
reading, change nothing, ask the owner.
