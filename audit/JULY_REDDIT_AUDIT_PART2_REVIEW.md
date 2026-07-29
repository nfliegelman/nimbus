# Decision Memo: Skeptical Review of JULY_REDDIT_AUDIT_PART2

**Reviewer:** in-repo session with full read access to `weather_state.json` (964
settled events, 262 settled plays, state at PR #11 head). Written 2026-07-29.
Every Nimbus number below was recomputed from the raw record this session; the
report's external citations could NOT be resolved (see section 2) and are
graded on that basis. This memo recommends registrations; it registers nothing
and changes nothing by itself.

## 1. Executive conclusion

The report's strategic direction is right (abstention over forecasting) and its
top target is right (the stated 0.80-0.90 win-probability band). But its
proposed number-one NEW rule, a tougher edge hurdle inside that band, is
**mis-matched to the mechanism the data actually shows**. A fresh diagnostic
run for this review found that the band's failure is a measured winner's curse,
not miscalibration: buckets the model states at 10-20% YES realize 15.6% across
all 1,249 of them, essentially perfect, while the 51 such buckets Nimbus chose
to FADE realized 45.1% YES. The model is right in aggregate and wrong precisely
where the market disagrees with it enough to create an apparent edge. A
bigger-edge hurdle inside the band selects for MORE disagreement and can
therefore make the curse worse, not better. The rule that matches the measured
mechanism is either the outright band skip (already racing) or
shrink-toward-market for selection purposes, which is the single best genuinely
new candidate (section 11.B). The report's sample-size arithmetic is also
optimistic by roughly 3x: it assumed 20-25 cents per contract of P&L
volatility, while the actual record shows 42 cents (49 cents on the core book),
which pushes honest detection thresholds for small effects out by months to
years and strengthens the report's own closing case for restraint.

## 2. Research-quality audit

A structural finding first: the stored report's citations are dead. Every
source appears as a "citeturn..." placeholder with no resolvable URL, title,
or author for most claims. The named works (Page and Clemen; Ottaviani and
Sorensen; Whelan; Baker and McHale; Chu, Wu and Swartz; Cont, Kukanov and
Stoikov; White; Hansen) are real literature, but the single most load-bearing
external claim, "a recent Kalshi paper using 300,000+ contract prices" with
specific numbers (sub-10-cent contracts losing over 60%, makers earning +2.6%
above 50 cents, weather included in the rejection of unbiasedness), cannot be
identified or checked from the document. Grading:

| Claim | Class | Basis |
|---|---|---|
| Nimbus's 0.80-0.90 band realizes ~54-61% | STRONGLY SUPPORTED | Reproduced: lifetime 53.8% (n=52), audit era 42.9% (n=21), 80%+ overall 64.6% (n=79). The report's 19-29 points of overstatement is if anything conservative; lifetime band overstatement is 31 points |
| Favorite-longshot bias exists in prediction markets broadly | MODERATELY SUPPORTED | Consistent real literature; magnitudes and after-fee survival on Kalshi weather specifically rest on the unresolvable Kalshi paper |
| Kalshi-specific numbers (60% tail losses, +2.6% maker favorites) | UNVERIFIABLE AS CITED | Dead placeholder citations; treat as plausible external claims only |
| Cheapest longshots lose after fees | STRONGLY SUPPORTED FOR NIMBUS | Own record: entries at or below 0.10 are 5.1% win rate (n=59); 0.10-0.20 entries -65.1% ROI (n=27); the docket 1 tripwire already targets this |
| Prices bias toward 0.5 (Page-Clemen), noise trader models | MODERATELY SUPPORTED | Real PM literature; transfer to daily weather ladders (12-36 hour horizon, verifiable physical outcome) is weaker than to long-horizon political markets |
| Regression postprocessing can make ensembles too sharp; skew helps | MODERATELY SUPPORTED, PARTLY MISAPPLIED | Real meteorology literature, but Nimbus's own record shows clean unconditional calibration in the relevant probability range (below), so this mechanism is NOT the band's driver here |
| Kelly shrinkage under estimated edge | STRONGLY SUPPORTED AS THEORY | Statistical theory; transfers cleanly; Nimbus already sizes at ~1/6 to 1/13 Kelly |
| Depth predicts impact/fill quality (Cont et al.) | MODERATELY SUPPORTED, WEAK TRANSFER | Equities microstructure; direction transfers, magnitudes do not; Kalshi book evidence is thin |
| 150-play gate catches only medium-large improvements | SUPPORTED, UNDERSTATED | Correct direction, but with measured sigma of 42-49c/contract rather than the assumed 20-25c, the thresholds roughly triple (section 8) |
| "Makers do better than takers" | PLAUSIBLE, MISAPPLIED SCOPE | Even if true, Nimbus's paper convention is taker-style; relevant only to the live era, where LIVE_TRADING_SPEC already mandates maker-first |

Domain-transfer summary: the statistical theory transfers fully; the
meteorological calibration literature transfers but is contradicted as a
mechanism by Nimbus's own cleaner data; sports-betting and equities evidence
transfer directionally at best; the only directly on-point market evidence
(Kalshi-wide) is unverifiable as stored.

## 3. Diagnosis of the 0.80-0.90 band (ranked, with measured signatures)

Composition first, because it reframes everything: the band is 52 plays, of
which 51 are Buy NO fades of buckets the model priced at 10-20% YES (avg
stated mp 15.3%), mostly HIGH markets, 30 legacy / 21 audit era. "The 80-90
band" is really "the NO-fade-of-a-15%-bucket trade".

1. **Winner's curse / conditional selection bias (adverse selection at the
   play filter). RANK 1, measured.** All mp 0.10-0.20 buckets: stated 15.0%,
   realized 15.6% (n=1,249). The FADED subset realized 45.1% YES (23 of 51).
   The forecast layer is calibrated; the selection layer buys exactly the
   cells where the market's higher price was information the ensemble lacked.
   This is a selection issue; a selection rule can mitigate it. It is also the
   same mechanism the repo already documented for the cheap tail (aggregate
   tails stated 14.4 realized 15.2 at n=960, played tails 0/9).
2. **Market probabilities contain information absent from the ensemble.
   RANK 2, same signature as 1 viewed from the other side.** For same-day and
   next-day highs the market ingests intraday observations continuously;
   Nimbus prices from model cycles plus (since v15) the same-day floor. The
   fix class here is information (nowcasting, already live) rather than
   filtering.
3. **Small-sample variance. RANK 3, real but insufficient.** n=51 with 23
   hits against an expected ~8 under calibration: binomial probability of a
   deviation this large is far below 1%, even before clustering corrections
   halve the effective n. Variance alone does not explain it, though it
   inflates the magnitude.
4. **Bucket-discretization / local distribution error. RANK 4, plausible
   contributor.** A half-degree mean error moves adjacent 1-degree bucket
   probabilities by several points; fades concentrate near the market's modal
   region where this is sharpest. Partially a forecast issue; the registered
   modal-fade-skip candidate tests its selection-side consequence.
5. **Underdispersion / kernel limitations. RANK 5, contradicted here.**
   sd(z)=1.00 on 259+ records, unconditional bucket calibration clean in the
   relevant ranges, and the CRPS-fit sigma challenger LOST out of sample.
   The report's postprocessing citations are good literature that this record
   happens to have already answered.
6. **Station/settlement risk. RANK 6, largely closed.** Stations verified
   against CLI rules text (batch 1); no voided or amended weather settlements
   found community-wide.
7. **Marginal-vs-conditional probability error. RANK 7, this is mechanism 1
   restated formally.** p(bucket) is valid marginally; p(bucket | model
   disagrees with market by 20+ points) is a different, worse-calibrated
   quantity. Any fix must condition on selection, which is what
   shrink-to-market does.

## 4. Ranked test queue (max 8; scores explained)

Priority = E (expected cents/contract on affected trades, 1-5) x P (probability
effect is real, 0-1) x I (implementation ease, 1-3) / N (required settled
plays in the affected cell, in hundreds). Sigma for N uses the measured
42-49c/contract with a 1.5x date-clustering design effect.

| # | Rule (exact preregistration) | Mechanism | Evidence | E cents | Downside | Rejects | Early warn / provisional / promote | Duplicate? | Priority |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Skip stated p_win in [0.80, 0.90) | Removes the measured winner's-curse cell | Own record: 31-point overstatement, n=52; mechanism measured this review | 15-25 on band trades (historical; true forward effect plausibly 5-10) | Forfeits any real edge in-band; ~20% of plays | ~20% | 40 / 80 / 150 in-band-eligible plays | YES (racing since v6.29) | high, already covered |
| 2 | Selection-shrink: use p_sel = 0.75 x model + 0.25 x market mid for the edge and p_win calculations, selection ONLY (logged mp unchanged) | Directly discounts disagreement, the measured failure axis; keeps trading where the model's residual signal survives the discount | Mechanism measured (section 3.1); shrinkage theory | 3-8 across the whole book | Shrinks all edges: trade count drops broadly (~30-50% fewer plays); one more parameter to defend | 30-50% | 60 / 120 / 200 differing plays | NO, genuinely new | HIGHEST NEW |
| 3 | Disagreement cap: skip when abs(mp - mid) > 0.25 | Rejection-form of the same mechanism; blunter than 2 | Same; SUSPECT_EDGE 0.15 candidate only caps SIZE above 0.15 net, never rejects | 2-6 on affected trades | Could remove the rare genuine dislocation | 5-10% | 40 / 80 / 150 affected | Partially (SUSPECT_EDGE races sizing, not rejection) | high |
| 4 | Band-specific hurdle: net edge >= 0.08 inside p_win [0.80, 0.90) | The report's top new pick | Report only | NEGATIVE under mechanism 1: selects deeper disagreement inside the cursed cell | Worst case actively harmful | ~10% | n/a | NO, and should NOT be added | REJECTED by this review |
| 5 | Uncertainty-scaled hurdle: net edge >= 1.5 x sigma(p_bucket), sigma from a member bootstrap | Rejects noisy small edges | Kelly-under-uncertainty theory | 2-4 on marginal trades | Overlaps the spread-filter candidates (sd quartiles) already racing; sigma(p_bucket) correlates with member sd | 15-30% | 80 / 150 / 250 differing | PARTIAL (sd <= 2.80 / 1.69 candidates) | medium, defer until the sd candidates read |
| 6 | Depth sufficiency: displayed executable depth >= 3 x intended contracts | Paper-honesty, not alpha | Microstructure direction only | 1-3 accounting honesty | Needs unbuilt instrumentation (EXECUTION_REALISM_DESIGN) | unknown | after depth logging exists | NO | medium, blocked on instrumentation |
| 7 | Cheap-entry ban <= 0.20 | Tail FLB defense | Own record, strongest cell | 5+ | Forfeits tail wins (rare) | ~15% | tripwire already armed at 40 | YES (docket 1 auto-remedy) | covered |
| 8 | Executable-close CLV metric (tape-based; measurement, not a filter) | Replaces mid-based CLV with yb/ya-based once the tape matures | CLV literature direction | 0 direct | none | 0% | 150 taped plays | NO (metric, not rule) | add as derived metric |

## 5. Existing vs genuinely new

- **Already adequately tested by the race:** band skip (#1), cheap-entry ban
  (#7, plus the pre-committed tripwire), entry floors/ceilings, p_win floors,
  NO-only / YES-only / HIGH-only, OI floor, lead caps, flat sizing, spread
  (sd) filters, favorite fades, modal-fade skip.
- **Existing candidate to reinterpret:** SUSPECT_EDGE 0.15 should be read as a
  weak disagreement treatment (it only downsizes); if the winner's-curse
  mechanism holds, its replay row will look better than the champion for the
  wrong-sized reason, and the honest comparison is against #3's rejection
  form. Also: p_win >= 0.30 has been historically 100% co-extensive with
  MIN_ENTRY 0.20 (every low-p_win play was also a cheap entry); its row adds
  nothing until those sets diverge.
- **Genuinely new and worth adding:** #2 selection-shrink (one parameter,
  0.25, fixed now), #3 disagreement cap (0.25, fixed now), #8 executable CLV
  as a metric. NOT worth adding: #4 (mechanism-mismatched), #5 (wait for the
  sd candidates to read first; adding a correlated variant now just thickens
  the multiple-testing penalty).

## 6. Edge floors vs band rejection vs haircuts vs shrinkage

Under the measured condition (globally calibrated model, conditionally
miscalibrated exactly where selection happens, noisy edges, informative market
prices, n < 300):

- Raising the global edge floor is dominated: it taxes every trade to treat a
  localized disease, and PLAY_NET_EDGE 0.06/0.08 rows are already racing.
- Band rejection is robust and simple but treats the symptom cell only; the
  same curse plausibly operates outside the band at smaller magnitude.
- An uncertainty haircut treats forecast noise but not market information.
- Edge >= k x sigma(edge) is theoretically clean but adds an estimated
  quantity with its own error, and overlaps the racing sd filters.
- **Shrink-toward-market for selection only is the most robust framework**: it
  is monotone in the measured failure axis (disagreement), it degrades
  gracefully (a correct model still trades where its signal is strong), it
  needs one pre-fixed parameter, and it nests the others (full shrink = never
  trade, zero shrink = champion). Recommended primary framework, registered as
  ONE candidate with lambda = 0.25, never tuned on the full history.

## 7. Favorite-longshot economics after Nimbus's costs

Per-contract costs at representative prices (exact fee formula, plus measured
median spread of 1 cent and the 1 cent buffer): entry 0.15, ~1.6-2.6c
all-in; entry 0.35, ~2.9-3.9c; entry 0.50, ~3.25-4.25c; entry 0.85, ~2.4-3.4c.

- Cheap YES longshots: Nimbus's own record is decisive (5.1% win at <= 0.10;
  -65% ROI at 0.10-0.20). Ban supported; tripwire armed. No new action.
- Expensive YES favorites (entry >= 0.80): own record 13/13 wins, +19% ROI,
  n=13. Far too small; the racing MAX_ENTRY 0.85 and p_win >= 0.90 rows are
  the honest tests.
- Buying NO against a favorite: this is where the winner's curse bit (the
  faded 15% buckets). The published FLB magnitudes (2-5 points on longshot
  prices, where verifiable at all) are of the same order as the 3-4c all-in
  cost near mid prices, so a generic NO-fade earns roughly zero after costs
  unless the model adds real information; Nimbus's band record shows the
  information ran the other way. The registered NO-only-at->=0.35/0.50 rows
  will price this properly.
- Weather-specific evidence: essentially none that is independent and
  verifiable; the report concedes this and this review confirms it.

## 8. Multiple testing, sample sizes, and promotion

Measured inputs this review: per-contract P&L sigma 42c (full book), 48.6c
(entry > 0.20 core); plays cluster hard by date (median 5, max 45 per target
date; cross-city same-day error concordance for temperature measured at ~51%),
so apply a design effect of ~1.5-2 and block every bootstrap by TARGET DATE.
One-sided alpha 0.10, power 0.80, PAIRED uplift vs the champion (the right
design: variance accrues only on differing trades):

- 4c/contract uplift on differing trades: ~500-950 differing plays.
- 2c: ~2,000-3,800 differing plays (years at current cadence).
- 1c: ~8,000-15,000 (not detectable at this scale; do not pretend otherwise).
- A filter affecting 20% of plays needs those counts IN THE AFFECTED CELL,
  so multiply calendar time by ~5.

Framework recommendation for ~26 correlated candidates at hundreds (not
thousands) of observations: (a) paired uplift vs champion, date-blocked
bootstrap, exactly as replay_selection already does; (b) the registration-date
prospective leg as the multiplicity control: it is a clean holdout and is
ALREADY the house rule, and at this sample scale it does more real work than
White/Hansen machinery, which needs longer series to have power; (c) report
the full slate every read (already done); (d) an ECONOMIC floor for promotion:
point uplift >= 2c/contract on the full sample AND >= 1c prospectively, with
the date-blocked 90% CI excluding zero on the prospective leg; (e) no
mid-course threshold edits, no new variants added after a read without a new
registration date. Deflated-Sharpe and FDR add little here; Bayesian
hierarchical shrinkage across candidates is attractive in principle but is
overkill for a slate this size and would itself need registration.

The honest restatement of the report's caution: the 150-play gate can flag
rules worth WATCHING; promotion at the report's implied confidence needs the
prospective leg to keep confirming for months. That is what the standing rule
already requires.

## 9. Closing-line value

Use as a diagnostic and a secondary ranking signal; never as a hard filter.
Kalshi weather closes embed intraday observations (measured: the final board
beats the morning model by 0.43 deg MAE), so negative CLV against the close
partly measures the market learning weather, not Nimbus erring. Mechanical
convergence, thin-book noise, and mid-vs-executable gaps all argue the same
way. The current money-gate CLV leg (average CLV positive with its CI above
zero) is acceptable as a SUPPORTING condition and should stay; a hard
per-trade CLV filter should not exist. Preregistered improvement (metric
only): once the board tape holds 150+ multi-board plays, define executable CLV
as entry price vs the LAST taped board's executable price for the same side
(yb/ya, not mid), report it beside mid-CLV, and require nothing of it. With
CLV standard deviation about 5-6c and clustering, averages become meaningfully
informative around 150-250 plays, consistent with the existing 150-play kill
leg.

## 10. Paper-execution stress test

The replay currently assumes every intended contract fills at top-of-book:
median 31, mean 73, max 333 contracts against ladders whose median OI was 488.
Risk is real but unquantifiable historically (no depth data exists, none may
be fabricated). Recommended stress design, all prospective, per
EXECUTION_REALISM_DESIGN: record displayed depth at the decision board; replay
fills as min(intended, displayed within 1c) with VWAP walking for the
remainder up to 5c; apply a queue-uncertainty penalty by honoring only a
pre-fixed fraction (0.75) of displayed size at the best level; report at
standardized sizes 10 / 35 / 100 / 350 contracts; never credit a fill the
displayed book could not supply. Conservative default paper-fill assumption
once data exists: 75% of displayed best-level size, then walk, cap at 5c
worse. Until the instrumentation ships, the only honest statement is the one
already in the findings report: idealized paper P&L is an upper bound,
tightest at small size.

## 11. Final decision memo

**A. Immediate actions (analysis/preregistration only):**
1. Record the winner's-curse diagnostic (section 3.1) beside the docket 6
   registration so the band candidates are read against the right mechanism.
2. Register the selection-shrink candidate (B below) and the disagreement cap
   (skip if abs(mp - mid) > 0.25), parameters fixed now, prospective leg from
   their registration date.
3. Adopt the economic promotion floor (section 8d) into the docket 6 adoption
   rule wording at its next owner-approved edit; and correct the working
   assumption sigma from 20-25c to the measured 42-49c everywhere sample
   sizes are discussed.

**B. Best new selection test (exact preregistration draft):**
"Selection-shrink lambda 0.25: for selection, sizing, and gating ONLY, compute
p_sel = 0.75 x mp_e + 0.25 x mid and use p_sel wherever mp_e enters edge,
p_win, and the cost gate; logged mp, calibration learning, and displayed
probabilities are unchanged. Registered into the docket 6 replay slate with
registration date = the date added; full-sample row contaminated by
construction (motivated by the 2026-07-29 winner's-curse diagnostic);
promotable only on the prospective leg under the slate's standing adoption
rule plus the section 8d economic floor."

**C. Best existing candidate:** MIN_ENTRY 0.20 (docket 1's pre-committed
remedy) on prior evidence strength; among the newer rows, the p_win
[0.80, 0.90) band skip has the strongest mechanism backing after this review.

**D. Tests to abandon (or demote to sensitivity rows):** the band-specific
8-point hurdle (mechanism-mismatched, do not add); p_win >= 0.30 (empirically
co-extensive with MIN_ENTRY 0.20 to date; keep computing, stop treating as an
independent candidate); MIN_ENTRY 0.10 and 0.15 (sensitivity shadows of the
0.20 remedy); YES-only (economically dominated in all evidence, n tiny);
sd <= 1.69 tightest-quartile-only (rejects ~75% of trades, cannot reach its
sample in any reasonable horizon).

**E. Promotion standard (single paragraph, for the next owner-approved
governance edit):** a selection candidate replaces the champion only if ALL
hold: 150+ replayable plays overall AND 60+ plays in the cell the rule
actually changes; full-sample paired uplift >= 2c/contract with the
date-blocked 90% CI excluding the champion; prospective (post-registration)
paired uplift >= 1c/contract with its date-blocked CI excluding zero; maximum
drawdown of the candidate book no worse than 120% of the champion's over the
same window; the uplift's sign stable across the HIGH/LOW split and across
calendar halves of the sample; and the change ships as its own single-knob
commit with MODEL_VERSION bump and Decision Log row. A candidate that fails
prospectively is retired, not retuned.

**F. The case for doing nothing (strongest three):**
1. The measured winner's curse implies the market is usually right when it
   disagrees with the model by enough to clear the gate. Filters can shrink
   the losses from that fact, but they cannot manufacture the informational
   edge whose absence causes it; the residual book after perfect filtering
   may simply be small and near-zero EV, which is what the core book
   (-0.8%, CI [-19.8, +19.2]) already looks like.
2. With sigma at 42-49c/contract and heavy date clustering, every effect
   small enough to still be plausible is at or beyond the edge of
   detectability at 4 plays/day. The honest expected outcome of the race is
   "no promotable winner", and that outcome should be treated as an answer,
   not a failure.
3. Every dollar of measured damage outside variance is already covered by an
   armed, pre-registered instrument (cheap-tail tripwire, band-skip row,
   nowcast information channel). Additional rules now mostly add
   multiple-testing burden to a record that needs quiet accumulation more
   than it needs new ideas.
