#!/usr/bin/env python3
"""
replay_selection.py - read-only play-SELECTION backtester for Nimbus.

WHAT THIS IS
------------
The forecast layer is already near-optimal (see backtest_models.py: swapping
ensemble weightings moves MAE by hundredths of a degree). The measured losses
live one layer down, in which bets get placed at what price. This replays
alternative play-selection, sizing, and pricing configs against real settled
history and reports true fees-inclusive P&L, so a candidate rule can be judged
on money rather than on a forecast score.

It reads `book0`, the write-once snapshot of the order book at the DECISION
board (the first healthy board for a market), carried onto resolved records and
stamped with each bucket's settled outcome. Everything needed to reprice and
grade a ladder is in that snapshot, so any config can be replayed offline over
all accumulated history, including configs invented long after the fact.

Records resolved before book0 shipped have no snapshot and are skipped; the
count is always printed, never silently dropped.

READ-ONLY / SIDE-EFFECT-FREE
----------------------------
Opens weather_state.json read-only, writes nothing, freezes nothing. It imports
kalshi_weather only to reuse pure helpers (fee, size thresholds, caps) so the
replay cannot drift from live pricing; importing does not execute the model.

GOVERNANCE (read CLAUDE.md and FUTURE.md)
-----------------------------------------
This is a pre-registration instrument, not a fishing rod. Racing many configs
is fine and is the point; inventing a config AFTER seeing the table and keeping
only what won is not, because at these sample sizes the best-looking cell is
usually noise. The discipline that makes a winner believable is the one docket
item 4 used: a candidate must beat the champion on the full sample AND keep
beating it on data logged after it was registered. `--since` exists for exactly
that prospective check. Adopting any winner into live pricing still requires its
own pre-registered gate, a MODEL_VERSION bump, and a Decision Log row.

USAGE
-----
    python3 replay_selection.py                  # full registered slate
    python3 replay_selection.py --since 2026-07-25   # prospective-only read
    python3 replay_selection.py --only champion  # single config
"""
import json, math, argparse, random, sys, os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kalshi_weather as kw

STATE_FILE = "weather_state.json"

# ------------------------------------------------------------------ #
#  CONFIG: every knob defaults to the live champion value, so a config
#  states ONLY what it changes. That keeps each candidate a one-knob
#  story, which is what makes a result attributable.
# ------------------------------------------------------------------ #
def cfg(name, **over):
    base = dict(name=name,
                min_entry=0.0,                     # floor on price paid (0 = off)
                max_entry=1.0,                     # ceiling on price paid
                play_net_edge=kw.PLAY_NET_EDGE,
                min_oi=kw.MIN_OI,
                max_lead=kw.MAX_LEAD_DAYS,
                lead_cap_days=kw.LEAD_CAP_DAYS,
                tail_floor=kw.TAIL_FLOOR,
                suspect_edge=kw.SUSPECT_EDGE,
                edge_2u=kw.EDGE_2U,
                edge_1_5u=kw.EDGE_1_5U,
                winprob_cap=kw.WINPROB_CAP,
                daily_cap=kw.DAILY_UNIT_CAP,
                event_cap=kw.EVENT_UNIT_CAP,
                min_pwin=0.0,                      # floor on stated win probability
                max_sd=None,                       # ceiling on decision-time member sd (None = off)
                sides="both",                      # both | yes | no
                kinds="both",                      # both | HIGH | LOW
                skip_pwin_band=None,               # (lo, hi): skip plays with lo <= p_win < hi
                skip_modal_no=False,               # skip Buy NO on the market's modal bucket
                flat_units=None)                   # None = tiered sizing
    base.update(over)
    return base

# ------------------------------------------------------------------ #
#  REGISTERED SLATE (FUTURE.md docket item 6, registered 2026-07-25).
#  Pre-registered BEFORE any book0 data existed. Add candidates by
#  appending here and recording the addition date in FUTURE.md.
# ------------------------------------------------------------------ #
SLATE = [
    cfg("champion"),
    # -- entry-price floors: the docket 1 remedy and its neighbours --
    cfg("MIN_ENTRY 0.10", min_entry=0.10),
    cfg("MIN_ENTRY 0.15", min_entry=0.15),
    cfg("MIN_ENTRY 0.20 (docket 1)", min_entry=0.20),
    cfg("MIN_ENTRY 0.25", min_entry=0.25),
    # -- win-probability floor: a different cut at the same leak --
    cfg("p_win >= 0.30", min_pwin=0.30),
    cfg("p_win >= 0.40", min_pwin=0.40),
    # -- side selection: YES plays ran 12% win rate lifetime --
    cfg("NO side only", sides="no"),
    cfg("YES side only", sides="yes"),
    # -- edge gate: is the cost gate too permissive --
    cfg("PLAY_NET_EDGE 0.06", play_net_edge=0.06),
    cfg("PLAY_NET_EDGE 0.08", play_net_edge=0.08),
    # -- plausibility cap: is an outsized edge even more suspect --
    cfg("SUSPECT_EDGE 0.15", suspect_edge=0.15),
    # -- sizing: does tiering earn anything over flat --
    cfg("flat 1u sizing", flat_units=1.0),
    # -- liquidity: is thin-book noise part of the leak --
    cfg("MIN_OI 1000", min_oi=1000),
    # -- lead: forecast skill decays fast --
    cfg("lead <= 1", max_lead=1),
    cfg("lead <= 2", max_lead=2),
    # -- expensive entries: high-prob plays win small and lose big --
    cfg("MAX_ENTRY 0.85", max_entry=0.85),
    # -- combination, registered as its own candidate not as a rescue --
    cfg("MIN_ENTRY 0.20 + NO only", min_entry=0.20, sides="no"),
    # -- spread convergence, REGISTERED 2026-07-28 (recorded in FUTURE docket 6).
    #    Motivated by the 2026-07-25 spread-skill read (corr +0.250, widest sd
    #    quartile misses 2.32 deg vs 1.52 tightest) plus an external bot's
    #    claimed convergence trigger (REDDIT_FINDINGS 2026-07-28 addendum).
    #    Thresholds were pinned to the ALREADY-MEASURED sd quartiles before any
    #    replay data existed, so they cannot be shopped after the fact. Filters
    #    read book0's frozen decision-time sd; records whose snapshot predates
    #    that field fall back to the final-board sd, and main() prints the split.
    cfg("sd <= 2.80 (skip widest qtl)", max_sd=2.80),
    cfg("sd <= 1.69 (tightest qtl only)", max_sd=1.69),
    # -- six candidates REGISTERED 2026-07-29 (owner-requested; quotes and full
    #    motivation notes recorded in FUTURE docket 6). Their prospective leg
    #    reads `--since 2026-07-29`. Honesty note fixed at registration: the
    #    belly-skip, 0.90 floor, HIGH-only, and modal-fade candidates were
    #    partly motivated by INSPECTED retrospective cells (the 2026-07-29
    #    p_win-band and era tables in audit/JULY_REDDIT_AUDIT_FINDINGS.md), so
    #    their full-sample rows are contaminated by construction and ONLY the
    #    prospective leg can promote them. The two favorite-fade candidates are
    #    structural (favorite-longshot direction, HANDOFF section 4). --
    cfg("NO only + entry >= 0.35", sides="no", min_entry=0.35),
    cfg("NO only + entry >= 0.50", sides="no", min_entry=0.50),
    cfg("skip p_win 0.80-0.90 band", skip_pwin_band=(0.80, 0.90)),
    cfg("p_win >= 0.90 only", min_pwin=0.90),
    cfg("HIGH markets only", kinds="HIGH"),
    cfg("no NO fade of modal bucket", skip_modal_no=True),
]

def _size(net, p_win, proven, lead, c):
    """size_play with config knobs. Mirrors kalshi_weather.size_play exactly."""
    if net < c["play_net_edge"]: return 0.0
    if c["flat_units"] is not None:
        u = c["flat_units"]
        return u if net < c["suspect_edge"] else min(u, 1.0)
    if net >= c["suspect_edge"]: return 1.0
    base = 2.0 if net >= c["edge_2u"] else 1.5 if net >= c["edge_1_5u"] else 1.0
    wpc = c["winprob_cap"][-1][1]
    for thr, u in c["winprob_cap"]:
        if p_win >= thr: wpc = u; break
    units = min(base, wpc)
    if lead is not None and lead >= c["lead_cap_days"] and units > 1.0: units = 1.0
    if units >= 2.0 and not proven: units = 1.5
    return units

def replay(records, c):
    """Strict prior-date walk-forward replay of one config. Returns graded plays."""
    bydate = defaultdict(list)
    for r in records: bydate[r["target"]].append(r)
    skill = defaultdict(lambda: {"bm": 0.0, "bk": 0.0, "nb": 0})   # prior-only city skill
    out = []
    for d in sorted(bydate):
        day = bydate[d]
        cands = []
        for r in day:
            b0 = r["book0"]
            if b0.get("biased"): continue          # live play gate: model vs market too far apart
            if c["kinds"] != "both" and r["kind"] != c["kinds"]: continue
            lead = b0.get("lead")
            if lead is None or lead > c["max_lead"]: continue
            # modal bucket = the market's favorite (highest mid on the decision board)
            modal = (max(b0["buckets"], key=lambda e: e["mid"])["ticker"]
                     if c["skip_modal_no"] and b0["buckets"] else None)
            if c["max_sd"] is not None:
                # decision-time member sd, frozen on the snapshot since 2026-07-28;
                # older records fall back to the record's final-board sd (the
                # stated proxy). A record with neither cannot satisfy an sd filter.
                sdv = b0.get("sd", r.get("sd"))
                if sdv is None or sdv > c["max_sd"]: continue
            proven = (lambda a: a["nb"] >= 20 and (a["bk"] - a["bm"]) / a["nb"] > 0)(
                skill[(r["code"], r["kind"])])
            for e in b0["buckets"]:
                mid, oi = e["mid"], e["oi"]
                if not (0.02 < mid < 0.98) or oi < c["min_oi"]: continue
                mp_e = min(max(e["mp"], c["tail_floor"]), 1.0 - c["tail_floor"])
                cost = (e["ya"] - e["yb"]) / 2 + kw.fee(mid) + 0.01
                edge = mp_e - mid
                if edge > 0: side, entry, net = "Buy YES", e["ya"], edge - cost
                else:        side, entry, net = "Buy NO", round(1 - e["yb"], 2), (-edge) - cost
                if c["sides"] == "yes" and side != "Buy YES": continue
                if c["sides"] == "no" and side != "Buy NO": continue
                if entry < c["min_entry"] or entry > c["max_entry"]: continue
                if modal is not None and side == "Buy NO" and e["ticker"] == modal: continue
                p_win = mp_e if side == "Buy YES" else 1 - mp_e
                if p_win < c["min_pwin"]: continue
                if c["skip_pwin_band"] and c["skip_pwin_band"][0] <= p_win < c["skip_pwin_band"][1]: continue
                units = _size(net, p_win, proven, lead, c)
                if units <= 0: continue
                cands.append({"code": r["code"], "kind": r["kind"], "target": d,
                              "ticker": e["ticker"], "side": side, "entry": entry, "net": net,
                              "p_win": p_win, "units": units, "hit": e["hit"]})
        # exposure caps, best plays first (same ordering as the live cap loop)
        cands.sort(key=lambda x: (-x["units"], -(x["p_win"] or 0), -x["net"], x["ticker"]))
        per_day = 0.0; per_ev = defaultdict(float)
        for x in cands:
            ev = (x["code"], x["kind"])
            if per_day + x["units"] > c["daily_cap"] + 1e-9: continue
            if per_ev[ev] + x["units"] > c["event_cap"] + 1e-9: continue
            per_day += x["units"]; per_ev[ev] += x["units"]
            stake = round(x["units"] * kw.BASE_UNIT_USD, 2)
            entry = x["entry"]
            contracts = int(stake // entry) if entry > 0 else 0
            won = (x["hit"] == 1) if x["side"] == "Buy YES" else (x["hit"] == 0)
            fees = math.ceil(0.07 * contracts * entry * (1 - entry) * 100) / 100 if contracts else 0.0
            pnl = contracts * ((1 - entry) if won else -entry) - fees
            out.append(dict(x, stake=stake, contracts=contracts, won=won, pnl=round(pnl, 2)))
        # city skill updates only AFTER the day is scored (no lookahead)
        for r in day:
            a = skill[(r["code"], r["kind"])]
            for e in r["book0"]["buckets"]:
                a["bm"] += (e["mp"] - e["hit"]) ** 2
                a["bk"] += (e["mid"] - e["hit"]) ** 2
                a["nb"] += 1
    return out

def agg(plays):
    n = len(plays)
    if not n: return None
    w = sum(1 for p in plays if p["won"])
    pnl = sum(p["pnl"] for p in plays)
    staked = sum(p["contracts"] * p["entry"] for p in plays)
    roi = pnl / staked if staked else 0.0
    lo = hi = None
    if n >= 25:
        rng = random.Random(13); rois = []
        for _ in range(2000):
            smp = rng.choices(plays, k=n)
            st = sum(x["contracts"] * x["entry"] for x in smp)
            if st: rois.append(sum(x["pnl"] for x in smp) / st)
        rois.sort()
        if rois: lo, hi = rois[100], rois[1899]
    return dict(n=n, w=w, wr=w / n, pnl=pnl, staked=staked, roi=roi, lo=lo, hi=hi)

def main():
    ap = argparse.ArgumentParser(description="Read-only Nimbus play-selection backtester.")
    ap.add_argument("--since", help="only targets on/after this date (prospective check)")
    ap.add_argument("--only", help="run a single config by name substring")
    args = ap.parse_args()

    with open(STATE_FILE) as f: state = json.load(f)
    allres = [r for r in state.get("resolved", []) if not r.get("gated")]
    recs = [r for r in allres if r.get("book0") and r["book0"].get("buckets")
            and all("hit" in e for e in r["book0"]["buckets"])]
    if args.since: recs = [r for r in recs if r["target"] >= args.since]
    skipped = len(allres) - len([r for r in allres if r.get("book0")])

    print(f"\nNimbus play-selection replay  |  {len(recs)} replayable events"
          + (f"  |  since {args.since}" if args.since else ""))
    print(f"  {skipped} resolved records skipped: no book0 (resolved before the snapshot shipped, "
          f"not reconstructable)")
    if not recs:
        print("\n  Nothing to replay yet. book0 attaches to records that resolve from now on;\n"
              "  the first should land within about a day of the retention change going live.\n")
        return
    nb0sd = sum(1 for r in recs if r["book0"].get("sd") is not None)
    if nb0sd < len(recs):
        print(f"  decision-time sd frozen on {nb0sd} of {len(recs)} events; sd-filter configs read the"
              f"\n  record's final-board sd as a stated proxy on the other {len(recs) - nb0sd} (FUTURE docket 6)")
    print(f"  target dates {min(r['target'] for r in recs)} -> {max(r['target'] for r in recs)}\n")

    slate = [c for c in SLATE if not args.only or args.only.lower() in c["name"].lower()]
    rows = []
    for c in slate:
        a = agg(replay(recs, c))
        if a: rows.append((c["name"], a))
    champ = next((a for nm, a in rows if nm == "champion"), None)
    rows.sort(key=lambda x: -x[1]["roi"])

    print(f"  {'config':<32}{'n':>5}{'win%':>7}{'staked':>10}{'P&L':>10}{'ROI':>8}   ROI 90% CI")
    print("  " + "-" * 100)
    for nm, a in rows:
        ci = f"[{a['lo']*100:+.1f}%, {a['hi']*100:+.1f}%]" if a["lo"] is not None else "n<25"
        tag = " *" if nm == "champion" else "  "
        print(f"{tag}{nm:<32}{a['n']:>5}{a['wr']*100:>6.1f}%{a['staked']:>10.2f}"
              f"{a['pnl']:>+10.2f}{a['roi']*100:>+7.1f}%   {ci}")
    if champ:
        print(f"\n  champion reference: {champ['n']} plays, {champ['roi']*100:+.1f}% ROI")
    print("\n  A config beating the champion here has NOT proven anything yet: with this many")
    print("  candidates the best cell is usually noise. Re-run with --since <registration date>")
    print("  and require the winner to keep winning on data logged after it was registered.\n")

if __name__ == "__main__":
    main()
