#!/usr/bin/env python3
"""
replay_timing.py - read-only BET-TIMING backtester for Nimbus (FUTURE docket 7).

WHAT THIS IS
------------
`replay_selection.py` answers "which bets should we place?" by repricing the
DECISION board. This answers the other question registered on 2026-07-28:
"is the board we freeze on the right one?"

The motivating position has been on the record since audit batch 6 and was
never measured: "the 21:38 UTC board is the information peak for next-day
markets; CLV is now the instrument that TESTS this prior instead of arguing
about it."

Two things blocked the test until the tape shipped. Bet time is not a setting:
plays freeze at the first PLAYABLE board, so the entry board is emergent, and
changing it is a behavior change needing a MODEL_VERSION bump, not a config
tweak. And there was no counterfactual price: `book0` stored the first board
and `buckets[]` the last, so every board in between was discarded.

HOW IT READS THE TAPE
---------------------
`tape` is the board-by-board price trail on a resolved record:

    [[at, mean, biased01, lead, fp, [[mp, mid, yb, ya, oi], ...]], ...]

Bucket rows are POSITIONAL against `book0`'s ladder, so this tool zips a tape
row against `book0["buckets"]` to recover each bucket's ticker, strike, and
settled `hit`. `book0` carries no `fp` of its own, so the fingerprint is
recomputed from its ticker tuple with the same hash `_tape_row` uses, and any
tape row whose `fp` differs is SKIPPED, never realigned: a differing fp means
Kalshi re-strung the ladder and position i is no longer the same contract.
Close prices for CLV come from the record's `buckets[]`, which is the final
board and is positional against the same ladder.

READ-ONLY / SIDE-EFFECT-FREE
----------------------------
Opens the state files read-only, writes nothing, freezes nothing. Sizing comes
from `replay_selection._size` and pricing constants from `kalshi_weather`, by
import rather than by copy, so this tool cannot drift from live behavior.

GOVERNANCE (read CLAUDE.md and FUTURE.md docket 7)
--------------------------------------------------
The slate, the gate, the metrics, and the adoption rule were all fixed in
writing on 2026-07-28, BEFORE any replayable board tape existed, and
deliberately without reading per-board outcomes first. This tool executes that
registration; it does not get to revise it.

ADOPTION RULE, pre-committed and not negotiable here: a candidate may be
proposed only if it beats the champion on the FULL sample with its ROI CI
excluding the champion's point ROI, AND keeps beating it on targets after
2026-07-28 (`--since 2026-07-28`). The slate is deliberately wide, so a
full-sample winner is expected by chance; the prospective leg is what
separates a rule from an artifact. If no candidate clears the gate, the
champion stands and the item closes with finality rather than being extended.

Waiting later is NOT free and this tool prices it: a later freeze forfeits
plays whose edge disappeared before that board, so skipped-play counts are part
of the verdict, not a footnote.

USAGE
-----
    python3 replay_timing.py                      # full registered slate
    python3 replay_timing.py --since 2026-07-28   # prospective leg
    python3 replay_timing.py --only board-2       # single config
"""
import json, math, argparse, random, sys, os, hashlib
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kalshi_weather as kw
from replay_selection import _size, cfg          # imported, never copied

STATE_FILE = "weather_state.json"
ARCHIVE_FILE = "weather_state_archive.json"
REG_DATE = "2026-07-28"            # docket 7 registration; prospective leg starts here

# Nominal cron minutes-of-day in UTC. GitHub fires these LATE and never early
# (measured drift runs to +7h on the 12:17 slot), so a board belongs to the most
# recent nominal cron at or before its stamp. That rule is causal rather than
# fitted: it asks which cron could have produced this board, not which one the
# numbers prefer. 16:10 is the shadow run and never appears, because a shadow
# run refreshes no board and therefore writes no tape row.
CRONS = [("12:17", 12 * 60 + 17), ("21:38", 21 * 60 + 38), ("02:07", 2 * 60 + 7)]


def board_cron(stamp):
    """Which nominal cron fired the board at this UTC stamp."""
    try:
        mins = int(stamp[11:13]) * 60 + int(stamp[14:16])
    except (ValueError, IndexError):
        return None
    best, bestgap = None, 10 ** 9
    for name, at in CRONS:
        gap = (mins - at) % (24 * 60)          # minutes SINCE that cron fired
        if gap < bestgap: best, bestgap = name, gap
    return best


def book0_fp(b0):
    """Recompute book0's ladder fingerprint; book0 does not store one."""
    return hashlib.sha1("|".join(b["ticker"] for b in b0["buckets"]).encode()).hexdigest()[:8]


# ------------------------------------------------------------------ #
#  REGISTERED SLATE (FUTURE docket 7, fixed 2026-07-28 before any
#  replayable tape existed). Do not add rows without recording the
#  addition date in FUTURE.md.
# ------------------------------------------------------------------ #
def tcfg(name, pick, note=""):
    c = cfg(name)
    c["pick"] = pick          # (record, tape_rows) -> list of usable tape indices
    c["note"] = note
    return c


def _idx(i):
    return lambda rec, rows: [i] if len(rows) > i else []


def _cron(which):
    def f(rec, rows):
        for i, row in enumerate(rows):
            if board_cron(row[0]) == which: return [i]
        return []
    return f


def _best(n):
    return lambda rec, rows: list(range(min(n, len(rows))))


SLATE = [
    tcfg("champion (first playable board)", _idx(0)),
    tcfg("freeze-at-board-2",               _idx(1)),
    tcfg("freeze-at-board-3",               _idx(2)),
    tcfg("freeze-only-on-21:38-board",      _cron("21:38")),
    tcfg("freeze-only-on-12:17-board",      _cron("12:17")),
    tcfg("best-price-of-first-2-boards",    _best(2), note="CEILING"),
    tcfg("best-price-of-first-3-boards",    _best(3), note="CEILING"),
]
# best-price-of-N is not a strategy anyone can run: picking the better of two
# boards requires knowing which one was better. HANDOFF already declares resting
# limit orders not honestly modelable at 3 boards/day. These two rows are an
# upper BOUND on what perfect timing could be worth, reported as registered and
# labeled so nobody mistakes a ceiling for a candidate.
CEILINGS = {c["name"] for c in SLATE if c["note"] == "CEILING"}


def _price_board(rec, row, fp):
    """One tape row as a priced ladder, or None if it cannot be trusted."""
    if row[4] != fp: return None               # ladder re-strung: never realign
    b0 = rec["book0"]["buckets"]
    cells = row[5]
    if len(cells) != len(b0): return None      # length drift without an fp change
    out = []
    for e, cell in zip(b0, cells):
        if "hit" not in e: return None
        mp, mid, yb, ya, oi = cell
        out.append({"ticker": e["ticker"], "mp": mp, "mid": mid, "yb": yb, "ya": ya,
                    "oi": oi, "hit": e["hit"]})
    return out


def replay(records, c):
    """Strict prior-date walk-forward replay of one timing config."""
    bydate = defaultdict(list)
    for r in records: bydate[r["target"]].append(r)
    skill = defaultdict(lambda: {"bm": 0.0, "bk": 0.0, "nb": 0})
    out = []
    for d in sorted(bydate):
        day = bydate[d]
        cands = []
        for r in day:
            rows = r["tape"]
            fp = book0_fp(r["book0"])
            idxs = c["pick"](r, rows)
            if not idxs: continue              # this config would not have traded here
            # close prices for CLV: the record's final board, same positional ladder
            closes = [b.get("mid") for b in r.get("buckets", [])]
            best = {}
            for i in idxs:
                row = rows[i]
                if row[2]: continue            # biased gate, as of THAT board
                lead = row[3]
                if lead is None or lead > c["max_lead"]: continue
                bk = _price_board(r, row, fp)
                if bk is None: continue
                proven = (lambda a: a["nb"] >= 20 and (a["bk"] - a["bm"]) / a["nb"] > 0)(
                    skill[(r["code"], r["kind"])])
                for pos, e in enumerate(bk):
                    mid, oi = e["mid"], e["oi"]
                    if not (0.02 < mid < 0.98) or oi < c["min_oi"]: continue
                    mp_e = min(max(e["mp"], c["tail_floor"]), 1.0 - c["tail_floor"])
                    cost = (e["ya"] - e["yb"]) / 2 + kw.fee(mid) + 0.01
                    edge = mp_e - mid
                    if edge > 0: side, entry, net = "Buy YES", e["ya"], edge - cost
                    else:        side, entry, net = "Buy NO", round(1 - e["yb"], 2), (-edge) - cost
                    p_win = mp_e if side == "Buy YES" else 1 - mp_e
                    units = _size(net, p_win, proven, lead, c)
                    if units <= 0: continue
                    cm = closes[pos] if pos < len(closes) else None
                    clv = None if cm is None else round(
                        (cm - mid) if side == "Buy YES" else (mid - cm), 3)
                    cand = {"code": r["code"], "kind": r["kind"], "target": d,
                            "ticker": e["ticker"], "side": side, "entry": entry, "net": net,
                            "p_win": p_win, "units": units, "hit": e["hit"], "clv": clv,
                            "board": i}
                    # best-price-of-N keeps the single most favorable board per bucket
                    k = e["ticker"]
                    if k not in best or cand["net"] > best[k]["net"]: best[k] = cand
            cands.extend(best.values())
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
        for r in day:                          # skill updates only after the day is scored
            a = skill[(r["code"], r["kind"])]
            for e in r["book0"]["buckets"]:
                # a bucket missing any of these cannot score; skip it rather than
                # crash the whole slate on one malformed record
                if e.get("hit") is None or e.get("mp") is None or e.get("mid") is None: continue
                a["bm"] += (e["mp"] - e["hit"]) ** 2
                a["bk"] += (e["mid"] - e["hit"]) ** 2
                a["nb"] += 1
    return out


def _boot(vals, stat, seed=13, blocks=None):
    """90 percent bootstrap interval. `blocks` resamples whole target dates,
    the honest unit here: cities on one weather day share their errors, so a
    play-level resample overstates the effective sample."""
    n = len(vals)
    if n < 25: return None, None
    rng = random.Random(seed); outs = []
    if blocks:
        keys = list(blocks)
        for _ in range(2000):
            smp = [v for k in rng.choices(keys, k=len(keys)) for v in blocks[k]]
            s = stat(smp)
            if s is not None: outs.append(s)
    else:
        for _ in range(2000):
            s = stat(rng.choices(vals, k=n))
            if s is not None: outs.append(s)
    if not outs: return None, None
    outs.sort()
    return outs[len(outs) // 20], outs[len(outs) - 1 - len(outs) // 20]


def _roi(ps):
    st = sum(x["contracts"] * x["entry"] for x in ps)
    return (sum(x["pnl"] for x in ps) / st) if st else None


def _clvavg(ps):
    c = [x["clv"] for x in ps if x.get("clv") is not None]
    return (sum(c) / len(c)) if c else None


def agg(plays):
    n = len(plays)
    if not n: return None
    byd = defaultdict(list)
    for p in plays: byd[p["target"]].append(p)
    roi = _roi(plays) or 0.0
    lo, hi = _boot(plays, _roi)
    blo, bhi = _boot(plays, _roi, blocks=byd)
    clv = [p["clv"] for p in plays if p.get("clv") is not None]
    clo, chi = _boot(plays, _clvavg, blocks=byd)
    return dict(n=n, w=sum(1 for p in plays if p["won"]),
                wr=sum(1 for p in plays if p["won"]) / n,
                pnl=sum(p["pnl"] for p in plays),
                staked=sum(p["contracts"] * p["entry"] for p in plays),
                roi=roi, lo=lo, hi=hi, blo=blo, bhi=bhi,
                clv=(sum(clv) / len(clv)) if clv else None, nclv=len(clv),
                clo=clo, chi=chi, dates=len(byd))


def main():
    ap = argparse.ArgumentParser(description="Read-only Nimbus bet-timing backtester (docket 7).")
    ap.add_argument("--since", help="only targets on/after this date (prospective leg)")
    ap.add_argument("--only", help="run a single config by name substring")
    args = ap.parse_args()

    with open(STATE_FILE) as f: state = json.load(f)
    res = list(state.get("resolved", []))
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE) as f: arch = json.load(f)
        seen = {(r.get("code"), r.get("kind"), r.get("target")) for r in res}
        res = [r for r in arch if (r.get("code"), r.get("kind"), r.get("target")) not in seen] + res
    allres = [r for r in res if not r.get("gated")]
    recs = [r for r in allres
            if r.get("book0") and r["book0"].get("buckets")
            and all("hit" in e for e in r["book0"]["buckets"])
            and r.get("tape") and len(r["tape"]) >= 2]
    if args.since: recs = [r for r in recs if r["target"] >= args.since]

    notape = len([r for r in allres if r.get("book0") and not (r.get("tape") and len(r["tape"]) >= 2)])
    print(f"\nNimbus BET-TIMING replay (FUTURE docket 7)  |  {len(recs)} replayable events"
          + (f"  |  since {args.since}" if args.since else ""))
    print(f"  {notape} book0-bearing records excluded: fewer than 2 taped boards, so they carry")
    print("  no counterfactual price and cannot distinguish one timing rule from another")
    if not recs:
        print("\n  Nothing to replay yet.\n"); return
    print(f"  target dates {min(r['target'] for r in recs)} -> {max(r['target'] for r in recs)}")
    bc = defaultdict(int)
    for r in recs:
        for row in r["tape"]: bc[board_cron(row[0])] += 1
    print("  taped boards by firing cron: " + ", ".join(f"{k} x{v}" for k, v in sorted(bc.items())) + "\n")

    slate = [c for c in SLATE if not args.only or args.only.lower() in c["name"].lower()]
    rows = []
    for c in slate:
        a = agg(replay(recs, c))
        if a: rows.append((c["name"], a))
    champ = next((a for nm, a in rows if nm.startswith("champion")), None)

    print(f"  {'config':<34}{'n':>5}{'win%':>7}{'P&L':>9}{'ROI':>8}   {'ROI 90% CI (by date)':<24}"
          f"{'CLV':>7}  CLV 90% CI")
    print("  " + "-" * 118)
    for nm, a in rows:
        ci = f"[{a['blo']*100:+.1f}%, {a['bhi']*100:+.1f}%]" if a["blo"] is not None else "n<25"
        cc = f"[{a['clo']:+.3f}, {a['chi']:+.3f}]" if a["clo"] is not None else "n<25"
        cv = f"{a['clv']:+.3f}" if a["clv"] is not None else "   n/a"
        tag = " *" if nm.startswith("champion") else " ^" if nm in CEILINGS else "  "
        sk = "" if champ is None else f"  ({a['n'] - champ['n']:+d} vs champ)"
        print(f"{tag}{nm:<34}{a['n']:>5}{a['wr']*100:>6.1f}%{a['pnl']:>+9.2f}"
              f"{a['roi']*100:>+7.1f}%   {ci:<24}{cv:>7}  {cc}{sk}")

    print("\n  * champion (the live rule)    ^ ceiling, not runnable: needs to know which board won")
    if champ:
        print(f"\n  champion reference: {champ['n']} plays over {champ['dates']} target dates, "
              f"{champ['roi']*100:+.1f}% ROI, CLV {champ['clv']:+.3f}")
        print("\n  ADOPTION RULE (docket 7, pre-committed 2026-07-28): a candidate may be proposed")
        print(f"  ONLY if its ROI CI excludes the champion's point ROI ({champ['roi']*100:+.1f}%) on the")
        print(f"  full sample AND it keeps beating the champion with --since {REG_DATE}.")
        print("  Skipped-play counts are part of the verdict: a config that trades less is not")
        print("  thereby better, because waiting forfeits plays whose edge died before that board.")
    print()


if __name__ == "__main__":
    main()
