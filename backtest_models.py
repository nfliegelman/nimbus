#!/usr/bin/env python3
"""
backtest_models.py - read-only forecast-config backtester for Nimbus.

WHAT THIS IS
------------
A model horse-race run against the ALREADY-LOGGED history in weather_state.json.
Every resolved record stores the raw per-provider forecast summary
(members_by_model = {provider: {n, mean, sd}}) and the settled actual, so ANY
ensemble-weighting or bias-correction config can be replayed across the full
history in one pass, ranked by forecast-quality metrics. This answers
"would a different forecast model have done better" instantly, without waiting
weeks for a live shadow to accumulate.

WHAT IT IS NOT
--------------
It does NOT reproduce P&L. When a play resolves, the record drops the order book
(yb/ya/oi) and bucket boundaries, so a challenger's *bet selection* cannot be
reconstructed retrospectively. Forecast quality (MAE, bias, RMSE, CRPS) is fully
recoverable; trading P&L needs a forward shadow. See FUTURE.md.

READ-ONLY / SIDE-EFFECT-FREE
----------------------------
Opens weather_state.json read-only, imports nothing from kalshi_weather.py,
writes nothing, freezes no plays. Safe to run inside the working tree (unlike
kalshi_weather.py). The small pure helpers below are copied verbatim from
kalshi_weather.py and validated to reproduce the logged champion mean to 1e-3.

GOVERNANCE (read CLAUDE.md)
---------------------------
This is a pre-registration instrument, not a fishing rod. The rule the project
holds (see FUTURE.md docket item 4, the template): name your candidate SLATE and
its decision gate BEFORE you look, run ONE pass, and report the WHOLE field,
winners and losers. Do not add candidates after seeing results and keep only the
best - that manufactures edge from noise. This script prints every candidate on
purpose. Adopting any of them into live pricing still requires its own
pre-registered gate, a MODEL_VERSION bump, and a Decision Log row.

USAGE
-----
    python3 backtest_models.py                # full field, all history
    python3 backtest_models.py --kind HIGH    # highs only
    python3 backtest_models.py --era audit    # audit-build records only
    python3 backtest_models.py --min-lead 0 --max-lead 1
"""
import json, math, argparse, random
from collections import defaultdict

STATE_FILE = "weather_state.json"
MODELS = ("gfs025", "ecmwf_ifs025", "icon_seamless", "gem_global")

# --- constants copied from kalshi_weather.py (keep in sync if they change) ---
BIAS_MIN_N, BIAS_LOOKBACK, BIAS_SHRINK_K = 5, 30, 5
SQRT2 = math.sqrt(2.0)

def _phi(z): return 0.5 * (1.0 + math.erf(z / SQRT2))

def _mix_mean(mm, w):
    """Weighted mean of per-provider means. Mirrors kalshi_weather._mix_mean."""
    t = sum(w.get(k, 0.0) for k in mm)
    return sum(w.get(k, 0.0) * v["mean"] for k, v in mm.items()) / t if t else None

def _crps_gauss(y, mu, s):
    """Closed-form CRPS of N(mu, s^2) vs outcome y. Lower is better."""
    if y is None or mu is None or not s or s <= 0: return None
    z = (y - mu) / s
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return s * (z * (2.0 * _phi(z) - 1.0) + 2.0 * pdf - 1.0 / math.sqrt(math.pi))

def _era(mv):
    """Legacy iff blank or a pre-audit (nimbus-calib) stamp; else audit build."""
    return "legacy" if ((not mv) or "nimbus-calib" in mv) else "audit"

# ------------------------------------------------------------------ #
#  WEIGHTING SCHEMES: mm (+ per-kind provider-error history) -> weights
# ------------------------------------------------------------------ #
def w_member_count(mm, hk):  return {k: v["n"] for k, v in mm.items()}          # champion
def w_equal(mm, hk):         return {k: 1.0 for k in mm}                        # one model, one vote

def w_skill_invmse(mm, hk):
    """Per-kind inverse-MSE skill weights over last 60 prior-date settlements,
    eps 0.25, 30-per-provider warmup. Docket item 4 challenger."""
    if all(len(hk[k]) >= 30 for k in MODELS):
        return {k: 1.0 / (sum(x * x for x in hk[k][-60:]) / len(hk[k][-60:]) + 0.25) for k in mm}
    return {k: v["n"] for k, v in mm.items()}   # warmup: fall back to member count

def _single(model):
    def w(mm, hk): return {model: 1.0} if model in mm else None
    return w

# ------------------------------------------------------------------ #
#  CANDIDATE SLATE  (pre-register here; the harness scores all of them)
#  Each entry: (name, weighting_fn, bias_scheme)  bias in {"none","roll30"}
# ------------------------------------------------------------------ #
SLATE = [
    ("champion (member-count + roll30 bias)", w_member_count,  "roll30"),
    ("member-count, NO bias correction",      w_member_count,  "none"),
    ("equal-weight per model + roll30",       w_equal,         "roll30"),
    ("skill inverse-MSE + roll30 (docket 4)", w_skill_invmse,  "roll30"),
    ("GFS only + roll30",                     _single("gfs025"),        "roll30"),
    ("ECMWF only + roll30",                   _single("ecmwf_ifs025"),  "roll30"),
    ("ICON only + roll30",                    _single("icon_seamless"), "roll30"),
    ("GEM only + roll30",                     _single("gem_global"),    "roll30"),
]
CHAMPION = SLATE[0][0]

def roll30_corr(errs):
    """Bias correction from prior raw errors: -mean(last 30) * n/(n+K), n>=MIN_N.
    Mirrors kalshi_weather.calib_params."""
    rows = errs[-BIAS_LOOKBACK:]; n = len(rows)
    if n < BIAS_MIN_N: return 0.0
    return -(sum(rows) / n) * (n / (n + BIAS_SHRINK_K))

def run(records, args):
    """Strict prior-DATE walk-forward. Returns {name: metrics}."""
    bydate = defaultdict(list)
    for r in records: bydate[r["target"]].append(r)

    # per-config bias history keyed by (code,kind); shared per-kind provider-error
    # history for the skill weighter (both updated only AFTER a date is scored).
    bias_hist = {name: defaultdict(list) for name, _, _ in SLATE}
    prov_hist = {"HIGH": {k: [] for k in MODELS}, "LOW": {k: [] for k in MODELS}}
    res = {name: {"ae": [], "signed": [], "crps": []} for name, _, _ in SLATE}

    for d in sorted(bydate):
        day = bydate[d]
        for r in day:
            mm, a, kind = r["members_by_model"], r["actual"], r["kind"]
            psd = r.get("psd")                       # shared sigma for CRPS (isolates the mean)
            hk = prov_hist[kind]
            for name, wfn, bias in SLATE:
                w = wfn(mm, hk)
                if not w: continue                   # provider absent (single-model config)
                raw = _mix_mean(mm, w)
                if raw is None: continue
                corr = roll30_corr(bias_hist[name][(r["code"], kind)]) if bias == "roll30" else 0.0
                mu = raw + corr
                res[name]["ae"].append(abs(mu - a))
                res[name]["signed"].append(mu - a)
                if psd: res[name]["crps"].append(_crps_gauss(a, mu, psd))
        # append this date's outcomes to history only after scoring it (no leakage)
        for r in day:
            mm, a, kind = r["members_by_model"], r["actual"], r["kind"]
            for name, wfn, bias in SLATE:
                if bias != "roll30": continue
                w = wfn(mm, hk)
                if not w: continue
                raw = _mix_mean(mm, w)
                if raw is not None: bias_hist[name][(r["code"], kind)].append(raw - a)
            for k in MODELS:
                if k in mm: prov_hist[kind][k].append(mm[k]["mean"] - a)
    return res

def summarize(res, records):
    champ_ae = res[CHAMPION]["ae"]
    rng = random.Random(11)
    rows = []
    for name, _, _ in SLATE:
        ae = res[name]["ae"]; sg = res[name]["signed"]; cr = [c for c in res[name]["crps"] if c is not None]
        if not ae: continue
        mae = sum(ae) / len(ae)
        bias = sum(sg) / len(sg)
        rmse = math.sqrt(sum(x * x for x in sg) / len(sg))
        crps = sum(cr) / len(cr) if cr else float("nan")
        # pairwise MAE advantage vs champion (champion_ae - config_ae), bootstrap 90% CI,
        # over the events BOTH scored (same length: full field runs on the common all-provider set)
        adv = ci_lo = ci_hi = None
        if name != CHAMPION and len(ae) == len(champ_ae):
            diffs = [champ_ae[i] - ae[i] for i in range(len(ae))]
            bs = sorted(sum(rng.choices(diffs, k=len(diffs))) / len(diffs) for _ in range(2000))
            adv, ci_lo, ci_hi = sum(diffs) / len(diffs), bs[100], bs[1899]
        rows.append((name, len(ae), mae, bias, rmse, crps, adv, ci_lo, ci_hi))
    rows.sort(key=lambda x: x[2])   # by MAE, best first
    return rows

def main():
    ap = argparse.ArgumentParser(description="Read-only Nimbus forecast-config backtester.")
    ap.add_argument("--kind", choices=["HIGH", "LOW"], help="restrict to highs or lows")
    ap.add_argument("--era", choices=["legacy", "audit"], help="restrict to a model era")
    ap.add_argument("--min-lead", type=int, help="minimum lead days")
    ap.add_argument("--max-lead", type=int, help="maximum lead days")
    args = ap.parse_args()

    with open(STATE_FILE) as f:
        state = json.load(f)
    # common comparable set: all four providers present + settled + not quarantined,
    # so every candidate scores the exact same events (fair pairwise comparison).
    records = []
    for r in state.get("resolved", []):
        if r.get("gated") or r.get("actual") is None: continue
        mm = r.get("members_by_model") or {}
        if any(k not in mm for k in MODELS): continue
        if args.kind and r["kind"] != args.kind: continue
        if args.era and _era(r.get("model_version") or "") != args.era: continue
        lead = r.get("lead")
        if args.min_lead is not None and (lead is None or lead < args.min_lead): continue
        if args.max_lead is not None and (lead is None or lead > args.max_lead): continue
        records.append(r)

    filt = [x for x in (args.kind, args.era,
                        None if args.min_lead is None else f"lead>={args.min_lead}",
                        None if args.max_lead is None else f"lead<={args.max_lead}") if x]
    print(f"\nNimbus forecast backtest  |  {len(records)} comparable events (all 4 providers, settled)"
          + (f"  |  filter: {', '.join(filt)}" if filt else ""))
    if len(records) < 30:
        print("  too few comparable events for a meaningful read.\n"); return
    dmin = min(r["target"] for r in records); dmax = max(r["target"] for r in records)
    print(f"  target dates {dmin} -> {dmax}   (strict prior-date walk-forward; lower MAE/CRPS = better)\n")

    rows = summarize(run(records, args), records)
    print(f"  {'config':<40}{'n':>5}{'MAE':>8}{'bias':>8}{'RMSE':>8}{'CRPS':>8}   MAE adv vs champ (90% CI)")
    print("  " + "-" * 108)
    for name, n, mae, bias, rmse, crps, adv, lo, hi in rows:
        tag = " *" if name == CHAMPION else "  "
        advs = "  --  (champion)" if adv is None else (
            f"{adv:+.3f}  [{lo:+.3f}, {hi:+.3f}]" + ("  CI>0" if lo > 0 else "  CI<0" if hi < 0 else ""))
        print(f"{tag}{name:<40}{n:>5}{mae:>8.3f}{bias:>+8.3f}{rmse:>8.3f}{crps:>8.3f}   {advs}")
    print("\n  MAE = mean |forecast-actual| (deg F). bias = mean signed error. CRPS uses the champion's")
    print("  logged sigma for every config, so CRPS gaps reflect the MEAN, not the spread.")
    print("  'CI>0' = beats champion with the 90% bootstrap interval excluding zero. This is a")
    print("  forecast-quality race only; adopting a winner needs its own pre-registered gate + version bump.\n")

if __name__ == "__main__":
    main()
