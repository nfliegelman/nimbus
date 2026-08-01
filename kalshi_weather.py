#!/usr/bin/env python3
"""
Nimbus  -  Kalshi weather edge, GitHub-deployable
=================================================
Runs headless on GitHub Actions (twice daily). Each run:
  * RESOLVES past paper bets using Kalshi's OWN settled result + settled temp
    (authoritative win/loss and margin of victory, straight from Kalshi).
  * SCORES today's forecastable markets, sizes each play in UNITS
    (2u / 1.5u / 1u / no bet) from a confidence score, guards out realized and
    station-offset markets.
  * WRITES two dashboards into docs/ for GitHub Pages:
       docs/index.html    -> today's bets
       docs/results.html  -> performance tracker (charts + raw data)
  * Persists everything to weather_state.json (committed back by the Action).

Confidence -> units is fully tunable in UNIT knobs below; we adjust as the
scorecard calibrates. Stdlib only.
"""

import json, math, os, sys, time, webbrowser, hashlib, random
import urllib.request, urllib.parse
import datetime as dt
from collections import defaultdict

# ------------------------------ knobs ------------------------------
BANKROLL      = 500.0
BASE_UNIT_USD = round(BANKROLL * 0.02, 2)     # 1u = 2% of bankroll ($10 at $500)
UNIT_MAP      = {"S": 2.0, "A": 1.5, "B": 1.0, "C": 0.0}   # tier -> units (0 = no bet)
# Win-probability caps. A bet you rarely WIN is high-variance no matter how big
# the edge, so cap its size. A long price is already its own reward. p_win is the
# model prob the *position* wins (mp for YES, 1-mp for NO). Tunable.
WINPROB_CAP   = [(0.55, 2.0), (0.42, 1.5), (0.00, 1.0)]   # p_win >= x -> max units
# Edge-band base sizing (net edge in probability, after spread+fee). Bigger edge
# earns more size UP TO A POINT: an edge past SUSPECT_EDGE is almost always the
# model being wrong or a thin market, not free money, so we size it DOWN and flag it.
SUSPECT_EDGE  = 0.20     # net edge above this is treated as noise, capped to 1u + flagged
EDGE_2U       = 0.14     # net edge for a 2u ceiling (also needs proven city + win prob >= .55)
EDGE_1_5U     = 0.08     # net edge for a 1.5u ceiling
# Stamp every logged bet so history survives model changes and tunes can be compared.
MODEL_VERSION = "2026-07-25.v15-nowcast-live"
# Exposure caps (audit batch 8). Measured before caps: 54.5u staked on a single
# target date against a $500 bankroll, and up to 5 plays stacked on one ladder
# (31 of 44 played events carried 2+), i.e. multiples of one settlement number.
# Cross-city error-sign concordance measured at 51% (effectively independent),
# so the binding correlation lives WITHIN an event and the binding risk is raw
# daily exposure: bootstrap median max drawdown was -$255 (p95 -$461) at the
# uncapped sizing. Best plays (by units, then p_win) fill first; the rest are
# never logged (their counterfactual stays reconstructible from the buckets).
DAILY_UNIT_CAP = 6.0   # total units per TARGET date (FUTURE section 2 guidance)
EVENT_UNIT_CAP = 2.0   # total units riding one ladder / one settlement number
# Pre-scoring integrity GATE (audit item 0.8, owner-approved in batch 7).
# A ladder or city that fails produces NO plays and NO logged prediction: a
# degraded forecast must reach neither the board nor the calibration history.
# Refinement vs the 0.8 draft, documented in HANDOFF v5.8: degraded-data
# records are excluded from LOGGING too, because bias/sigma learned from a
# 1-2 model forecast is not the statistic applied to healthy forecasts.
GATE_MIN_LADDERS = 25   # below this the Kalshi pull is truncated: abort the run
GATE_MIN_MEMBERS = 90   # three healthy models minimum is 92 pooled members
GATE_MIN_MODELS  = 3    # of the 4 ensemble models must have contributed
# Tail humility clamp (audit batch 4). Measured: buckets the model stated at
# 0-2% (avg 0.3%) realized ~6.8% (n=118, Wilson lower bound 3.5%; tail misses
# cluster within busted ladders, so treat the magnitude as directional).
# Gaussian kernel tails are too thin for temperature busts, and a fake NO edge
# on an ultra-thin tail passes the cost gate quietly. For EDGE and p_win the
# model prob is clamped into [TAIL_FLOOR, 1-TAIL_FLOOR]; the displayed and
# logged mp stays RAW so the calibration tables keep seeing the true model.
# Revisit the value at 500+ tail buckets (rule in FUTURE.md section 2b).
TAIL_FLOOR = 0.015
MIN_OI        = 300
PLAY_NET_EDGE = 0.04
# DORMANT (pre-staged 2026-07-31 for the docket 1 tripwire; see
# protocols/GATE_PLAYBOOK.md gate 1). At 0.0 this floor is provably inert
# (every entry price exceeds it; unit-tested bit-identical). It is
# deliberately NOT in _KNOB_NAMES while dormant so CONFIG_HASH does not move
# for a no-op. If the pre-committed remedy fires at the 40-play gate, the
# entire behavior change is: set 0.20, add "MIN_ENTRY" to _KNOB_NAMES, bump
# MODEL_VERSION, changelog + Decision Log in the same commit. Do not set any
# other value without its own registration.
MIN_ENTRY     = 0.0
MAX_LEAD_DAYS = 4
LEAD_CAP_DAYS = 3        # plays 3+ days out are capped at 1u; forecast skill decays fast
BIAS_TOL      = 2.0
INTRADAY_HIGH_CUTOFF = 14
NOWCAST_MIN_LHR = 9      # nowcast SHADOW snapshots collect no earlier than this local hour (FUTURE 5 stage 1); upper bound is INTRADAY_HIGH_CUTOFF
# Four independent global ensembles pooled: ~143 members (GFS 31, ECMWF 51, ICON 40, GEM 21).
# Multi-model diversity beats more members from one model.
ENSEMBLE_MODELS = ["gfs025", "ecmwf_ifs025", "icon_seamless", "gem_global"]
# Reference point forecasts logged alongside every prediction and NEVER scored:
# NBM is NOAA's station-calibrated National Blend of Models, HRRR the sharpest
# short-lead CONUS model. Their skill vs the pooled ensemble is judged from
# settled results before any blending decision (audit batches 4-5).
REF_MODELS = ["ncep_nbm_conus", "ncep_hrrr_conus"]
# AI ensembles, EVIDENCE-ONLY (FUTURE 5, added 2026-07-28): NOAA's AI-augmented
# GEFS (31 members) and ECMWF's AIFS ensemble (51), served by the same keyless
# ensemble API. Fetched in their OWN per-model calls and logged into
# members_by_model beside the four pricing providers; they never enter the
# pooled cloud, the weighted cloud, or the integrity gate's member and model
# counts (every pricing path iterates ENSEMBLE_MODELS, and the gate counts
# pms, which these never join). Pricing is identical with or without them,
# unit-tested. Promotion into pricing requires its own pre-registered gate
# (FUTURE 5); the race runs in backtest_models.py once settlements carry them.
# Deliberately NOT in _KNOB_NAMES: evidence logging, not a behavior knob, so
# CONFIG_HASH is unaffected.
AI_ENSEMBLE_MODELS = ["ncep_aigefs025", "ecmwf_aifs025"]
# KXRAIN evidence shadow (FUTURE 5b, registered 2026-07-29, owner-approved).
# Kalshi's daily "measurable rain" binaries settle on the SAME CLI climate
# reports and stations as the temperature ladders (rules cite CLINYC etc;
# trace counts as 0, so YES means >= 0.01 inch), and their city suffixes are
# exactly the 20 codes in CITIES (verified live 2026-07-29). Evidence-only:
# forecasts and prices are logged write-once and graded at settlement, no rain
# play is ever generated, every fetch is isolated so a rain outage can never
# touch temperature pricing, and main() wraps the whole pass non-fatally.
# Deliberately NOT in _KNOB_NAMES: evidence, not behavior.
RAIN_SERIES = "KXRAIN"
RAIN_WET_IN = 0.01                    # CLI measurable-precip threshold, inches
RAIN_WET_MM = round(RAIN_WET_IN*25.4, 3)   # 0.254 mm, Open-Meteo units
# A grid-cell ensemble drizzling 0.3 mm is not the same claim as a station
# gauge recording 0.01 inch: grid precip is smoother and wetter than a point.
# The 1.0 mm variant is logged from day one so the threshold-mapping question
# is answerable from the record instead of argued from priors.
RAIN_WET1_MM = 1.0
# Open-Meteo publishes per-model run metadata at
# api.open-meteo.com/data/{id}/static/meta.json; forecast responses themselves
# carry no run id. Ensemble-API model names map to different metadata ids.
META_IDS = {"gfs025":"ncep_gefs025","ecmwf_ifs025":"ecmwf_ifs025",
            "icon_seamless":"dwd_icon_eps","gem_global":"cmc_gem_geps",
            "ncep_nbm_conus":"ncep_nbm_conus","ncep_hrrr_conus":"ncep_hrrr_conus",
            # AI evidence models; the divergent spellings are Open-Meteo's own
            # (ensemble id aigefs vs metadata id aigfs, verified live 2026-07-28)
            "ncep_aigefs025":"ncep_aigfs025","ecmwf_aifs025":"ecmwf_aifs025_ensemble"}
# --- calibration (learned automatically from settled results) ---
# Kernel dressing: each member is smeared with a Gaussian so 1-degree bucket
# probabilities are smooth instead of noisy member counts. Width is learned per
# city/kind from realized errors (Wang-Bishop second-moment matching), clamped.
DRESS_SIGMA_DEFAULT = 1.1   # deg F, used until a city has enough settled history
DRESS_SIGMA_MIN     = 0.6
DRESS_SIGMA_MAX     = 3.0
# Rolling bias correction: shift members by the negative of the city's recent
# raw forecast bias vs Kalshi settlement, shrunk toward 0 when history is thin.
BIAS_MIN_N    = 5     # settled events needed before any correction applies
BIAS_LOOKBACK = 30    # only the most recent N settlements count (season drift)
BIAS_SHRINK_K = 5     # correction = -mean_bias * n/(n+K)
# --- provider weighting (docket 4, adopted 2026-07-25 on its pre-registered gate) ---
# Per-kind inverse-MSE pooling. Values are the ones the gate was measured
# under; changing any of them makes the measured advantage inapplicable.
PROVIDER_W_WARMUP   = 30    # prior settlements per provider PER KIND before weighting engages
PROVIDER_W_LOOKBACK = 60    # most recent settlements per provider that count
PROVIDER_W_EPS      = 0.25  # floors a lucky provider: without it one tiny MSE takes the cloud
HICONF_PWIN   = 0.65  # plays with win prob >= this get the high-confidence tag
# Legacy tier-score thresholds. Sizing is now done entirely in size_play (edge
# bands + win-prob/plausibility/lead/proven caps); the old tier_for scorer that
# consumed this was removed. RETAINED (unused) only to keep it in _KNOB_NAMES so
# CONFIG_HASH and the calibration-era fingerprint stay continuous with all prior
# records. Do not delete without accepting a one-time era split.
TIER_CUTS = [("S", 0.12), ("A", 0.08), ("B", 0.05), ("C", 0.03)]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "docs")
STATE_PATH = os.path.join(HERE, "weather_state.json")
# State archive (HANDOFF 7b, ratified audit batch 3, AMENDED 2026-07-28).
# The original policy said "at 3 MB, archive resolved records older than 120
# days". Those two numbers were never mutually satisfiable: at the growth rate
# of the day (1.5 MB/month) the file reaches 120 days of history at about 6 MB,
# so the trigger would always fire while nothing was old enough to move, and
# the policy would run as a permanent no-op. Measured 2026-07-28 with the file
# at 2.37 MB and its whole history 27 days old: zero records qualified.
#
# The amendment derives both numbers from the one real constraint instead of
# picking them independently. The pricing path deliberately reads the LIVE file
# only, and its longest lookback is calibration's BIAS_LOOKBACK of 30
# settlements per city/kind, which at roughly one settlement per pair per day
# is about 30 calendar days. ARCHIVE_KEEP_DAYS is that with 50 percent
# headroom. ARCHIVE_TRIGGER_MB is then the steady-state size that window
# implies at current growth (about 0.117 MB/day with the board tape, so 45 days
# is roughly 5.3 MB), rounded up so the trigger cannot fire before the window
# can answer it. Re-derive both together if growth changes; changing one alone
# recreates the original inconsistency.
ARCHIVE_PATH = os.path.join(HERE, "weather_state_archive.json")
ARCHIVE_KEEP_DAYS = 45     # resolved records younger than this stay in the live file
ARCHIVE_TRIGGER_MB = 6.0   # live-file size that starts a split
KBASE = "https://api.elections.kalshi.com/trade-api/v2"
# -------------------------------------------------------------------

CITIES = {
    "ATL":(33.6301,-84.4418,"America/New_York","Atlanta (ATL)"),
    "AUS":(30.1830,-97.6799,"America/Chicago","Austin (AUS)"),
    "BOS":(42.3606,-71.0097,"America/New_York","Boston (Logan)"),
    "CHI":(41.7868,-87.7522,"America/Chicago","Chicago (Midway)"),
    "DAL":(32.8975,-97.0203,"America/Chicago","Dallas (DFW)"),
    "DC":(38.8485,-77.0341,"America/New_York","Washington (DCA)"),
    "DEN":(39.8466,-104.6562,"America/Denver","Denver (DEN)"),
    "HOU":(29.6454,-95.2789,"America/Chicago","Houston (Hobby)"),
    "LAX":(33.9416,-118.4085,"America/Los_Angeles","Los Angeles (LAX)"),
    "LV":(36.0719,-115.1633,"America/Los_Angeles","Las Vegas (LAS)"),
    "MIA":(25.7932,-80.2906,"America/New_York","Miami (MIA)"),
    "MIN":(44.8831,-93.2289,"America/Chicago","Minneapolis (MSP)"),
    "NOLA":(29.9934,-90.2581,"America/Chicago","New Orleans (MSY)"),
    "NYC":(40.7790,-73.9693,"America/New_York","New York (Central Park)"),
    "OKC":(35.3889,-97.6008,"America/Chicago","Oklahoma City (OKC)"),
    "PHIL":(39.8729,-75.2407,"America/New_York","Philadelphia (PHL)"),
    "PHX":(33.4277,-112.0037,"America/Phoenix","Phoenix (PHX)"),
    "SATX":(29.5337,-98.4698,"America/Chicago","San Antonio (SAT)"),
    "SEA":(47.4444,-122.3138,"America/Los_Angeles","Seattle (SEA)"),
    "SFO":(37.6189,-122.3750,"America/Los_Angeles","San Francisco (SFO)"),
}
# ASOS/ICAO station ids for each city's Kalshi settlement station, derived
# from the rules-text CLI products verified 2026-07-04 (audit batch 1, e.g.
# CLIDFW -> KDFW, CLINYC -> KNYC Central Park, CLIHOU -> KHOU Hobby).
# INERT today: this is the prerequisite map for intraday observation
# truncation (nowcasting, FUTURE section 5) via api.weather.gov
# /stations/{id}/observations. Do not guess these; re-verify against
# rules_secondary if Kalshi changes a settlement source.
STATION_IDS={"ATL":"KATL","AUS":"KAUS","BOS":"KBOS","CHI":"KMDW","DAL":"KDFW",
             "DC":"KDCA","DEN":"KDEN","HOU":"KHOU","LAX":"KLAX","LV":"KLAS",
             "MIA":"KMIA","MIN":"KMSP","NOLA":"KMSY","NYC":"KNYC","OKC":"KOKC",
             "PHIL":"KPHL","PHX":"KPHX","SATX":"KSAT","SEA":"KSEA","SFO":"KSFO"}
# Legacy Kalshi series codes that differ from our CITIES keys (NYC's original
# high-temp series is KXHIGHNY, so the code after the prefix is "NY").
SERIES_ALIAS={"NY":"NYC"}
# NWS Climate Reports (the Kalshi settlement source) record the daily high/low in
# Local STANDARD Time year-round. During DST the settlement day therefore runs
# 1:00 AM to 12:59 AM local clock time, not midnight to midnight. We shift hourly
# forecast timestamps back to LST before picking each day's high/low so our "day"
# is the same day Kalshi settles. Standard UTC offsets are fixed per zone (hours):
STD_OFFSET_H={"America/New_York":-5,"America/Chicago":-6,"America/Denver":-7,
              "America/Phoenix":-7,"America/Los_Angeles":-8}

# Config fingerprint (audit batch 12). Every logged record carries an 8-hex
# hash of the behavior knobs, so a knob edited WITHOUT a MODEL_VERSION bump
# still splits cleanly in later analysis instead of silently blending eras.
_KNOB_NAMES=("BANKROLL","BASE_UNIT_USD","UNIT_MAP","WINPROB_CAP","SUSPECT_EDGE",
 "EDGE_2U","EDGE_1_5U","DAILY_UNIT_CAP","EVENT_UNIT_CAP","GATE_MIN_LADDERS",
 "GATE_MIN_MEMBERS","GATE_MIN_MODELS","TAIL_FLOOR","MIN_OI","PLAY_NET_EDGE",
 "MAX_LEAD_DAYS","LEAD_CAP_DAYS","BIAS_TOL","INTRADAY_HIGH_CUTOFF","NOWCAST_MIN_LHR",
 "DRESS_SIGMA_DEFAULT","DRESS_SIGMA_MIN","DRESS_SIGMA_MAX","BIAS_MIN_N",
 "PROVIDER_W_WARMUP","PROVIDER_W_LOOKBACK","PROVIDER_W_EPS",
 "BIAS_LOOKBACK","BIAS_SHRINK_K","HICONF_PWIN","TIER_CUTS","ENSEMBLE_MODELS","REF_MODELS")
CONFIG_HASH=hashlib.sha1(repr([(k,globals()[k]) for k in _KNOB_NAMES if k in globals()]).encode()).hexdigest()[:8]
MON={"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
TODAY=dt.date.today()
DOT="\u00b7"   # middot, kept out of f-string expressions for py3.11 safety
# Client-side staleness guard: the page carries its own build epoch and warns
# when it is more than 16h old. Catches failed scheduled runs AND failed GitHub
# Pages deploys (observed 2026-07-04: Pages served a board one run behind the
# repo, showing a profit that no longer existed). Plain string, not an f-string,
# because the JS braces would need doubling.
STALE_JS=("<div id='stale' style='display:none;background:#2a1a12;color:#e3a23c;"
 "padding:9px 16px;font-size:12.5px;border-bottom:1px solid #3a2a1a'></div>"
 "<script>(function(){var el=document.getElementById('stale');"
 "var h=(Date.now()/1000-%d)/3600.0;if(h>16){el.style.display='block';"
 "el.textContent='Stale board: last successful update was '+Math.round(h)+"
 "' hours ago. A scheduled run or the Pages deploy has not landed; check the repo Actions tab.';}})();</script>")

# ----------------------------- helpers -----------------------------
def fget(url, tries=3):
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"kw/3.0"})
            with urllib.request.urlopen(req,timeout=45) as r: return json.load(r)
        except Exception as e:
            if i==tries-1: print("   fetch failed:",str(e)[:90]); return None
            time.sleep(1.0)

def fnum(x,d=None):
    try: return float(x)
    except (TypeError,ValueError): return d

def parse_date_code(c):
    try: return dt.date(2000+int(c[:2]),MON[c[2:5]],int(c[5:7]))
    except Exception: return None

def round_nws(x): return int(math.floor(x+0.5))

def bucket_range(b):
    st=b["stype"]
    if st=="less":    return (-999, (b["cap"] or 999)-1)
    if st=="greater": return ((b["floor"] or -999)+1, 999)
    if st=="between": return (b["floor"], b["cap"])
    return (-999,999)

def margin_deg(actual,b,won):
    lo,hi=bucket_range(b)
    lo_e,hi_e=lo-0.5,hi+0.5
    if lo<=round_nws(actual)<=hi:
        mag=min(actual-lo_e,hi_e-actual)
    else:
        mag=min(abs(actual-lo_e),abs(hi_e-actual))
    return round(mag if won else -mag,1)

def bucket_rep(b):
    if b["stype"]=="between" and b["floor"] is not None and b["cap"] is not None: return (b["floor"]+b["cap"])/2
    if b["stype"]=="less"    and b["cap"]   is not None: return b["cap"]-1.5
    if b["stype"]=="greater" and b["floor"] is not None: return b["floor"]+1.5
    return None

def bucket_id(b): return f'{b["stype"]}:{b["floor"]}:{b["cap"]}'
def fee(p):
    """Per-contract taker fee RATE under Kalshi's quadratic schedule
    (fee_type "quadratic", fee_multiplier 1, read live from the series API,
    audit batch 6): 0.07*p*(1-p) dollars. Unrounded here because the cost gate
    consumes it as a rate; the real charge rounds UP to the next cent per TRADE
    and is applied that way in resolve_pending. The old round(...,2) was wrong
    in both directions (undercharged ~0.5c/contract near 30c, overcharged near 50c)."""
    return max(0.07*p*(1-p),0.0)
def pstdev(xs):
    if len(xs)<2: return 0.0
    m=sum(xs)/len(xs); return math.sqrt(sum((x-m)**2 for x in xs)/len(xs))

# --------------------------- data fetch ----------------------------
def _ladder_contiguous(strikes):
    """Structural integrity of one ladder from ALL parsed strikes (before the
    quote filter drops unquoted buckets): exactly one 'less', one 'greater',
    a chained run of 'between's, no gaps or overlaps. Strictly stronger than
    the 0.8 draft's probability-sum test and immune to its false positive
    (an illiquid unquoted tail bucket). A False here means Kalshi changed the
    bucket structure or the parser broke: gate the ladder, touch the code."""
    less=[s for s in strikes if s[0]=="less"]; grt=[s for s in strikes if s[0]=="greater"]
    bet=sorted([s for s in strikes if s[0]=="between"],key=lambda s:(s[1] if s[1] is not None else -1e9))
    if len(less)!=1 or len(grt)!=1 or not bet: return False
    try:
        if less[0][2]!=bet[0][1]: return False              # less-than C meets between starting at C
        for a,b in zip(bet,bet[1:]):
            if b[1]!=a[2]+1: return False                   # betweens chain with step 1
        if grt[0][1]!=bet[-1][2]: return False              # greater-than F meets between ending at F
    except TypeError:
        return False
    return True

def pull_weather_markets():
    evs,cur=[],None; print("Pulling Kalshi weather markets...")
    for _ in range(60):
        u=f"{KBASE}/events?limit=200&status=open&with_nested_markets=true"
        if cur: u+="&cursor="+cur
        d=fget(u)
        if not d: break
        evs+=d.get("events",[]); cur=d.get("cursor")
        if not cur: break
        time.sleep(0.15)
    out=[]
    for e in evs:
        ser=e.get("series_ticker") or ""
        # Two ticker generations coexist on Kalshi: newer cities use KXHIGHT/KXLOWT,
        # the original cities still use legacy KXHIGH/KXLOW (no T), and legacy NYC
        # is "NY". Matching only KXHIGHT* silently dropped 7 of 20 HIGH ladders
        # (AUS, CHI, DEN, LAX, MIA, NYC, PHIL), including the most liquid ones.
        # Non-weather KXHIGH* series fall out at the CITIES membership check.
        if   ser.startswith("KXHIGHT"): kind,code="HIGH",ser[7:]
        elif ser.startswith("KXLOWT"):  kind,code="LOW",ser[6:]
        elif ser.startswith("KXHIGH"):  kind,code="HIGH",ser[6:]
        elif ser.startswith("KXLOW"):   kind,code="LOW",ser[5:]
        else: continue
        code=SERIES_ALIAS.get(code,code)
        if code not in CITIES: continue
        et=e.get("event_ticker",""); parts=et.split("-")
        tdate=parse_date_code(parts[1]) if len(parts)>1 else None
        if not tdate: continue
        bks=[]; raw_strikes=[]
        for m in e.get("markets",[]):
            raw_strikes.append((m.get("strike_type"),fnum(m.get("floor_strike")),fnum(m.get("cap_strike"))))
            yb,ya=fnum(m.get("yes_bid_dollars")),fnum(m.get("yes_ask_dollars"))
            if yb is None or ya is None: continue
            bks.append({"ticker":m.get("ticker"),"floor":fnum(m.get("floor_strike")),
                        "cap":fnum(m.get("cap_strike")),"stype":m.get("strike_type"),
                        "sub":m.get("yes_sub_title") or "","yb":yb,"ya":ya,
                        "oi":fnum(m.get("open_interest_fp"),0) or 0})
        if bks: out.append({"code":code,"kind":kind,"date":tdate,"event_ticker":et,"buckets":bks,
                            "structure_ok":_ladder_contiguous(raw_strikes)})
    print(f"  found {len(out)} city/day ladders")
    if len(out)<GATE_MIN_LADDERS:
        print(f"FATAL (gate): only {len(out)} ladders returned, below GATE_MIN_LADDERS={GATE_MIN_LADDERS}."
              " A truncated or empty market universe must not publish as a quiet day.")
        sys.exit(2)
    return out

def fetch_members(lat,lon,tz):
    """Pool ensemble members across models. Daily highs/lows are taken over the
    NWS Climate Report day (Local Standard Time), not the local clock day, because
    that is the window Kalshi settles on. During DST that means shifting every
    timestamp back one hour before grouping by date."""
    highs,lows,offset={},{},0
    permodel={}
    std_off=STD_OFFSET_H.get(tz,0)*3600
    for model in ENSEMBLE_MODELS:
        u=(f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}"
           f"&hourly=temperature_2m&models={model}&temperature_unit=fahrenheit"
           f"&timezone={urllib.parse.quote(tz)}&forecast_days=10")
        d=fget(u)
        if not d: continue
        offset=d.get("utc_offset_seconds",offset)
        dst_shift=dt.timedelta(seconds=(offset-std_off))  # 1h during DST, 0 in winter
        h=d.get("hourly",{}); times=h.get("time",[])
        # precompute the LST date string for each timestamp once per model
        lst_days=[]
        for t in times:
            try:
                lst_days.append((dt.datetime.fromisoformat(t)-dst_shift).date().isoformat())
            except ValueError:
                lst_days.append(t[:10])
        mh,ml={},{}
        for k in [k for k in h if k.startswith("temperature_2m")]:
            dv={}
            for day,v in zip(lst_days,h[k]):
                if v is not None: dv.setdefault(day,[]).append(v)
            for day,vs in dv.items():
                if vs:
                    hv,lv=max(vs),min(vs)
                    highs.setdefault(day,[]).append(hv); lows.setdefault(day,[]).append(lv)
                    mh.setdefault(day,[]).append(hv);   ml.setdefault(day,[]).append(lv)
        permodel[model]={"hi":mh,"lo":ml}
        time.sleep(0.2)
    return highs,lows,offset,permodel

def fetch_ai_members(lat,lon,tz):
    """AI ensemble members (AI_ENSEMBLE_MODELS), same LST windowing as
    fetch_members, returned in their OWN per-model dict. Evidence-only: the
    caller merges the summaries into members_by_model for logging and the
    skill tables; the members never join the pricing cloud or the gate counts.
    Each model is its own request so an AI outage, a renamed id, or a slow
    response can never degrade the pricing fetch."""
    permodel={}
    std_off=STD_OFFSET_H.get(tz,0)*3600
    for model in AI_ENSEMBLE_MODELS:
        u=(f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}"
           f"&hourly=temperature_2m&models={model}&temperature_unit=fahrenheit"
           f"&timezone={urllib.parse.quote(tz)}&forecast_days=10")
        d=fget(u)
        if not d: continue
        dst_shift=dt.timedelta(seconds=(d.get("utc_offset_seconds",0)-std_off))
        h=d.get("hourly",{}); times=h.get("time",[])
        lst_days=[]
        for t in times:
            try: lst_days.append((dt.datetime.fromisoformat(t)-dst_shift).date().isoformat())
            except ValueError: lst_days.append(t[:10])
        mh,ml={},{}
        for k in [k for k in h if k.startswith("temperature_2m")]:
            dv={}
            for day,v in zip(lst_days,h[k]):
                if v is not None: dv.setdefault(day,[]).append(v)
            for day,vs in dv.items():
                if vs:
                    mh.setdefault(day,[]).append(max(vs)); ml.setdefault(day,[]).append(min(vs))
        permodel[model]={"hi":mh,"lo":ml}
        time.sleep(0.2)
    return permodel

def fetch_ref(lat,lon,tz):
    """Reference point forecasts (NBM + HRRR) as CLI-day max/min per target date,
    same LST windowing as the ensemble. Logged for skill comparison only; these
    values never touch scoring, sizing, or the guards."""
    u=(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       f"&hourly=temperature_2m&models={','.join(REF_MODELS)}"
       f"&temperature_unit=fahrenheit&timezone={urllib.parse.quote(tz)}&forecast_days=3")
    d=fget(u,tries=2)
    out={}
    if not d: return out
    std_off=STD_OFFSET_H.get(tz,0)*3600
    dst_shift=dt.timedelta(seconds=(d.get("utc_offset_seconds",0)-std_off))
    h=d.get("hourly",{}); times=h.get("time",[])
    lst_days=[]
    for t in times:
        try: lst_days.append((dt.datetime.fromisoformat(t)-dst_shift).date().isoformat())
        except ValueError: lst_days.append(t[:10])
    for m in REF_MODELS:
        k="temperature_2m_"+m
        if k not in h: k="temperature_2m" if len(REF_MODELS)==1 else None
        if not k or k not in h: continue
        dv={}
        for day,v in zip(lst_days,h[k]):
            if v is not None: dv.setdefault(day,[]).append(v)
        out[m]={day:{"hi":round(max(vs),1),"lo":round(min(vs),1),"nh":len(vs)} for day,vs in dv.items()}
    return out

def fetch_run_meta():
    """Init time of the newest model run Open-Meteo is serving, per model.
    This is the audit's forecast-provenance stamp: responses carry no run id,
    so the metadata endpoint is the only honest 'which run made this' record."""
    out={}
    for name,mid in META_IDS.items():
        d=fget(f"https://api.open-meteo.com/data/{mid}/static/meta.json",tries=1)
        t=(d or {}).get("last_run_initialisation_time")
        if t:
            out[name]=dt.datetime.fromtimestamp(t,dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    return out

def _pm_summary(pm,kind,day):
    """Per-model member count/mean/sd of the RAW daily extreme for one city/kind/day.
    Food for the provider-weighting decision (audit batch 5); display-free."""
    key="hi" if kind=="HIGH" else "lo"
    out={}
    for m,d in (pm or {}).items():
        vs=(d.get(key) or {}).get(day) or []
        if vs: out[m]={"n":len(vs),"mean":round(sum(vs)/len(vs),2),"sd":round(pstdev(vs),2)}
    return out

def _ref_for(ref,kind,day):
    """NBM/HRRR value for this city/kind/day, only when hourly coverage is real."""
    out={}
    for m,days in (ref or {}).items():
        d=days.get(day)
        if d and d.get("nh",0)>=18:
            out["nbm" if "nbm" in m else "hrrr"]=d["hi"] if kind=="HIGH" else d["lo"]
    return out

def fetch_settled_event(event_ticker):
    """Return {ticker: (result, exp_value)} for settled markets of an event."""
    d=fget(f"{KBASE}/markets?event_ticker={event_ticker}&status=settled&limit=100")
    out={}
    if d:
        for m in d.get("markets",[]):
            out[m.get("ticker")]=(m.get("result"), fnum(m.get("expiration_value")))
    return out

# ----------------------- rain evidence shadow ----------------------
def fetch_rain_markets():
    """Open KXRAIN events -> {target_iso: {code: quote}}. Isolated: a failure
    returns {} and the temperature pipeline never notices. Quote fields use the
    same fixed-point names pull_weather_markets already consumes."""
    d=fget(f"{KBASE}/events?series_ticker={RAIN_SERIES}&status=open&limit=20&with_nested_markets=true",tries=2)
    out={}
    if not d: return out
    for e in d.get("events",[]):
        et=e.get("event_ticker","") or ""; parts=et.split("-")
        tdate=parse_date_code(parts[1]) if len(parts)>1 else None
        if not tdate: continue
        for m in e.get("markets",[]):
            tk=m.get("ticker","") or ""; code=tk.split("-")[-1]
            if code not in CITIES: continue        # unknown suffixes are skipped, never guessed
            yb,ya=fnum(m.get("yes_bid_dollars")),fnum(m.get("yes_ask_dollars"))
            if yb is None or ya is None: continue
            out.setdefault(tdate.isoformat(),{})[code]={
                "ticker":tk,"event_ticker":et,"yb":yb,"ya":ya,
                "mid":round((yb+ya)/2,4),
                "vol":round(fnum(m.get("volume_fp"),0) or 0,2),
                "oi":round(fnum(m.get("open_interest_fp"),0) or 0,2)}
    return out

def fetch_rain_members(lat,lon,tz):
    """Per-provider ensemble precipitation over the CLI day (same LST windowing
    as fetch_members): {model: {date: {n, wet, wet0}}} where wet is the member
    fraction with total precip >= RAIN_WET_MM (the CLI measurable threshold)
    and wet0 the fraction with any precip at all; wet1 uses the 1.0 mm variant
    threshold. Each model is its own request (the fetch_ai_members isolation
    pattern), and the AI evidence providers ride along the same way: their
    failure can never cost the core rows, and they never enter the pooled
    fractions (rain_pass pools core providers only, mirroring temperature)."""
    out={}
    std_off=STD_OFFSET_H.get(tz,0)*3600
    for model in ENSEMBLE_MODELS+AI_ENSEMBLE_MODELS:
        u=(f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}"
           f"&hourly=precipitation&models={model}"
           f"&timezone={urllib.parse.quote(tz)}&forecast_days=3")
        d=fget(u,tries=2)
        if not d: continue
        dst_shift=dt.timedelta(seconds=(d.get("utc_offset_seconds",0)-std_off))
        h=d.get("hourly",{}); times=h.get("time",[])
        lst_days=[]
        for t in times:
            try: lst_days.append((dt.datetime.fromisoformat(t)-dst_shift).date().isoformat())
            except ValueError: lst_days.append(t[:10])
        tot={}
        for k in [k for k in h if k.startswith("precipitation")]:
            dv={}
            for day,v in zip(lst_days,h[k]):
                if v is not None: dv[day]=dv.get(day,0.0)+v
            for day,s in dv.items(): tot.setdefault(day,[]).append(s)
        md={}
        for day,sums in tot.items():
            n=len(sums)
            if n: md[day]={"n":n,"wet":round(sum(1 for s in sums if s>=RAIN_WET_MM)/n,4),
                           "wet0":round(sum(1 for s in sums if s>0)/n,4),
                           "wet1":round(sum(1 for s in sums if s>=RAIN_WET1_MM)/n,4)}
        if md: out[model]=md
        time.sleep(0.2)
    return out

def rain_pass(state,run_stamp):
    """Write-once per (city, target date): per-provider wet fractions beside the
    market's quote at first sighting. No plays, no pricing, no touch on any
    temperature path. Records freeze at the FIRST board that shows the market
    (typically lead 1, since Kalshi lists tomorrow's rain event a day ahead),
    which is the same decision-time honesty the temperature book uses."""
    mkts=fetch_rain_markets()
    if not mkts: return 0
    rain=state.setdefault("rain",{"pending":{},"resolved":[]})
    pend=rain.setdefault("pending",{})
    fx={}; logged=0
    for tdate in sorted(mkts):
        for code in sorted(mkts[tdate]):
            key=f"{code}|{tdate}"
            if key in pend: continue                   # write-once
            if code not in fx:
                lat,lon,tz=CITIES[code][0],CITIES[code][1],CITIES[code][2]
                fx[code]=fetch_rain_members(lat,lon,tz)
            provs={m:fx[code][m][tdate] for m in fx[code] if tdate in fx[code][m]}
            core={m:v for m,v in provs.items() if m in ENSEMBLE_MODELS}
            if not core: continue                      # no core forecast, no record: never log prices alone
            q=mkts[tdate][code]
            nT=sum(v["n"] for v in core.values())
            # pooled fractions are CORE providers only, mirroring temperature:
            # AI providers are logged in p as evidence and race solo offline.
            pend[key]={"code":code,"target":tdate,"ticker":q["ticker"],
                       "event_ticker":q["event_ticker"],"logged_at":run_stamp,
                       "yb":q["yb"],"ya":q["ya"],"mid":q["mid"],"vol":q["vol"],"oi":q["oi"],
                       "p":provs,
                       "pool_wet":round(sum(v["wet"]*v["n"] for v in core.values())/nT,4),
                       "pool_wet0":round(sum(v["wet0"]*v["n"] for v in core.values())/nT,4),
                       "pool_wet1":round(sum(v.get("wet1",0.0)*v["n"] for v in core.values())/nT,4),
                       "rv":1}
            logged+=1
    if logged: print(f"Rain shadow: logged {logged} city-days.")
    return logged

def rain_resolve(state):
    """Grade pending rain records against Kalshi's settled results. hit=1 iff
    the market settled YES (measurable rain). Unsettled records simply wait."""
    rain=state.get("rain") or {}
    pend=rain.get("pending") or {}
    if not pend: return 0
    resv=rain.setdefault("resolved",[])
    byev={}
    for key,r in pend.items(): byev.setdefault(r["event_ticker"],[]).append(key)
    n=0
    for et,keys in byev.items():
        if dt.date.fromisoformat(pend[keys[0]]["target"])>TODAY-dt.timedelta(days=1): continue
        settled=fetch_settled_event(et); time.sleep(0.1)
        if not settled: continue
        for key in keys:
            r=pend[key]; res=settled.get(r["ticker"])
            if not res or res[0] not in ("yes","no"): continue
            resv.append(dict(r,hit=1 if res[0]=="yes" else 0))
            del pend[key]; n+=1
    if n: print(f"Rain shadow: graded {n} city-days.")
    return n

# --------------------------- calibration ---------------------------
SQRT2=math.sqrt(2.0)
def _phi(z): return 0.5*(1.0+math.erf(z/SQRT2))

def _wilson(k,n,z=1.96):
    """Wilson 95% interval for a binomial proportion: the honest error bars for
    small-n calibration bins (audit batch 9; plain +-1/sqrt(n) lies at the edges)."""
    if n<=0: return (0.0,1.0)
    p=k/n; d=1+z*z/n
    c=(p+z*z/(2*n))/d; m=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (max(0.0,c-m),min(1.0,c+m))

def _crps_gauss(y,mu,s):
    """Closed-form CRPS of N(mu, s^2) against outcome y. A Gaussian
    approximation of the full kernel mixture (exact mixture CRPS would need the
    143 members stored per record, rejected for bytes). Lower is better; it is
    a proper score, so it rewards the whole distribution, not just the mean.
    Logged per resolved event for the retune-checkpoint sigma experiments."""
    if y is None or mu is None or not s or s<=0: return None
    z=(y-mu)/s
    pdf=math.exp(-0.5*z*z)/math.sqrt(2*math.pi)
    return round(s*(z*(2.0*_phi(z)-1.0)+2.0*pdf-1.0/math.sqrt(math.pi)),3)

def _pm_values(pm,kind,day):
    """{model: [raw member values]} for one city/kind/day. Unlike _pm_summary this
    keeps the individual members, which provider weighting needs."""
    key="hi" if kind=="HIGH" else "lo"
    return {m:((d.get(key) or {}).get(day) or []) for m,d in (pm or {}).items()}

def provider_weights(state):
    """Docket 4, ADOPTED 2026-07-25 after its pre-registered gate fired (199/150
    prospective records, prospective advantage +0.022 deg, full-sample advantage
    +0.053 deg with 90% CI [+0.024, +0.083]).

    Per-KIND inverse-MSE provider weights: w_i proportional to
    1/(MSE_i + PROVIDER_W_EPS), MSE over that provider's last PROVIDER_W_LOOKBACK
    prior-date settlements of that kind. Highs and lows are learned separately
    because a provider good at daytime maxima is not automatically good at
    overnight minima.

    Returns {} for a kind until EVERY provider has PROVIDER_W_WARMUP settlements
    there, so the member-count pool remains the warmup behavior and a thin
    provider history can never dominate. The epsilon floors the weight of a
    provider on a lucky streak: without it, one near-zero MSE would take the
    entire cloud."""
    hist={"HIGH":defaultdict(list),"LOW":defaultdict(list)}
    for r in sorted(state.get("resolved",[]),key=lambda x:x.get("target","")):
        if r.get("gated") or r.get("actual") is None: continue
        if r.get("kind") not in hist: continue
        for m,v in (r.get("members_by_model") or {}).items():
            if v.get("mean") is not None: hist[r["kind"]][m].append(v["mean"]-r["actual"])
    out={}
    for kind,per in hist.items():
        if any(len(per.get(m,[]))<PROVIDER_W_WARMUP for m in ENSEMBLE_MODELS): continue
        w={}
        for m in ENSEMBLE_MODELS:
            e=per[m][-PROVIDER_W_LOOKBACK:]
            w[m]=1.0/((sum(x*x for x in e)/len(e))+PROVIDER_W_EPS)
        out[kind]=w
    return out

def weighted_cloud(pvals,wmap,corr):
    """Bias-corrected member cloud plus per-member weights implementing wmap.
    Each provider's members SHARE that provider's weight, so a 51-member model no
    longer outvotes a 21-member one on member count alone; it outvotes it only if
    its measured skill earns it. Returns (members, weights) or None when any
    provider is missing, in which case the caller keeps the pooled cloud."""
    if not wmap or not pvals: return None
    if any(not pvals.get(m) for m in ENSEMBLE_MODELS): return None
    members,wts=[],[]
    for m in ENSEMBLE_MODELS:
        vs=pvals[m]; per=wmap[m]/len(vs)
        for v in vs: members.append(v+corr); wts.append(per)
    return members,wts

def wmean_wsd(members,wts):
    """Weighted mean and weighted population sd of the member cloud."""
    tw=sum(wts)
    if not tw: return (sum(members)/len(members),pstdev(members))
    mean=sum(w*v for w,v in zip(wts,members))/tw
    var=sum(w*(v-mean)**2 for w,v in zip(wts,members))/tw
    return mean,math.sqrt(max(var,0.0))

def dressed_prob(members,b,sigma,weights=None):
    """Bucket probability from a Gaussian-kernel-dressed ensemble. Each member is
    smeared with N(member, sigma^2); the bucket prob is the average kernel mass
    inside the bucket's real-valued interval. NWS rounds half-up, so the integer
    bucket [lo,hi] covers real temperatures [lo-0.5, hi+0.5). This replaces raw
    member counting, whose 1-degree bucket probs are dominated by sampling noise."""
    lo,hi=bucket_range(b); lo_e,hi_e=lo-0.5,hi+0.5
    if weights:
        tot=tw=0.0
        for m,w in zip(members,weights):
            tot+=w*(_phi((hi_e-m)/sigma)-_phi((lo_e-m)/sigma)); tw+=w
        return tot/tw if tw else 0.0
    tot=0.0
    for m in members:
        tot+=_phi((hi_e-m)/sigma)-_phi((lo_e-m)/sigma)
    return tot/len(members)

# --------------------- nowcast SHADOW (FUTURE 5 stage 1) ---------------------
# Built at checkpoint 1 (2026-07-13). Today's high cannot settle below the max
# already observed at the settlement station, so between NOWCAST_MIN_LHR and
# INTRADAY_HIGH_CUTOFF local time we truncate every calibrated member at the
# running observed max and store a PAIRED truncated-vs-untruncated ladder
# snapshot on the pending record. PLAYS NEVER SEE THESE NUMBERS: the
# pre-registered gate (FUTURE 5) requires truncated CRPS AND RPS to beat
# untruncated over 30+ graded same-day HIGH events before any pricing change.
# Snapshots are WRITE-ONCE (first in-window snapshot wins) so later,
# better-informed observations can never cherry-pick the comparison.

def _parse_obs_max(js,start_iso):
    """Running max (deg F) from an api.weather.gov observations payload,
    counting only records timestamped at or after start_iso (UTC, lexicographic
    compare on the first 16 chars). Null and non-numeric temperatures are
    skipped defensively. Returns (max_f, n_obs) or None."""
    if not isinstance(js,dict): return None
    best=None; n=0
    for f in js.get("features") or []:
        pr=(f or {}).get("properties") or {}
        ts=pr.get("timestamp") or ""
        if ts[:16]<start_iso[:16]: continue
        v=fnum(((pr.get("temperature") or {}).get("value")))
        if v is None: continue
        fdeg=v*9.0/5.0+32.0; n+=1
        if best is None or fdeg>best: best=fdeg
    return (best,n) if n else None

def fetch_running_max(code,tz,target_iso):
    """Observed running max at the settlement station since 07:00 LST of the
    target day. NWS CLI computes the daily max from denser data than hourly
    METARs, so this is a LOWER BOUND on the settlement value: exactly what
    truncation needs, never more than the truth. Returns (max_f,n_obs) or None."""
    sid=STATION_IDS.get(code)
    if not sid: return None
    start=dt.datetime.fromisoformat(target_iso)+dt.timedelta(hours=7-STD_OFFSET_H.get(tz,0))
    js=fget(f"https://api.weather.gov/stations/{sid}/observations"
            f"?start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=200")
    if not js: return None
    return _parse_obs_max(js,start.strftime("%Y-%m-%dT%H:%M"))

def _grade_nowcast(nc,settled,actual):
    """Grade a paired shadow snapshot against Kalshi's own per-bucket settlement,
    mirroring compute_report's RPS conventions exactly (rep-sorted, normalized,
    last cumulative step dropped, exactly one hit required) so the two ladders
    and the headline metric all speak the same units. CRPS uses each snapshot's
    own mean/psd. Returns the compact graded dict or None."""
    bs=[b for b in nc.get("buckets",[]) if b.get("rep") is not None]
    if len(bs)<3: return None
    bs=sorted(bs,key=lambda b:b["rep"])
    hits=[]
    for b in bs:
        res=settled.get(b["ticker"])
        if not res or res[0] not in ("yes","no"): return None
        hits.append(1 if res[0]=="yes" else 0)
    if sum(hits)!=1: return None
    def _rps(key):
        s=sum(b[key] for b in bs) or 1.0
        F=O=0.0; tot=0.0
        for b,h in zip(bs[:-1],hits[:-1]):
            F+=b[key]/s; O+=h; tot+=(F-O)**2
        return tot
    out={"asof":nc.get("asof"),"obs_max":nc.get("obs_max"),"n_obs":nc.get("n_obs"),
         "mean_u":nc.get("mean_u"),"mean_t":nc.get("mean_t"),
         "rps_u":round(_rps("mp_u"),4),"rps_t":round(_rps("mp_t"),4)}
    if actual is not None:
        out["crps_u"]=_crps_gauss(actual,nc.get("mean_u"),nc.get("psd_u"))
        out["crps_t"]=_crps_gauss(actual,nc.get("mean_t"),nc.get("psd_t"))
    return out

def shadow_pass(state):
    """Collect nowcast shadow snapshots onto eligible pending records: same-day
    HIGH markets whose city clock sits inside [NOWCAST_MIN_LHR,
    INTRADAY_HIGH_CUTOFF) and which do not already carry one. Touches ONLY the
    'nowcast' key on pending records; boards, plays, resolution, and every
    existing measurement are untouched by design."""
    preds=state.get("predictions",{})
    if not preds: return 0
    calib=calib_params(state); gsigma=calib.get("_gsigma",DRESS_SIGMA_DEFAULT)
    ladders=None; members_cache={}; pm_cache={}
    # v15: the shadow must price its paired snapshot the SAME way production
    # does, or the ongoing tally measures a model that is no longer running.
    pw=provider_weights(state)
    wrote=0
    for key,p in preds.items():
        if p.get("kind")!="HIGH" or p.get("gated") or p.get("nowcast"): continue
        code=p.get("code"); tgt=p.get("target")
        if code not in CITIES: continue
        lat,lon,tz,label=CITIES[code]
        off=STD_OFFSET_H.get(tz,0)*3600
        lnow=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)+dt.timedelta(seconds=off)
        if tgt!=lnow.date().isoformat(): continue
        if not (NOWCAST_MIN_LHR<=lnow.hour<INTRADAY_HIGH_CUTOFF): continue
        if ladders is None:
            ladders={(l["code"],l["kind"],l["date"].isoformat()):l for l in pull_weather_markets()}
        L=ladders.get((code,"HIGH",tgt))
        if not L or not L.get("structure_ok",True): continue
        if code not in members_cache:
            hi,_lo,_o,_pm=fetch_members(lat,lon,tz); members_cache[code]=hi or {}; pm_cache[code]=_pm
        raw=members_cache[code].get(tgt,[])
        if len(raw)<GATE_MIN_MEMBERS: continue
        obs=fetch_running_max(code,tz,tgt)
        if not obs: continue
        runmax,n_obs=obs
        cp=calib.get((code,"HIGH")) or {}
        corr=cp.get("corr",0.0); sigma=cp.get("sigma") or gsigma
        # Same skill-weighted cloud production uses (docket 4), then the same
        # truncation production applies (FUTURE 5). Before v15 this snapshot was
        # built from the POOLED cloud, which was harmless while the shadow only
        # had to gate itself (its comparison is internal), but is wrong now that
        # truncation is live: a monitor has to watch the model that is actually
        # running. Falls back to the pooled cloud on warmup or a missing
        # provider, exactly as production does.
        wc=weighted_cloud(_pm_values(pm_cache.get(code),"HIGH",tgt),pw.get("HIGH"),corr)
        if wc: mem_u,wts=wc
        else:  mem_u,wts=[v+corr for v in raw],None
        mem_t=[max(v,runmax) for v in mem_u]
        def _mps(ms):
            if wts: mu,msd=wmean_wsd(ms,wts)
            else:   mu=sum(ms)/len(ms); msd=pstdev(ms)
            return mu,math.sqrt(msd*msd+sigma*sigma)
        mu_u,psd_u=_mps(mem_u); mu_t,psd_t=_mps(mem_t)
        p["nowcast"]={"asof":dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                      "obs_max":round(runmax,1),"n_obs":n_obs,
                      "mean_u":round(mu_u,2),"psd_u":round(psd_u,3),
                      "mean_t":round(mu_t,2),"psd_t":round(psd_t,3),
                      "model_version":MODEL_VERSION,"cfg":CONFIG_HASH,
                      "buckets":[{"ticker":b["ticker"],"rep":bucket_rep(b),
                                  "mp_u":dressed_prob(mem_u,b,sigma,wts),
                                  "mp_t":dressed_prob(mem_t,b,sigma,wts)} for b in L["buckets"]]}
        wrote+=1
    if wrote: print(f"   nowcast shadow: {wrote} snapshot(s) collected")
    return wrote

def calib_params(state):
    """Learn per (city,kind) mean-bias correction and dressing sigma from settled
    results. Uses the RAW forecast bias (logged bias plus whatever correction was
    applied at log time) so the learning target is stable as corrections evolve.
    Correction is shrunk toward 0 when history is thin; sigma comes from
    second-moment matching (Wang-Bishop): predictive variance should equal the
    realized MSE of the bias-corrected mean, so kernel variance fills the gap
    between that and the raw member variance."""
    hist=defaultdict(list)
    for r in state.get("resolved",[]):
        if r.get("bias") is None or r.get("gated"): continue   # quarantined: degraded data never teaches the corrections
        # RAW forecast bias = logged (corrected) bias MINUS the correction that was
        # added to the members at log time: corrected_mean = raw_mean + corr, so
        # raw = (corrected_mean - actual) - corr. The pre-audit code ADDED corr,
        # which is a stable but WRONG feedback loop: it converges to only
        # s/(1+2s) of the needed correction (about a third at full shrink), so a
        # city with a 3 degree station offset would keep a ~2 degree error and
        # trip the bias guard forever. Verified by simulation, audit batch 3.
        # It never fired live because no city had reached BIAS_MIN_N settlements.
        raw=r["bias"]-(r.get("bias_corr") or 0.0)
        hist[(r["code"],r["kind"])].append({"raw":raw,"sd":r.get("sd"),"t":r.get("target","")})
    out={}
    pooled=[]
    for k,rows in hist.items():
        # window by TARGET DATE, not append order: multi-day settlement batches
        # can resolve out of order, and "most recent 30" must mean the calendar.
        rows=sorted(rows,key=lambda x:x.get("t",""))[-BIAS_LOOKBACK:]
        rb=[x["raw"] for x in rows]; n=len(rb)
        corr=-(sum(rb)/n)*(n/(n+BIAS_SHRINK_K)) if n>=BIAS_MIN_N else 0.0
        srows=[x for x in rows if x.get("sd") is not None]
        pooled+=srows
        sig=None
        if len(srows)>=8:
            sb=[x["raw"] for x in srows]; m=sum(sb)/len(sb)
            var_err=sum((x-m)**2 for x in sb)/len(sb)
            mean_s2=sum(x["sd"]**2 for x in srows)/len(srows)
            sig=math.sqrt(max(var_err-mean_s2,0.0))
        out[k]={"corr":round(corr,2),"sigma":sig,"n":n}
    gsig=None
    if len(pooled)>=15:
        gb=[x["raw"] for x in pooled]; m=sum(gb)/len(gb)
        var_err=sum((x-m)**2 for x in gb)/len(gb)
        mean_s2=sum(x["sd"]**2 for x in pooled)/len(pooled)
        gsig=math.sqrt(max(var_err-mean_s2,0.0))
    for k,v in out.items():
        s=v["sigma"] if v["sigma"] is not None else (gsig if gsig is not None else DRESS_SIGMA_DEFAULT)
        v["sigma"]=round(min(max(s,DRESS_SIGMA_MIN),DRESS_SIGMA_MAX),2)
    out["_gsigma"]=round(min(max(gsig,DRESS_SIGMA_MIN),DRESS_SIGMA_MAX),2) if gsig is not None else DRESS_SIGMA_DEFAULT
    return out

# ------------------------------ tiers ------------------------------
def city_skill(state):
    agg=defaultdict(lambda:{"bm":0.0,"bk":0.0,"nb":0})
    for r in state.get("resolved",[]):
        a=agg[(r["code"],r["kind"])]
        for b in r["buckets"]:
            a["bm"]+=(b["mp"]-b["hit"])**2; a["bk"]+=(b["mid"]-b["hit"])**2; a["nb"]+=1
    return {k:{"nb":a["nb"],"brier_edge":(a["bk"]-a["bm"])/a["nb"]} for k,a in agg.items() if a["nb"]>=20}

def size_play(net, p_win, proven, lead=0):
    """Size from edge magnitude, then cap by win-probability, plausibility, lead time, and city track record."""
    if net < PLAY_NET_EDGE: return 0.0, ""
    # plausibility: an outsized edge is a red flag, not a green light
    if net >= SUSPECT_EDGE:
        return 1.0, "edge %.0f%% is implausibly large (likely model error or thin market), sized down" % (net*100)
    base = 2.0 if net>=EDGE_2U else 1.5 if net>=EDGE_1_5U else 1.0
    # win-probability ceiling: a bet you rarely WIN is high-variance regardless of edge
    wpc=WINPROB_CAP[-1][1]
    for thr,u in WINPROB_CAP:
        if p_win>=thr: wpc=u; break
    units=min(base,wpc); reason=""
    if wpc<base: reason="win prob %.0f%%, trimmed"%(p_win*100)
    # forecast skill decays fast with lead; a 3-4 day edge is mostly model noise
    if lead>=LEAD_CAP_DAYS and units>1.0:
        units=1.0; reason=reason or ("%d days out, capped"%lead)
    # a city must prove itself before it can earn max size
    if units>=2.0 and not proven:
        units=1.5; reason=reason or "city not yet proven, 2u locked"
    return units, reason

# ----------------------------- scoring -----------------------------
# Fields of the write-once decision-board snapshot (book0). Enough to REPRICE a
# ladder (mp, mid, yb, ya, oi) and to re-derive bucket probabilities under a
# different forecast config (floor, cap, stype); ticker is the join key to the
# settlement. Deliberately NOT in _KNOB_NAMES: this is a recording schema, not a
# behavior knob, so CONFIG_HASH is unaffected.
# Since 2026-07-28 the snapshot also freezes `sd`, the member sd of the DECISION
# board. The record-level `sd` refreshes with the forecast every run, so by
# settlement it describes the final board; the docket 6 spread-convergence
# candidates filter on what was knowable when the decision was made, which only
# this frozen copy preserves. Snapshots written before that date have no `sd`
# and the replay tool falls back to the record's final-board sd, saying so.
BOOK0_FIELDS=("ticker","mp","mid","yb","ya","oi","floor","cap","stype")

# Board tape (FUTURE docket 7, bet-timing replay). book0 preserves the FIRST
# board and rec["buckets"] holds the LAST, so the boards in between were being
# discarded: "would freezing at a later board have been better" had no stored
# answer, and the natural entry-board split (67 plays on the 12:17 board vs 15
# on 21:38) is far too lopsided to settle it observationally. The tape records
# every healthy board as a compact positional row so a replay can re-run
# selection at board k instead of board 0.
#
# Encoding, measured against alternatives before choosing: [at, mean, biased,
# lead, fp, [[mp, mid, yb, ya, oi], ...]] costs ~234 B/board, about 20 percent
# of a full book0 snapshot, and adds roughly 1.1-1.7 MB/month. Keying every
# bucket by id instead was 342 B/board; the fingerprint buys the same safety
# for a third of the bytes.
#
# `fp` is a hash of the board's ticker tuple. Bucket values are POSITIONAL, so
# a replay must confirm a board's fp matches book0's before indexing into it;
# Kalshi can add a strike mid-life (never observed in 81 paired boards, but
# never observed is not never). A board whose fp differs is skipped by the
# replay rather than silently misaligned.
#
# Only records that also carry book0 are taped, so tape[0] IS the decision
# board by construction. A record already in flight has boards nobody captured,
# which would make "board k" mean nothing. Gated boards are never taped, same
# rule as book0: degraded data must not enter a replay.
# Deliberately NOT in _KNOB_NAMES: recording schema, not a behavior knob, so
# CONFIG_HASH is unaffected.
TAPE_MAX_BOARDS=8   # records have never seen more than 5; this is a runaway guard

def _tape_row(run_stamp, mean, biased, lead, pbk):
    fp=hashlib.sha1("|".join(b["ticker"] for b in pbk).encode()).hexdigest()[:8]
    return [run_stamp, round(mean,2), 1 if biased else 0, lead, fp,
            [[round(b["mp"],4), b["mid"], b["yb"], b["ya"], round(b["oi"],1)] for b in pbk]]

def score(state):
    ladders=pull_weather_markets()
    needed=sorted({l["code"] for l in ladders})
    print(f"Forecasts for {len(needed)} cities ({'+'.join(ENSEMBLE_MODELS)})...")
    fc,offs,pms,refs,ai_pms={},{},{},{},{}
    fetch_failed=[]; gated=[]
    for code in needed:
        lat,lon,tz,label=CITIES[code]
        hi,lo,off,pm=fetch_members(lat,lon,tz); fc[code]={"HIGH":hi,"LOW":lo}; offs[code]=off; pms[code]=pm
        refs[code]=fetch_ref(lat,lon,tz)
        ai_pms[code]=fetch_ai_members(lat,lon,tz)   # evidence-only, never priced
        if not hi and not lo: fetch_failed.append(code)
    run_meta=fetch_run_meta()
    run_stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    frozen_now=set()   # keys whose plays froze during THIS invocation (cap pruning
                       # must never touch plays frozen by an earlier run; a timestamp
                       # comparison fails when two runs share a minute, unit-test proven)
    rows,plays=[],[]
    skill=city_skill(state); preds=state.setdefault("predictions",{})
    calib=calib_params(state); gsigma=calib.get("_gsigma",DRESS_SIGMA_DEFAULT)
    pw=provider_weights(state)   # docket 4 (v14); {} per kind until every provider clears warmup
    for L in ladders:
        code,kind,tdate=L["code"],L["kind"],L["date"]
        # Lead and local hour come from the CITY's clock, never the runner's.
        # GitHub runners are UTC: after 00:00 UTC the runner's date is tomorrow
        # in every US zone, so runner-date leads mislabel each market by a day
        # and the realized guard wrongly kills next-day logging on evening runs.
        off=offs.get(code) or STD_OFFSET_H.get(CITIES[code][2],0)*3600
        lnow=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)+dt.timedelta(seconds=off)
        lead=(tdate-lnow.date()).days
        if lead<0: continue
        lhr=lnow.hour
        realized=(lead==0 and kind=="LOW") or (lead==0 and kind=="HIGH" and lhr>=INTRADAY_HIGH_CUTOFF)
        # the pending record is needed BEFORE pricing now: it carries the nowcast
        # snapshot whose observed max floors the member cloud.
        key=f"{code}|{kind}|{tdate.isoformat()}"
        old=preds.get(key)
        raw_members=fc[code][kind].get(tdate.isoformat(),[])
        # ---- integrity GATE (0.8, approved; quarantine amendment, batch 8) ----
        # A gated ladder still LOGS its record, flagged "gated", so the exclusion
        # is auditable later (owner-directed: never destroy the evidence needed
        # to judge whether an exclusion rule was right). Gated records carry no
        # plays, are skipped by calibration learning, drift alarms, and every
        # report aggregate, and never overwrite a healthy record's frozen plays.
        pmsum=_pm_summary(pms.get(code),kind,tdate.isoformat())
        gate=None
        if not L.get("structure_ok",True): gate="ladder structure"
        elif len(raw_members)<GATE_MIN_MEMBERS: gate=f"{len(raw_members)} members"
        elif len(pmsum)<GATE_MIN_MODELS: gate=f"{len(pmsum)}/4 models"
        if gate:
            gated.append(f"{code}/{kind} {tdate.isoformat()[5:]}: {gate}")
            if len(raw_members)<2: continue   # nothing meaningful to quarantine
        # learned calibration for this city/kind: shift by bias correction, dress with sigma
        cp=calib.get((code,kind)) or {}
        corr=cp.get("corr",0.0); sigma=cp.get("sigma") or gsigma
        # provider weighting (docket 4, v14): weight the cloud by measured per-kind
        # skill when every provider has cleared warmup, else keep the member-count
        # pool exactly as before.
        wc=weighted_cloud(_pm_values(pms.get(code),kind,tdate.isoformat()),pw.get(kind),corr)
        if wc: members,mwts=wc
        else:  members,mwts=[v+corr for v in raw_members],None
        # NOWCAST TRUNCATION (FUTURE 5, PROMOTED to live pricing at v15 on its
        # re-registered gate: 55 binding events vs a gate of 25, truncated wins
        # mean CRPS 1.277 vs 1.578 and the per-event RPS majority 38 to 4).
        # Today's high cannot settle below what the settlement station has
        # ALREADY recorded, so every member is floored at the running observed
        # max. The observation is a lower bound on the CLI daily max by
        # construction (NWS computes it from denser data than hourly METARs), so
        # this can never claim more than the truth. It also moves the forecast
        # toward the outcome rather than away: measured over 200 graded events
        # the signed bias improves from -0.324 to -0.087 deg and MAE from 1.753
        # to 1.637, so the bias learner sees a BETTER forecast and does not
        # fight the truncation.
        # The floor comes from the snapshot shadow_pass wrote earlier THIS run,
        # not a fresh fetch: it is the exact quantity the gate graded, and it
        # costs no extra API calls.
        nowcast_floor=None
        if kind=="HIGH" and lead==0 and old and old.get("nowcast"):
            _rm=old["nowcast"].get("obs_max")
            if _rm is not None:
                members=[max(v,_rm) for v in members]; nowcast_floor=_rm
        n=len(members)
        if mwts: mean,msd=wmean_wsd(members,mwts)
        else:    msd=pstdev(members); mean=sum(members)/n
        sd=math.sqrt(msd*msd+sigma*sigma)   # predictive spread incl. dressing
        ov=sum(b["ya"] for b in L["buckets"])-1.0
        wsum=sum((b["yb"]+b["ya"])/2 for b in L["buckets"])
        mkt_mean=(sum(((b["yb"]+b["ya"])/2)*(bucket_rep(b) or 0) for b in L["buckets"])/wsum) if wsum else mean
        offset=mean-mkt_mean; biased=abs(offset)>BIAS_TOL
        pbk,ppl=[],[]
        for b in L["buckets"]:
            mp=dressed_prob(members,b,sigma,mwts); mid=(b["yb"]+b["ya"])/2
            # decisions use the clamped prob; displays and logs keep raw mp
            mp_e=min(max(mp,TAIL_FLOOR),1.0-TAIL_FLOOR)
            cost=(b["ya"]-b["yb"])/2+fee(mid)+0.01; edge=mp_e-mid
            if edge>0: side,entry,net="Buy YES",b["ya"],edge-cost
            else:      side,entry,net="Buy NO",round(1-b["yb"],2),(-edge)-cost
            base=((not gate) and (not biased) and (not realized) and net>=PLAY_NET_EDGE and b["oi"]>=MIN_OI
                  and lead<=MAX_LEAD_DAYS and 0.02<mid<0.98 and entry>=MIN_ENTRY)
            tier=None; eff=net; units=0.0; p_win=None; size_reason=""; hiconf=False
            if base:
                p_win = mp_e if side=="Buy YES" else 1-mp_e
                proven = (code,kind) in skill
                units, size_reason = size_play(net, p_win, proven, lead)
                tier = "S" if units>=2 else "A" if units>=1.5 else "B" if units>=1 else None
                hiconf = units>0 and p_win>=HICONF_PWIN
            is_play=base and units>0
            rec={"code":code,"label":CITIES[code][3],"kind":kind,"date":tdate,"lead":lead,
                 "bucket":b["sub"],"ticker":b["ticker"],"mid":mid,"mp":mp,"edge":edge,"side":side,
                 "entry":entry,"net":net,"oi":b["oi"],"sd":sd,"mean":mean,"overround":ov,
                 "offset":offset,"biased":biased,"realized":realized,"tier":tier,"eff":eff,"p_win":p_win,
                 "size_reason":size_reason,"hiconf":hiconf,
                 "units":units,"stake":round(units*BASE_UNIT_USD,2) if units else None}
            if not gate: rows.append(rec)
            if is_play: plays.append(rec)
            pbk.append({"ticker":b["ticker"],"bid":bucket_id(b),"sub":b["sub"],"floor":b["floor"],
                        "cap":b["cap"],"stype":b["stype"],"mp":mp,"mid":mid,"yb":b["yb"],"ya":b["ya"],"oi":b["oi"]})
            if is_play:
                ppl.append({"ticker":b["ticker"],"bid":bucket_id(b),"sub":b["sub"],"side":side,
                            "entry":entry,"net":net,"edge":edge,"tier":tier,"units":units,
                            "stake":round(units*BASE_UNIT_USD,2),"p_win":p_win,"mp":mp,"mid":mid})
        if not realized:
            if gate and old and old.get("plays"):
                pass   # degraded data must never overwrite a record holding frozen plays
            else:
                rec={"code":code,"kind":kind,"target":tdate.isoformat(),
                    "event_ticker":L["event_ticker"],"logged_at":run_stamp,
                    "first_logged":(old or {}).get("first_logged") or (old or {}).get("logged_at") or run_stamp,
                    "lead":lead,"mean":mean,"sd":msd,"psd":sd,"bias_corr":corr,"sigma":sigma,
                    "model_version":MODEL_VERSION,"biased":biased,"offset":offset,
                    "model_runs":run_meta,
                    # core providers first, AI evidence models beside them. The
                    # gate's model count above reads pms only, so these can
                    # never rescue a thin ladder, and every pricing path
                    # iterates ENSEMBLE_MODELS, so they are never priced.
                    "members_by_model":{**_pm_summary(pms.get(code),kind,tdate.isoformat()),
                                        **_pm_summary(ai_pms.get(code),kind,tdate.isoformat())},
                    "ref":_ref_for(refs.get(code),kind,tdate.isoformat()),
                    "cfg":CONFIG_HASH,
                    "mean_hist":(((old or {}).get("mean_hist") or [])+[[run_stamp,round(mean,2)]])[-6:],
                    "buckets":pbk,"plays":ppl}
                if nowcast_floor is not None: rec["nowcast_floor"]=nowcast_floor
                if gate: rec["gated"]=gate
                if old and old.get("nowcast"): rec["nowcast"]=old["nowcast"]   # shadow snapshots survive refreshes (write-once)
                # BOOK0 (write-once): the order book of the FIRST healthy board for
                # this market, i.e. the board a decision would actually have been made
                # on. rec["buckets"] refreshes every run because calibration and CLV
                # want the freshest prices, so by settlement the stored book is the
                # FINAL board's: 75 percent of resolved records saw 2 or more boards,
                # which makes the refreshed book useless for reconstructing a decision.
                # Carried onto the resolved record and stamped with each bucket's
                # settled outcome, book0 lets any play-selection, sizing, or pricing
                # config be replayed offline against real history, including configs
                # invented long after the fact. Gated boards never write it: degraded
                # data must not become the decision snapshot.
                if old and old.get("book0"):
                    rec["book0"]=old["book0"]
                elif old is None and not gate:
                    # ONLY on a market's genuinely first log. A record already in
                    # flight when this shipped has boards we never captured, and its
                    # plays may have frozen on one of them, so snapshotting it now
                    # would label a mid-life board as the decision board and quietly
                    # corrupt every replay built on it. Those records are excluded
                    # forever instead, which costs about two days of coverage. Same
                    # reason a first-board gate forfeits the snapshot: better absent
                    # than wrong.
                    # Record-level scalars travel WITH the snapshot: `biased` is a
                    # play-gate input that resolved records never stored at all, and
                    # `lead` on the record is the LAST refresh's, not the decision
                    # board's. A replay missing either would apply the wrong filters.
                    rec["book0"]={"at":run_stamp,"mean":mean,"biased":biased,"lead":lead,
                                  "sd":msd,
                                  "buckets":[{k:b[k] for k in BOOK0_FIELDS} for b in pbk]}
                    # SOURCE_MP (registered 2026-07-29, FUTURE docket 8): each
                    # core provider's own dressed bucket probabilities under the
                    # SHARED city/kind calibration (same corr, same sigma, no
                    # cross-provider weighting), positional against book0's
                    # buckets. This is the minimum logging an honest source-
                    # consensus test needs: provider summaries (mean/sd) cannot
                    # reconstruct bucket probabilities, proven in the July
                    # audit. Write-once with book0; pure recording, read by
                    # nothing in the pricing path; AI providers excluded like
                    # everywhere else; a provider under 5 members logs nothing.
                    # The nowcast floor is deliberately NOT applied here (it is
                    # a pooled-cloud operation; the point is each provider's
                    # independent opinion), noted in 7b.
                    _kk="hi" if kind=="HIGH" else "lo"
                    _smp={}
                    for _m in ENSEMBLE_MODELS:
                        _vals=(((pms.get(code) or {}).get(_m) or {}).get(_kk) or {}).get(tdate.isoformat())
                        if _vals and len(_vals)>=5:
                            _sh=[v+corr for v in _vals]
                            _smp[_m]=[round(dressed_prob(_sh,b,sigma),4) for b in L["buckets"]]
                    if _smp:
                        rec["book0"]["source_mp"]=_smp; rec["book0"]["smp_v"]=1
                # BOARD TAPE (append-once per run stamp): every healthy board this
                # market is seen on, so a replay can ask what freezing at board k
                # would have done. Gated boards are skipped.
                # A record must be taped from its FIRST board or not at all. Holding
                # book0 is not sufficient: the 46 records already in flight when the
                # tape shipped have a book0 from an earlier run, so starting their
                # tape now would make tape[0] a mid-life board while every reader
                # takes it for the decision board. That is the same trap book0 itself
                # guards against, and it silently corrupts the replay rather than
                # failing loudly. Those records are excluded forever instead, costing
                # about two days of coverage. Better absent than wrong.
                prior=(old or {}).get("tape")
                if not gate and rec.get("book0") and (prior is not None or old is None):
                    tape=list(prior or [])
                    if len(tape)<TAPE_MAX_BOARDS and not any(t[0]==run_stamp for t in tape):
                        tape.append(_tape_row(run_stamp,mean,biased,lead,pbk))
                    if tape: rec["tape"]=tape
                # FREEZE: once a run has published plays for this market, later runs must
                # not rewrite them; the tracker has to score the board the owner actually
                # saw. Buckets/mean/sigma keep refreshing (calibration wants the freshest
                # forecast); the plays list locks at its first NON-EMPTY log, so an edge
                # that only appears later can still be picked up once, then locks too.
                if old and old.get("plays"):
                    rec["plays"]=old["plays"]
                    rec["plays_lead"]=old.get("plays_lead",old.get("lead"))
                    rec["plays_logged_at"]=old.get("plays_logged_at",old.get("logged_at"))
                    rec["plays_model_version"]=old.get("plays_model_version",old.get("model_version",""))
                elif ppl:
                    rec["plays_lead"]=lead; rec["plays_logged_at"]=run_stamp
                    rec["plays_model_version"]=MODEL_VERSION
                    frozen_now.add(key)
                preds[key]=rec
    plays.sort(key=lambda r:(-r["units"],-(r.get("p_win") or 0),-r.get("net",0),r["ticker"]))
    # ---- exposure caps (audit batch 8; SEEDED v12): best plays fill first ----
    # The caps bound CUMULATIVE frozen exposure per target, so the ledger of
    # already-frozen plays (earlier runs today, or inherited pre-audit records:
    # deploy day proved a 37.5u legacy board can be inherited in one race)
    # consumes the budget BEFORE any new play may freeze. Without the seed,
    # every additional run on a volatile day could rotate a fresh 6u into the
    # frozen set as old edges fade and new ones appear.
    kept=[]; dropped=0
    per_day=defaultdict(float); per_ev=defaultdict(float)
    for key,rec in preds.items():
        if key in frozen_now or not rec.get("plays"): continue
        for pl in rec["plays"]:
            per_day[rec["target"]]+=pl["units"]
            per_ev[(rec["target"],rec["code"],rec["kind"])]+=pl["units"]
    for r in plays:
        dk=r["date"].isoformat(); ek=(dk,r["code"],r["kind"])
        if per_day[dk]+r["units"]>DAILY_UNIT_CAP+1e-9 or per_ev[ek]+r["units"]>EVENT_UNIT_CAP+1e-9:
            # Over the daily/event exposure budget: drop from the actionable board
            # AND neutralize the shared row object so the By-city detail view cannot
            # still advertise it as a live sized bet (rows and plays hold the SAME
            # dict). Persistence is capped separately in the prune loop below.
            dropped+=1; r["capped"]=True; r["units"]=0.0; r["stake"]=None; continue
        per_day[dk]+=r["units"]; per_ev[ek]+=r["units"]; kept.append(r)
    plays=kept
    # prune ONLY plays frozen THIS run; earlier frozen history is untouchable
    kept_ids={(r["date"].isoformat(),r["ticker"],r["side"]) for r in plays}
    for key,rec in preds.items():
        if key in frozen_now and rec.get("plays"):
            pruned=[pl for pl in rec["plays"] if (rec["target"],pl["ticker"],pl["side"]) in kept_ids]
            if len(pruned)!=len(rec["plays"]):
                rec["plays"]=pruned
                if not pruned:
                    for f in ("plays_lead","plays_logged_at","plays_model_version"): rec.pop(f,None)
    new24=0
    now_utc=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for rec in preds.values():
        ts=rec.get("plays_logged_at")
        if ts and rec.get("plays"):
            try:
                try: tsd=dt.datetime.strptime(ts,"%Y-%m-%dT%H:%MZ")
                except ValueError: tsd=dt.datetime.strptime(ts,"%Y-%m-%dT%H:%M")  # inherited pre-audit stamps lack the Z
                if (now_utc-tsd).total_seconds()<=86400:
                    new24+=len(rec["plays"])
            except ValueError: pass
    health={"ladders":len(ladders),"cities":len(needed),"cities_failed":fetch_failed,
            "gated":gated,"capped":dropped,"new_24h":new24,
            "run_utc":dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
    return rows,plays,health

# --------------------------- resolution ----------------------------
def resolve_pending(state):
    preds=state.get("predictions",{}); resolved=state.setdefault("resolved",[])
    due={k:p for k,p in preds.items() if dt.date.fromisoformat(p["target"])<=TODAY-dt.timedelta(days=1)}
    n=0
    for k,p in list(due.items()):
        settled=fetch_settled_event(p["event_ticker"]); time.sleep(0.1)
        if not settled: continue                      # not settled yet; retry next run
        exps=[v for _,v in settled.values() if v is not None]
        actual=exps[0] if exps else None
        rec={"code":p["code"],"kind":p["kind"],"target":p["target"],"lead":p["lead"],
             "actual":round_nws(actual) if actual is not None else None,
             "mean":p["mean"],"bias":(p["mean"]-actual) if actual is not None else None,
             "sd":p.get("sd"),"psd":p.get("psd"),"bias_corr":p.get("bias_corr",0.0),"sigma":p.get("sigma"),
             "crps":_crps_gauss(actual,p["mean"],p.get("psd")),
             "model_version":p.get("model_version",""),"cfg":p.get("cfg"),
             "first_logged":p.get("first_logged",p.get("logged_at")),
             "model_runs":p.get("model_runs"),
             "members_by_model":p.get("members_by_model"),
             "ref":p.get("ref"),
             "buckets":[],"plays":[]}
        if p.get("mean_hist"): rec["mean_hist"]=p["mean_hist"]   # run-by-run forecast revision trail (audit batch 11)
        if p.get("gated"): rec["gated"]=p["gated"]   # quarantined record: kept for audit, excluded from learning and metrics
        ok=True
        for b in p["buckets"]:
            res=settled.get(b["ticker"])
            if not res or res[0] not in ("yes","no"): ok=False; continue
            hit=1 if res[0]=="yes" else 0
            rec["buckets"].append({"mp":b["mp"],"mid":b["mid"],"hit":hit,"rep":bucket_rep(b)})
        if p.get("nowcast"):
            g=_grade_nowcast(p["nowcast"],settled,actual)
            if g: rec["nowcast"]=g   # nowcast shadow, graded (FUTURE 5 gate instrument)
        # book0 -> resolved record, each entry stamped with its settled outcome so
        # the snapshot is self-contained: reprice AND grade with no join back to
        # buckets[]. All or nothing: a partially graded book would silently bias a
        # replay's exposure caps, which allocate across a whole ladder.
        b0=p.get("book0")
        if b0 and b0.get("buckets"):
            graded=[]
            for e in b0["buckets"]:
                sr=settled.get(e["ticker"])
                if not sr or sr[0] not in ("yes","no"): graded=None; break
                graded.append(dict(e,hit=1 if sr[0]=="yes" else 0))
            if graded: rec["book0"]=dict(b0,buckets=graded)
        # The tape rides along only when book0 graded: the two are read together
        # (book0 supplies the ladder geometry the tape's positional rows index
        # into, plus the settled hits), so a tape without a graded book0 is not
        # replayable and would only cost bytes.
        if rec.get("book0") and p.get("tape"): rec["tape"]=p["tape"]
        # Entry board of the frozen plays. Dropping this was the reason the
        # bet-timing question could only be answered through a first_logged
        # proxy: plays freeze at the first PLAYABLE board, which is not always
        # the record's first board, so the proxy is an assumption, not a fact.
        if p.get("plays") and p.get("plays_logged_at"):
            rec["plays_logged_at"]=p["plays_logged_at"]
        for pl in p.get("plays",[]):
            res=settled.get(pl["ticker"])
            if not res or res[0] not in ("yes","no"): continue
            won=(res[0]=="yes") if pl["side"]=="Buy YES" else (res[0]=="no")
            entry=pl["entry"]; contracts=int(pl["stake"]//entry) if entry>0 else 0
            # Kalshi charges the quadratic taker fee per TRADE, rounded UP to the
            # next cent. Ceil can only overstate paper costs: conservative.
            fees=math.ceil(0.07*contracts*entry*(1-entry)*100)/100 if contracts else 0.0
            pnl=contracts*((1-entry) if won else -entry)-fees
            bb=next((b for b in p["buckets"] if b["ticker"]==pl["ticker"]),None)
            # CLV analog (audit batch 5): entry-time mid (frozen with the play) vs
            # the mid at this record's LAST refresh, i.e. the final actionable
            # board (HIGHs: the morning-of 12:17 board; LOWs: the prior-evening
            # 02:07 board). Positive = the market moved toward the position.
            # Mirrors RidgeSeeker's beat-the-close philosophy: edge shows here
            # long before win/loss variance can.
            cmid=bb.get("mid") if bb else None
            clv=None
            if cmid is not None and pl.get("mid") is not None:
                clv=round((cmid-pl["mid"]) if pl["side"]=="Buy YES" else (pl["mid"]-cmid),3)
            mv=margin_deg(actual,bb,won) if (bb and actual is not None) else None
            rec["plays"].append({"code":p["code"],"kind":p["kind"],"target":p["target"],"sub":pl["sub"],
                                 "side":pl["side"],"entry":entry,"tier":pl["tier"],"units":pl["units"],
                                 "stake":pl["stake"],"contracts":contracts,"won":won,"pnl":round(pnl,2),
                                 "margin":mv,"actual":rec["actual"],"mp":pl["mp"],"mid":pl["mid"],
                                 "edge":pl.get("edge"),"lead":p.get("plays_lead",p.get("lead")),
                                 "p_win":pl.get("p_win"),
                                 # net (the post-cost edge the play was SIZED on) plus the bucket
                                 # identity were dropped here from v7 until 2026-07-28, the same
                                 # loss class as p_win above. Cost was real: the stated-edge
                                 # honesty tile divides net over contracts, so it rendered a false
                                 # +0.0c from the day it shipped. net is NOT reconstructable for
                                 # plays settled in that window (the half-spread died with the
                                 # decision book), so the tile reports only net-bearing plays.
                                 "net":pl.get("net"),"ticker":pl.get("ticker"),"bid":pl.get("bid"),
                                 "close_mid":cmid,"clv":clv,
                                 "model_version":p.get("plays_model_version") or p.get("model_version","")})
        if ok and rec["buckets"]:
            resolved.append(rec); del preds[k]; n+=1
    print(f"Resolved {n} events from Kalshi settlement.")
    return n

# --------------------------- reporting -----------------------------
CHALLENGER_REG_DATE="2026-07-16"   # docket item 4 registration; prospective data = targets after this date

def _mix_mean(mm,w):
    t=sum(w.get(k,0.0) for k in mm)
    return sum(w.get(k,0.0)*v["mean"] for k,v in mm.items())/t if t else None

def challenger_weighting_tally(resolved):
    """Docket item 4 live test line: strict prior-DATE walk-forward comparing
    the champion pool (member-count weights) against the registered challenger
    (per-kind inverse-MSE skill weights over the last 60 prior-date
    settlements, eps 0.25, 30-per-provider warmup) on RAW mixture means.
    Recomputed from logged members_by_model on every render: deterministic,
    stateless, and incapable of touching pricing. Positive = challenger
    better. Returns None below 50 usable records."""
    models=("gfs025","ecmwf_ifs025","icon_seamless","gem_global")
    # Count and score CORE providers only. members_by_model may also carry
    # evidence-only AI providers (since 2026-07-28); they have no error history
    # here, would KeyError the skill weights, and must not dilute the docket 4
    # comparison, which is defined over the four pricing providers.
    rows=[r for r in resolved if r.get("members_by_model") and r.get("actual") is not None
          and len([k for k in r["members_by_model"] if k in models])>=3]
    if len(rows)<50: return None
    bydate={}
    for r in rows: bydate.setdefault(r["target"],[]).append(r)
    hist={"HIGH":{k:[] for k in models},"LOW":{k:[] for k in models}}
    diffs=[]; prosp=[]
    for d in sorted(bydate):
        for r in bydate[d]:
            mm={k:v for k,v in r["members_by_model"].items() if k in models}
            a=r["actual"]; hk=hist[r["kind"]]
            e0=abs(_mix_mean(mm,{k:v["n"] for k,v in mm.items()})-a)
            if min(len(hk[k]) for k in models)>=30:
                w={k:1.0/(sum(x*x for x in hk[k][-60:])/len(hk[k][-60:])+0.25) for k in mm}
            else:
                w={k:v["n"] for k,v in mm.items()}
            dv=e0-abs(_mix_mean(mm,w)-a)
            diffs.append(dv)
            if d>CHALLENGER_REG_DATE: prosp.append(dv)
        for r in bydate[d]:
            for k in models:
                if k in r["members_by_model"]:
                    hist[r["kind"]][k].append(r["members_by_model"][k]["mean"]-r["actual"])
    rng=random.Random(11)
    bs=sorted(sum(rng.choices(diffs,k=len(diffs)))/len(diffs) for _ in range(2000))
    return {"n":len(diffs),"adv":sum(diffs)/len(diffs),"ci_lo":bs[100],"ci_hi":bs[1899],
            "n_prosp":len(prosp),"adv_prosp":(sum(prosp)/len(prosp)) if prosp else None}

def _prod_gate(audp, zs, exp_n):
    """The six operative manual-money conditions (FUTURE section 2, approved by
    explicit owner sign-off 2026-07-16), evaluated live. audp = audit-era
    plays, zs = audit-era z-scores, exp_n = cheap-cell play count. Not-binding
    kill legs count as not fired. Returns ordered (label, met, detail)."""
    out=[]
    n=len(audp)
    out.append(("100+ resolved plays", n>=100, f"{n}/100"))
    stake=sum(p.get("stake") or 0 for p in audp); pnl=sum(p.get("pnl") or 0 for p in audp)
    out.append(("fees-inclusive ROI positive", stake>0 and pnl>0,
                f"{100*pnl/stake:+.1f}%" if stake else "no stakes yet"))
    clv=[p["clv"] for p in audp if p.get("clv") is not None]
    if len(clv)>=10:
        rng=random.Random(7)
        bs=sorted(sum(rng.choices(clv,k=len(clv)))/len(clv) for _ in range(2000))
        out.append(("CLV 90% CI above zero", bs[100]>0,
                    f"avg {sum(clv)/len(clv):+.3f}, CI [{bs[100]:+.3f}, {bs[1899]:+.3f}], n={len(clv)}"))
    else:
        out.append(("CLV 90% CI above zero", False, f"n={len(clv)}, too few"))
    if len(zs)>=30:
        m=sum(zs)/len(zs); sd=math.sqrt(sum((z-m)**2 for z in zs)/len(zs))
        out.append(("sd(z) in [0.85, 1.15]", 0.85<=sd<=1.15, f"{sd:.2f}, n={len(zs)}"))
    else:
        out.append(("sd(z) in [0.85, 1.15]", False, f"n={len(zs)}, too few"))
    fired=False; kd="not binding (under 150 plays)"
    if n>=150 and stake>0:
        rng=random.Random(9); rois=[]
        for _ in range(2000):
            smp=rng.choices(audp,k=n); s=sum(p["stake"] for p in smp)
            rois.append(100*sum(p["pnl"] for p in smp)/s if s else 0.0)
        rois.sort()
        roi_fired=rois[1899]<-8.0
        clv_fired=False
        if len(clv)>=150:
            rng2=random.Random(7)
            bs2=sorted(sum(rng2.choices(clv,k=len(clv)))/len(clv) for _ in range(2000))
            clv_fired=bs2[1899]<0
        fired=roi_fired or clv_fired
        kd=("ROI leg FIRED" if roi_fired else "")+(" CLV leg FIRED" if clv_fired else "") or "both legs clear"
    out.append(("neither kill leg fired", not fired, kd))
    out.append(("cheap-entry cell verdict read", exp_n>=40, f"{exp_n}/40"))
    return out

def _era_label(mv):
    """Legacy iff the stamp is empty or a pre-audit stamp; every later
    MODEL_VERSION (v11, v12, v13, ...) is the audit build. The first draft
    matched substrings 'audit'/'capseed' and silently misfiled v13 plays under
    Legacy for three days (caught 2026-07-16): never enumerate the NEW-era
    stamps, enumerate the CLOSED legacy set."""
    return "Legacy (pre-audit)" if ((not mv) or "nimbus-calib" in mv) else "Audit build (v11+)"

def play_pwin(p):
    """Model probability that a SETTLED play's position wins. Prefer the value
    frozen at entry; fall back to reconstructing it from the retained raw mp.

    The fallback exists because resolve_pending dropped p_win when copying a
    frozen play into its resolved record (shipped v7, caught 2026-07-28), so
    every play settled before the fix carries mp but not p_win. That silently
    killed the second arm of the docket 1 cheap-entry cell ("entry <= 0.20 OR
    p_win <= 0.30"), which is a REGISTERED gate definition: the cell must be
    read as registered, not as the narrowed entry-only version the missing
    field left behind. Measured at the time of the fix, the dead arm had cost
    nothing (all 83 audit-era plays with p_win <= 0.30 also had entry <= 0.20,
    so cell membership was 14 either way), but that is luck, not a guarantee.

    Reconstruction is exact at the 0.30 threshold that matters. Entry-time
    p_win uses mp clamped into [TAIL_FLOOR, 1-TAIL_FLOOR] while the logged mp
    is raw, so the two can differ only where the clamp binds, at raw mp below
    0.015 or above 0.985. Backfilling the stored records instead was rejected:
    weather_state.json is live state and is never rewritten."""
    if p.get("p_win") is not None: return p["p_win"]
    mp=p.get("mp")
    if mp is None: return None
    mp_e=min(max(mp,TAIL_FLOOR),1.0-TAIL_FLOOR)
    return mp_e if p.get("side")=="Buy YES" else 1.0-mp_e

def _play_view(pls,resolved):
    """Every display aggregate derived from PLAYS, computed over whatever play
    list is handed in. Called once for the whole book and once for
    current-engine plays alone, so the era toggle governs the entire
    play-derived view rather than only the headline.

    Deliberately NOT in here: calibration bins, learned corrections, source
    MAE, spread skill, the era table, and the gates. Those describe the
    FORECASTER, or are already era-scoped by their own registration, and must
    keep counting the whole record. `resolved` is the matching record scope and
    is used only for the events count."""
    out={}
    if not pls: return out
    wins=sum(1 for p in pls if p["won"]); tot=len(pls); pnl=sum(p["pnl"] for p in pls)
    staked=sum(p["contracts"]*p["entry"] for p in pls)
    nmar=sum(1 for p in pls if p["margin"] is not None)
    out["pnl"]={"n":tot,"wins":wins,"winrate":wins/tot,"net":pnl,"staked":staked,
                "roi":(pnl/staked if staked else 0),"net_units":pnl/BASE_UNIT_USD,
                "avg_margin":sum(p["margin"] for p in pls if p["margin"] is not None)/max(1,nmar)}
    out["n_events"]=len(resolved)
    ncon=sum(p["contracts"] for p in pls)
    if ncon:
        out["edge_real"]=pnl/ncon
        netp=[p for p in pls if p.get("net") is not None]
        ncon_net=sum(p["contracts"] for p in netp)
        if ncon_net:
            out["edge_stated"]=sum(p["net"]*p["contracts"] for p in netp)/ncon_net
            out["edge_stated_n"]=len(netp)
    days=defaultdict(list)
    for p in pls: days[p["target"]].append(p)
    dk=sorted(days)
    if len(dk)>=3:
        rng=random.Random(len(pls)*100003+len(dk))
        rois=[]
        for _ in range(800):
            sample=[p for _x in range(len(dk)) for p in days[rng.choice(dk)]]
            st=sum(p["contracts"]*p["entry"] for p in sample)
            if st: rois.append(sum(p["pnl"] for p in sample)/st)
        rois.sort()
        if rois: out["roi_ci"]=(rois[int(0.05*len(rois))],rois[int(0.95*len(rois))],len(dk))
    cl=[p for p in pls if p.get("clv") is not None]
    live=[p for p in cl if abs(p["clv"])>1e-9 or p.get("close_mid")!=p.get("mid")]
    if cl:
        out["clv"]={"n":len(cl),"beat":sum(1 for p in cl if p["clv"]>0),
                    "avg":sum(p["clv"] for p in cl)/len(cl),"live":len(live)}
    byc=defaultdict(lambda:{"n":0,"w":0,"pnl":0.0})
    for p in pls:
        a=byc[p["code"]]; a["n"]+=1; a["w"]+=1 if p["won"] else 0; a["pnl"]+=p["pnl"]
    out["by_city"]=sorted(((CITIES[c][3],v["n"],v["w"],v["pnl"]) for c,v in byc.items()),key=lambda x:-x[3])
    byu=defaultdict(lambda:{"n":0,"w":0,"pnl":0.0})
    for p in pls:
        a=byu[p["units"]]; a["n"]+=1; a["w"]+=1 if p["won"] else 0; a["pnl"]+=p["pnl"]
    out["by_unit"]=sorted(((u,v["n"],v["w"],v["pnl"]) for u,v in byu.items()),key=lambda x:-x[0])
    def _win(dcount):
        cut=(TODAY-dt.timedelta(days=dcount)).isoformat()
        sel=[x for x in pls if x["target"]>=cut]
        if not sel: return None
        w=sum(1 for x in sel if x["won"])
        return {"n":len(sel),"w":w,"wr":w/len(sel),"u":sum(x["pnl"] for x in sel)/BASE_UNIT_USD}
    out["windows"]={"day":_win(1),"week":_win(7),"all":_win(100000)}
    EB=[(0.0,0.08,"under 8%"),(0.08,0.15,"8-15%"),(0.15,0.25,"15-25%"),(0.25,9.0,"25%+")]
    bye=[]
    for lo,hi,lab in EB:
        sel=[x for x in pls if x.get("edge") is not None and lo<=abs(x["edge"])<hi]
        if sel:
            w=sum(1 for x in sel if x["won"]); bye.append((lab,len(sel),w,sum(x["pnl"] for x in sel)))
    out["by_edge"]=bye
    PB=[(0.0,0.50,"under 50%"),(0.50,0.65,"50-65%"),(0.65,0.80,"65-80%"),(0.80,1.01,"80%+")]
    byp=[]
    for lo,hi,lab in PB:
        sel=[]
        for x in pls:
            if x.get("mp") is None: continue
            pw=x["mp"] if x.get("side")=="Buy YES" else 1-x["mp"]
            if lo<=pw<hi: sel.append((x,pw))
        if sel:
            w=sum(1 for x,_ in sel if x["won"])
            stk=sum(x["contracts"]*x["entry"] for x,_ in sel)
            pn=sum(x["pnl"] for x,_ in sel)
            avgp=sum(pw for _,pw in sel)/len(sel)
            byp.append((lab,len(sel),w,avgp,pn,(pn/stk if stk else 0.0)))
    out["by_pwin"]=byp
    spls=sorted(pls,key=lambda x:x["target"])
    ser=[]; run=0.0
    for p in spls:
        run+=p["pnl"]/BASE_UNIT_USD; ser.append(round(run,2))
    out["cum"]=ser
    out["cum_dates"]=(spls[0]["target"],spls[-1]["target"])
    out["recent"]=sorted(pls,key=lambda x:x["target"],reverse=True)
    return out

def compute_report(state):
    resolved=[r for r in state.get("resolved",[]) if not r.get("gated")]   # quarantined records never enter any aggregate
    bk=[b for r in resolved for b in r["buckets"]]
    pls=[pl for r in resolved for pl in r["plays"]]
    rep={"n_events":len(resolved),"n_buckets":len(bk),"plays":pls}
    if bk:
        rep["brier_model"]=sum((b["mp"]-b["hit"])**2 for b in bk)/len(bk)
        rep["brier_market"]=sum((b["mid"]-b["hit"])**2 for b in bk)/len(bk)
    # RPS: the ordered-bucket proper score (audit batch 9 verdict: the right
    # headline for ladder markets, because missing by one bucket should score
    # better than missing by five, which per-bucket Brier cannot see). Only
    # records whose buckets carry rep (v6+) qualify. Market probabilities are
    # the normalized mids: a devig used for SCORING ONLY, never for pricing.
    rme,rmk=[],[]
    for r in resolved:
        bs=[b for b in r["buckets"] if b.get("rep") is not None]
        if len(bs)<3 or sum(b["hit"] for b in bs)!=1: continue
        bs=sorted(bs,key=lambda b:b["rep"])
        sm=sum(b["mp"] for b in bs) or 1.0; sk=sum(b["mid"] for b in bs) or 1.0
        Fm=Fk=O=0.0; sA=sB=0.0
        for b in bs[:-1]:
            Fm+=b["mp"]/sm; Fk+=b["mid"]/sk; O+=b["hit"]
            sA+=(Fm-O)**2; sB+=(Fk-O)**2
        rme.append(sA); rmk.append(sB)
    if rme:
        rep["rps_model"]=sum(rme)/len(rme); rep["rps_market"]=sum(rmk)/len(rmk); rep["rps_n"]=len(rme)
    # nowcast shadow tally (FUTURE 5 gate: truncated must beat untruncated on
    # CRPS AND RPS over 30+ graded same-day HIGH events before plays may use it)
    ncs=[r["nowcast"] for r in resolved if r.get("nowcast") and r["nowcast"].get("rps_u") is not None]
    if ncs:
        rep["nowcast"]={"n":len(ncs),
            "rps_u":sum(g["rps_u"] for g in ncs)/len(ncs),
            "rps_t":sum(g["rps_t"] for g in ncs)/len(ncs),
            "crps_u":sum(g.get("crps_u") or 0.0 for g in ncs)/len(ncs),
            "crps_t":sum(g.get("crps_t") or 0.0 for g in ncs)/len(ncs),
            "wins":sum(1 for g in ncs if g["rps_t"]<g["rps_u"])}
    ch=challenger_weighting_tally(resolved)
    if ch: rep["challenger_w"]=ch
    # calibration bins
    bins=[]
    for lo in [i/10 for i in range(10)]:
        sel=[b for b in bk if lo<=b["mp"]<lo+0.1]
        if sel:
            n=len(sel); hits=sum(b["hit"] for b in sel)
            wlo,whi=_wilson(hits,n)
            bins.append((lo,n,sum(b["mp"] for b in sel)/n,hits/n,wlo,whi))
    rep["bins"]=bins
    # Forecast-source skill (audit batch 10 display; data from batches 2-5):
    # MAE of each raw model mean, NBM, HRRR, and the corrected pooled mean.
    src=defaultdict(lambda:[0.0,0])
    for r in resolved:
        a=r.get("actual")
        if a is None: continue
        if r.get("mean") is not None:
            src["Pooled ensemble (corrected)"][0]+=abs(r["mean"]-a); src["Pooled ensemble (corrected)"][1]+=1
        for m,d in (r.get("members_by_model") or {}).items():
            src[m][0]+=abs(d["mean"]-a); src[m][1]+=1
        for k,v in (r.get("ref") or {}).items():
            nm="NBM (station-calibrated)" if k=="nbm" else "HRRR (short-lead)"
            src[nm][0]+=abs(v-a); src[nm][1]+=1
    rep["sources"]=sorted(((k,s/n,n) for k,(s,n) in src.items() if n),key=lambda x:x[1])
    # Rain shadow tally (FUTURE 5b, evidence only): pooled wet-fraction Brier vs
    # the market's mid over graded city-days. rain passes through reporting_view
    # untouched (dict(state, resolved=...) keeps top-level keys).
    rsh=state.get("rain") or {}
    rres=rsh.get("resolved") or []; rpend=rsh.get("pending") or {}
    if rres or rpend:
        # Render even before the first grading: a shadow that shows nothing for
        # its first day reads as broken to the owner (the CLV tile solved the
        # same problem with an explicit pending state, batch 5).
        rep["rain"]={"n":len(rres),"pend":len(rpend)}
        if rres:
            rep["rain"].update(
                brier_pool=sum((r["pool_wet"]-r["hit"])**2 for r in rres)/len(rres),
                brier_mkt=sum((r["mid"]-r["hit"])**2 for r in rres)/len(rres),
                wet_rate=sum(r["hit"] for r in rres)/len(rres))
    # Calibration engine series (owner request 2026-07-06): rolling MAE of the
    # UNCORRECTED forecast, the CORRECTED forecast, and the market-implied mean,
    # in resolution order. Raw-vs-corrected divergence IS the learning engine
    # visible; the market line is the bar both must clear. The rounded stored
    # actual adds identical noise to every line, so comparisons stay fair.
    W=30
    crows=[r for r in resolved if r.get("bias") is not None and r.get("actual") is not None]
    if len(crows)>=8:
        raw=[abs(r["bias"]-(r.get("bias_corr") or 0.0)) for r in crows]
        cor=[abs(r["bias"]) for r in crows]
        mkt=[]
        for r in crows:
            bs=[b for b in r.get("buckets",[]) if b.get("rep") is not None and b.get("mid")]
            sm=sum(b["mid"] for b in bs) if len(bs)>=3 else 0
            mkt.append(abs(sum(b["mid"]*b["rep"] for b in bs)/sm-r["actual"]) if sm else None)
        def _roll(xs,minn=8):
            out=[]
            for i in range(len(xs)):
                w=[x for x in xs[max(0,i-W+1):i+1] if x is not None]
                out.append(round(sum(w)/len(w),3) if len(w)>=minn else None)
            return out
        rep["calib_series"]={"raw":_roll(raw),"cor":_roll(cor),"mkt":_roll(mkt),
            "active":sum(1 for r in crows if abs(r.get("bias_corr") or 0.0)>0.01)}
        zs=[(r["bias"]/r["psd"]) if r.get("psd") else None for r in crows]
        dso=[]
        for i in range(len(zs)):
            w=[z for z in zs[max(0,i-W+1):i+1] if z is not None]
            if len(w)>=10:
                m=sum(w)/len(w); dso.append(round(math.sqrt(sum((z-m)**2 for z in w)/len(w)),3))
            else: dso.append(None)
        if any(v is not None for v in dso): rep["disp_series"]=dso
    # learned calibration currently in force (bias correction + dressing sigma)
    cal=calib_params(state)
    rep["calib"]=sorted(((CITIES[k[0]][3],k[1],v["corr"],v["sigma"],v["n"])
                         for k,v in cal.items() if isinstance(k,tuple)),
                        key=lambda x:-abs(x[2]))
    rep["gsigma"]=cal.get("_gsigma",DRESS_SIGMA_DEFAULT)
    # per-city bias
    cb=defaultdict(list)
    for r in resolved:
        if r["bias"] is not None: cb[(r["code"],r["kind"])].append(r["bias"])
    rep["city_bias"]=sorted(((CITIES[c][3],k,sum(v)/len(v),len(v)) for (c,k),v in cb.items()),key=lambda x:-abs(x[2]))
    # play performance
    if pls:
        rep.update(_play_view(pls,resolved))
        # ERA VIEW (display only): the identical play-derived tables over
        # current-engine plays alone. Before this, only the headline and the
        # chart followed the toggle while every table stayed all-time, which
        # was actively misleading: San Antonio reads +31.8u all-time and +0.1u
        # on the current engine, because two retired-engine longshot hits carry
        # the entire number. Gates, kill criteria, and the forecast-record
        # tables are untouched and still count the whole book.
        curp=[p for p in pls if _era_label(p.get("model_version") or "")!="Legacy (pre-audit)"]
        if curp and len(curp)<len(pls):
            rep["cur"]=_play_view(curp,[r for r in resolved
                                        if _era_label(r.get("model_version") or "")!="Legacy (pre-audit)"])
        # Era split in units: the honest instrument for "is the audit build
        # better", once its plays settle. Version stamps make this a query.
        eras=defaultdict(lambda:[0,0,0.0,0.0])
        for p in pls:
            mv=p.get("model_version") or ""
            lab=_era_label(mv)
            e=eras[lab]; e[0]+=1; e[1]+=1 if p["won"] else 0
            e[2]+=p["units"]; e[3]+=p["pnl"]/BASE_UNIT_USD
        rep["eras"]=sorted(((k,)+tuple(v) for k,v in eras.items()))
        # Core vs experimental split (docket 1, registered 2026-07-13): the
        # cheap-entry cell is an EXPERIMENT the paper ledger pays tuition on;
        # showing it separately keeps the core strategy readable in both
        # directions and shows the docket gate filling in public.
        audp=[p for p in pls if _era_label(p.get("model_version") or "")!="Legacy (pre-audit)"]
        def _cell(p):
            pw=play_pwin(p)
            return p["entry"]<=0.20 or (pw is not None and pw<=0.30)
        rep["book_split"]={
            "core":{"n":len([p for p in audp if not _cell(p)]),
                    "w":sum(1 for p in audp if not _cell(p) and p["won"]),
                    "stake_u":sum(p["units"] for p in audp if not _cell(p)),
                    "net_u":sum(p["pnl"] for p in audp if not _cell(p))/BASE_UNIT_USD},
            "exp":{"n":len([p for p in audp if _cell(p)]),
                   "w":sum(1 for p in audp if _cell(p) and p["won"]),
                   "stake_u":sum(p["units"] for p in audp if _cell(p)),
                   "net_u":sum(p["pnl"] for p in audp if _cell(p))/BASE_UNIT_USD}}
        zsa=[(r["actual"]-r["mean"])/r["psd"] for r in resolved
             if r.get("psd") and r.get("actual") is not None
             and _era_label(r.get("model_version") or "")!="Legacy (pre-audit)"]
        rep["prod_gate"]=_prod_gate(audp, zsa, rep["book_split"]["exp"]["n"])
    # Spread-skill (FUTURE 2b, gate n>=100): does the spread the model REPORTS
    # predict how wrong it turns out to be? Read 2026-07-25 at n=804 as +0.250
    # with a 90% CI excluding zero, which is what earns spread a place on the
    # boards. Recomputed live so the claim on the page is never stale.
    sp=[(r["sd"],abs(r["mean"]-r["actual"])) for r in resolved
        if r.get("sd") and r.get("actual") is not None and r.get("mean") is not None]
    if len(sp)>=100:
        nn=len(sp)
        mx=sum(a for a,_ in sp)/nn; my=sum(b for _,b in sp)/nn
        cov=sum((a-mx)*(b-my) for a,b in sp)/nn
        sx=math.sqrt(sum((a-mx)**2 for a,_ in sp)/nn); sy=math.sqrt(sum((b-my)**2 for _,b in sp)/nn)
        bands=[]
        for lab,lo,hi in (("tight",0.0,SPREAD_TIGHT),("normal",SPREAD_TIGHT,SPREAD_WIDE),("wide",SPREAD_WIDE,1e9)):
            sel=[b for a,b in sp if lo<a<=hi]
            if sel: bands.append((lab,len(sel),sum(sel)/len(sel)))
        rep["spread_skill"]={"n":nn,"corr":(cov/(sx*sy) if sx and sy else 0.0),"bands":bands}

    return rep

# ----------------------------- render ------------------------------
_css_override=os.path.join(HERE,"_style.css")
CSS=""
if os.path.exists(_css_override):
    with open(_css_override) as _f: CSS=_f.read()
if not CSS:
 CSS=""":root{--bg:#0d1014;--panel:#14181e;--line:#232a33;--tx:#e7ecf2;--mut:#8b97a6;--dim:#4d5765;--teal:#5ad1c8;--up:#46c08a;--dn:#e3a23c;--red:#e25a4d;--gold:#e8c468}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font-family:Inter,system-ui,sans-serif;font-size:14px;line-height:1.45}
header{position:sticky;top:0;z-index:5;background:var(--bg);padding:16px 16px 8px;border-bottom:1px solid var(--line)}
.hd,.wrap{max-width:1120px;margin:0 auto}.wrap{padding:0 16px 64px}
.brand{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.brand h1{font-size:18px;font-weight:600;margin:0}.brand .dot{color:var(--teal)}
.brand .sub{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--mut)}
.nav{display:flex;gap:8px;margin-top:10px}.nav a{text-decoration:none;font-size:13px;padding:7px 13px;border-radius:8px;border:1px solid var(--line);color:var(--mut);background:var(--panel)}
.nav a.on{color:#0d1014;background:var(--teal);border-color:var(--teal);font-weight:600}
.strip{margin-top:9px;display:flex;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--mut)}
.chip{font-family:'IBM Plex Mono',monospace;border:1px solid var(--line);border-radius:999px;padding:3px 10px;background:var(--panel)}.chip b{color:var(--tx)}
.chip.pos b{color:var(--up)}.chip.neg b{color:var(--red)}
.note{margin:12px 0;padding:11px 13px;border:1px solid var(--line);border-left:2px solid var(--teal);border-radius:8px;background:var(--panel);color:var(--mut);font-size:12.5px}.note b{color:var(--tx)}
h2.sec{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:20px 0 8px}
table{width:100%;border-collapse:collapse}th{text-align:left;font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--dim);font-weight:500;padding:8px 10px;border-bottom:1px solid var(--line)}
th.n,td.n{text-align:right;font-family:'IBM Plex Mono',monospace}td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}tbody tr:hover{background:var(--panel)}
.mk .mt{font-weight:500}.mk .me{font-size:11.5px;color:var(--dim);margin-top:2px}td.model{color:var(--teal)}td.edge{color:var(--up);font-weight:600}
.pl{font-family:'IBM Plex Mono',monospace;font-size:12.5px;white-space:nowrap}.up{color:var(--up)}.dn{color:var(--dn)}.dim{color:var(--dim)}.red{color:var(--red)}
.unit{font-family:'IBM Plex Mono',monospace;font-weight:700;font-size:12px;padding:2px 9px;border-radius:6px;display:inline-block;min-width:44px;text-align:center}
.u2{background:var(--gold);color:#0d1014}.u15{background:rgba(70,192,138,.2);color:var(--up);border:1px solid rgba(70,192,138,.4)}.u1{background:rgba(227,162,60,.16);color:var(--dn)}.u0{background:rgba(125,139,156,.14);color:var(--mut)}
tr.play td{background:rgba(70,192,138,.05)}
.rating{display:flex;align-items:center;gap:14px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--panel);margin:8px 0}
.rating .big{font-family:'IBM Plex Mono',monospace;font-size:26px;font-weight:700;line-height:1;padding:8px 14px;border-radius:10px}.rating .txt{color:var(--mut);font-size:13px}.rating .txt b{color:var(--tx)}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}.kbox{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:12px 16px;min-width:120px}
.kbox .v{font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:600}.kbox .l{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;margin-top:2px}
.eratog{display:flex;gap:6px;margin:10px 0 2px}.eratog button{font:600 12px 'IBM Plex Mono',monospace;color:var(--mut);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer}
.eratog button.on{color:var(--tx);border-color:var(--teal)}.eranote{font-size:11.5px;color:var(--mut);margin:2px 0 6px}
.tag{font-family:'IBM Plex Mono',monospace;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:5px}.c-hi{background:rgba(70,192,138,.14);color:var(--up)}
.c-wide{background:rgba(227,162,60,.14);color:var(--dn)}
.gloss{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.gloss summary{cursor:pointer;color:var(--teal);font-size:13px;font-weight:600}
.gloss dl{margin:10px 0 2px}.gloss dt{font-weight:600;font-size:12.5px;margin-top:10px}
.gloss dd{margin:2px 0 0;font-size:12.5px;color:var(--mut);line-height:1.5}.c-md{background:rgba(227,162,60,.14);color:var(--dn)}.c-lo{background:rgba(125,139,156,.12);color:var(--mut)}
.block{margin:14px 0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--panel)}.bh{padding:10px 12px;font-weight:600;border-bottom:1px solid var(--line)}.bm{padding:6px 12px;font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--mut);border-bottom:1px solid var(--line)}.block td,.block th{padding:8px 12px}
.tabs{display:flex;gap:4px;overflow-x:auto;padding:6px 0}.tab{flex:0 0 auto;background:transparent;border:1px solid transparent;color:var(--mut);font:inherit;font-size:13px;padding:7px 12px;border-radius:8px;cursor:pointer;white-space:nowrap}.tab:hover{color:var(--tx);background:var(--panel)}.tab.active{color:var(--tx);background:var(--panel);border-color:var(--line)}.panel{display:none}.panel.active{display:block}
.empty{padding:20px;border:1px dashed var(--line);border-radius:10px;color:var(--mut);background:var(--panel)}.empty b{color:var(--tx)}
.pcard{border:1px solid var(--line);border-radius:12px;background:var(--panel);margin-top:10px;overflow:hidden}
.pcard.side-yes{border-left:4px solid var(--up)}.pcard.side-no{border-left:4px solid var(--red)}
.ptop{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px}
.pcity{font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
.prange{font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:700;margin-top:3px;line-height:1.1}
.pside{font-family:'IBM Plex Mono',monospace;font-weight:800;font-size:24px;padding:8px 14px;border-radius:10px;min-width:78px;text-align:center;line-height:1}
.pside .psub{font-size:12px;font-weight:600;margin-top:3px;opacity:.85}
.sb-yes{background:var(--up);color:#07130d}.sb-no{background:var(--red);color:#1c0707}
.pbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:0 16px 8px}
.pmoney{font-family:'IBM Plex Mono',monospace;font-size:14px;font-weight:600}
.pwin{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--mut)}
.pflag{font-size:11.5px;font-weight:600;color:var(--dn);background:rgba(227,162,60,.14);padding:2px 8px;border-radius:6px}
.pdata{padding:8px 16px;font-size:11.5px;color:var(--dim);border-top:1px solid var(--line)}
svg{max-width:100%;height:auto}.card{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:14px 16px;margin:10px 0}"""

# --- spread display (FUTURE 2b spread-skill check, READ 2026-07-25 at n=804) ---
# corr(member sd, realized absolute error) = +0.250, 90% CI [+0.186, +0.317],
# so the spread the model reports really does predict how wrong it will be.
# Cut points are the measured sd quartiles over 804 settlements, and the error
# each band actually realized: tight 1.52 deg, normal 1.65, wide 2.32. Display
# only: these are NOT in _KNOB_NAMES because nothing here touches pricing.
SPREAD_TIGHT = 1.69   # sd at or below this is the narrowest measured quartile
SPREAD_WIDE  = 2.80   # sd above this is the widest measured quartile

def spread_label(sd):
    """(tag text, css class) for a forecast spread, or None when unremarkable."""
    if sd is None: return None
    if sd <= SPREAD_TIGHT: return ("tight spread", "c-hi")
    if sd > SPREAD_WIDE:   return ("wide spread", "c-wide")
    return None

def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def pct(x): return "%.0f%%"%(x*100)
def fmt_oi(o): o=o or 0; return "%.0fk"%(o/1000) if o>=1000 else "%.0f"%o
def _lead(l): return {0:"resolves today",1:"tomorrow"}.get(l,"%d days out"%l)
def _edge(e):
    if e>0: return '<span class="up">+%s</span>'%pct(e)
    if e<0: return '<span class="dn">%s</span>'%pct(e)
    return '<span class="dim">0%</span>'
def unit_badge(u):
    if u>=2: return '<span class="unit u2">2u</span>'
    if u>=1.5: return '<span class="unit u15">1.5u</span>'
    if u>=1: return '<span class="unit u1">1u</span>'
    return '<span class="unit u0">no bet</span>'
def head(active,updated,extra=""):
    a=lambda p:'on' if active==p else ''
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width, initial-scale=1'><title>Nimbus</title>"
      "<link rel='preconnect' href='https://fonts.googleapis.com'>"
      "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap' rel='stylesheet'>"
      f"<style>{CSS}</style></head><body>"+(STALE_JS%int(time.time()))+"<header><div class='hd'>"
      "<div class='brand'><h1>Nimbus<span class='dot'> .</span></h1>"
      f"<span class='sub'>{updated} &middot; {MODEL_VERSION} &middot; calibrated ensemble {'+'.join(ENSEMBLE_MODELS)} &middot; settled by Kalshi</span></div> {DOT} cfg {CONFIG_HASH}"
      f"<div class='nav'><a class='{a('bets')}' href='index.html'>Today's bets</a>"
      f"<a class='{a('results')}' href='results.html'>Results tracker</a></div>{extra}</div></header><div class='wrap'>")

def svg_line(vals,w=680,h=170,pad=26,title="cumulative units P&L",dates=None):
    if not vals: return ""
    lo=min(0,min(vals)); hi=max(0,max(vals)); rng=(hi-lo) or 1
    def X(i): return pad+(w-2*pad)*(i/max(1,len(vals)-1))
    def Y(v): return h-pad-(h-2*pad)*((v-lo)/rng)
    pts=" ".join(f"{X(i):.1f},{Y(v):.1f}" for i,v in enumerate(vals))
    zero=Y(0)
    aria=esc(f"{title}: {len(vals)} resolved plays, ending at {vals[-1]:+.1f} units")
    # x-axis date labels (owner request 2026-07-29): without them the chart's
    # early-history swings read as recent
    dl=""
    if dates:
        dl=(f"<text x='{pad}' y='{h-6}' fill='#8b97a6' font-size='10' font-family=monospace>{esc(dates[0])}</text>"
            f"<text x='{w-pad}' y='{h-6}' fill='#8b97a6' font-size='10' font-family=monospace text-anchor='end'>{esc(dates[1])}</text>")
    return (f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='{aria}'><line x1='{pad}' y1='{zero:.1f}' x2='{w-pad}' y2='{zero:.1f}' "
            f"stroke='#232a33'/><polyline points='{pts}' fill='none' stroke='#5ad1c8' stroke-width='2'/>"
            f"<text x='{pad}' y='14' fill='#8b97a6' font-size='11' font-family=monospace>{esc(title).replace('P&L','P&amp;L')}</text>{dl}</svg>")

def svg_multi(series,labels,colors,w=680,h=190,pad=26,ref=None):
    """Multi-line chart; None values break the line (data-gated segments)."""
    vals=[v for s in series for v in s if v is not None]
    if not vals: return ""
    lo=min(vals+([ref] if ref is not None else [])); hi=max(vals+([ref] if ref is not None else []))
    rng=(hi-lo) or 1; n=max(len(s) for s in series)
    X=lambda i: pad+(w-2*pad)*(i/max(1,n-1)); Y=lambda v: h-pad-(h-2*pad)*((v-lo)/rng)
    aria=esc("Line chart comparing "+", ".join(labels)+(", reference %g"%ref if ref is not None else ""))
    out=[f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='{aria}'>"]
    if ref is not None:
        out.append(f"<line x1='{pad}' y1='{Y(ref):.1f}' x2='{w-pad}' y2='{Y(ref):.1f}' stroke='#232a33' stroke-dasharray='4 4'/>")
        out.append(f"<text x='{w-pad-8}' y='{Y(ref)-5:.1f}' fill='#8b97a6' font-size='10' font-family=monospace text-anchor='end'>{ref:g}</text>")
    for s,c in zip(series,colors):
        seg=[]
        for i,v in enumerate(s):
            if v is None:
                if len(seg)>1: out.append(f"<polyline points='{' '.join(seg)}' fill='none' stroke='{c}' stroke-width='2'/>")
                seg=[]
            else: seg.append(f"{X(i):.1f},{Y(v):.1f}")
        if len(seg)>1: out.append(f"<polyline points='{' '.join(seg)}' fill='none' stroke='{c}' stroke-width='2'/>")
    x=pad
    for lab,c,s in zip(labels,colors,series):
        if any(v is not None for v in s):
            out.append(f"<text x='{x}' y='14' fill='{c}' font-size='11' font-family=monospace>{esc(lab)}</text>")
            x+=len(lab)*7+18
    out.append("</svg>")
    return "".join(out)

def svg_bars(items,w=680,bar=26,gap=10,pad=90):
    if not items: return ""
    h=len(items)*(bar+gap)+16
    mx=max(abs(v) for _,v in items) or 1
    aria=esc("Bar chart: "+", ".join(f"{lab} {v:+.2f}" for lab,v in items))
    out=[f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='{aria}'>"]
    for i,(lab,v) in enumerate(items):
        y=8+i*(bar+gap); wpx=(w-pad-20)*(abs(v)/mx); col="#46c08a" if v>=0 else "#e25a4d"
        out.append(f"<text x='0' y='{y+bar/2+4:.0f}' fill='#e7ecf2' font-size='12'>{esc(lab)[:16]}</text>")
        out.append(f"<rect x='{pad}' y='{y}' width='{wpx:.0f}' height='{bar}' rx='4' fill='{col}'/>")
        out.append(f"<text x='{pad+wpx+6:.0f}' y='{y+bar/2+4:.0f}' fill='#8b97a6' font-size='11' font-family=monospace>{v:+.2f}</text>")
    out.append("</svg>"); return "".join(out)

RATING_TXT={"2u":"an exceptional day. A proven-city edge worth your max size.",
            "1.5u":"a strong day. Solid, higher-probability edges.",
            "1u":"a decent day. Real but modest, or capped longshots.",
            "NO BET":"a sit-out day. Nothing clears the bar; the right move is no bet."}

def _health_strip(health,alerts=None):
    if not health and not alerts: return ""
    health=health or {}
    fails=health.get("cities_failed") or []
    okc=health.get("cities",0)-len(fails)
    s=("<div class='strip'><span class='chip'>ladders <b>%d</b></span>"
       "<span class='chip'>forecast cities <b>%d/%d</b></span>"
       %(health.get("ladders",0),okc,health.get("cities",0)))
    if fails: s+="<span class='chip neg'>fetch failed: <b>%s</b></span>"%esc(", ".join(fails))
    if health.get("capped"): s+="<span class='chip'>cap trimmed <b>%d</b> plays</span>"%health["capped"]
    if health.get("new_24h") is not None: s+="<span class='chip'>new plays 24h <b>%d</b></span>"%health["new_24h"]
    if health.get("state_kb"):
        # After a 7b split the live count alone would understate the record, so
        # the archived half is named rather than quietly dropped from the chip.
        s+="<span class='chip'>state <b>%d KB</b> / <b>%d</b> resolved</span>"%(health["state_kb"],health.get("resolved_n",0))
        if health.get("archived_n"): s+="<span class='chip'>archived <b>%d</b></span>"%health["archived_n"]
    for g in (health.get("gated") or []):
        s+="<span class='chip neg'>gated: <b>%s</b></span>"%esc(g)
    for a in (alerts or []):
        s+="<span class='chip neg'>%s</span>"%esc(a)
    return s+"</div>"

def render_bets(rows,plays,updated,health=None):
    best_u=max((p["units"] for p in plays),default=0)
    rlab="2u" if best_u>=2 else "1.5u" if best_u>=1.5 else "1u" if best_u>=1 else "NO BET"
    rtxt=RATING_TXT[rlab]
    ucls={"2u":"u2","1.5u":"u15","1u":"u1","NO BET":"u0"}[rlab]
    counts=defaultdict(int)
    for p in plays: counts[p["units"]]+=1
    cstr=", ".join(f'{counts[u]}x {unit_str(u)}' for u in sorted(counts,reverse=True)) or "none"
    if plays:
        ptab=""
        for r in plays[:30]:
            yes=r["side"]=="Buy YES"
            sc="side-yes" if yes else "side-no"; sb="sb-yes" if yes else "sb-no"; word="YES" if yes else "NO"
            city=esc(r["label"].split(" (")[0]); mk="Highest temp" if r["kind"]=="HIGH" else "Lowest temp"
            pw=("win prob %.0f%%"%(r["p_win"]*100)) if r.get("p_win") is not None else ""
            flag=(f'<span class="pflag">{esc(r["size_reason"])}</span>') if r.get("size_reason") else ""
            if r.get("hiconf"): flag='<span class="tag c-hi">high confidence</span>'+flag
            _sp=spread_label(r.get("sd"))
            sptag=(f'<span class="tag {_sp[1]}">{_sp[0]}</span>') if _sp else ""
            ptab+=(f'<div class="pcard {sc}"><div class="ptop">'
                   f'<div><div class="pcity">{city} &middot; {mk} &middot; {r["date"].strftime("%b %d")}</div>'
                   f'<div class="prange">{esc(r["bucket"])}</div></div>'
                   f'<div class="pside {sb}">{word}<div class="psub">{r["entry"]*100:.0f}\u00a2</div></div></div>'
                   f'<div class="pbar">{unit_badge(r["units"])}'
                   f'<span class="pwin">{pw}</span>{sptag}{flag}</div>'
                   f'<div class="pdata">model {pct(r["mp"])} &middot; market {pct(r["mid"])} &middot; '
                   f'edge +{pct(abs(r["edge"]))} &middot; net +{r["net"]*100:.0f}\u00a2 &middot; '
                   f'spread \u00b1{r["sd"]:.1f}\u00b0 &middot; OI {fmt_oi(r["oi"])}</div></div>')
    else:
        ptab=('<div class="empty"><b>No bets today.</b> Run in the morning; same-day lows are already '
              'realized and same-day highs after ~2pm too. Realized / offset ladders under By city are '
              'shown to illustrate the comparison, not to bet.</div>')
    # by city
    bycity=defaultdict(list)
    for r in rows: bycity[r["code"]].append(r)
    order=sorted(bycity,key=lambda c:-max((x["net"] for x in bycity[c]),default=0))
    ctabs=cpan=""
    for code in order:
        cid="c"+code; np=sum(1 for r in bycity[code] if r.get("stake"))
        ctabs+=f'<button class="tab" data-t="{cid}">{esc(CITIES[code][3])}{(" ("+str(np)+")") if np else ""}</button>'
        sub=defaultdict(list)
        for r in bycity[code]: sub[(r["kind"],r["date"])].append(r)
        blocks=""
        for (kind,d),rs in sorted(sub.items(),key=lambda kv:(kv[0][1],kv[0][0])):
            r0=rs[0]
            rt=('<span class="tag c-lo">realized</span>' if r0["realized"] else
                (f'<span class="tag c-md">offset {r0["offset"]:+.1f}\u00b0</span>' if r0["biased"] else
                 '<span class="tag c-hi">live</span>'))
            hd=f'{"High" if kind=="HIGH" else "Low"} &middot; {d.strftime("%a %b %d")} {rt}'
            mt=f'forecast {r0["mean"]:.0f}\u00b0 \u00b1{r0["sd"]:.1f}\u00b0 &middot; {_lead(r0["lead"])} &middot; model\u2212mkt {r0["offset"]:+.1f}\u00b0'
            tr=""
            for r in sorted(rs,key=lambda x:-x["mp"]):
                pcell=(f'{unit_badge(r["units"])} {r["side"]} @ {r["entry"]*100:.0f}\u00a2' if r.get("stake")
                       else ('<span class="tag c-md">capped</span>' if r.get("capped") else '<span class="dim">\u00b7</span>'))
                tr+=(f'<tr><td>{esc(r["bucket"])}</td><td class="n">{pct(r["mid"])}</td><td class="n model">{pct(r["mp"])}</td>'
                     f'<td class="n">{_edge(r["edge"])}</td><td class="n">{fmt_oi(r["oi"])}</td><td class="pl">{pcell}</td></tr>')
            blocks+=(f'<div class="block"><div class="bh">{hd}</div><div class="bm">{mt}</div>'
                     f'<table><thead><tr><th>Bucket</th><th class="n">Mkt</th><th class="n">Model</th>'
                     f'<th class="n">Edge</th><th class="n">OI</th><th>Play</th></tr></thead><tbody>{tr}</tbody></table></div>')
        cpan+=f'<div class="panel" id="{cid}">{blocks}</div>'
    html=(head("bets",updated,_health_strip(health))+
      "<div class='note'><b>Confidence = size.</b> Probabilities come from a bias-corrected, kernel-dressed "
      "multi-model ensemble that learns each city's error from Kalshi settlements. Plays are sized 2u / 1.5u / 1u "
      "and listed highest win probability first within each size. A city cannot earn a 2u until it has proven it "
      "beats the market on the Results tab.</div>"
      f"<h2 class='sec'>Today</h2><div class='rating'><div class='big unit {ucls}'>{rlab}</div>"
      f"<div class='txt'>Today is <b>{rtxt}</b><br>Plays: {cstr}.</div></div>"+ptab+
      "<h2 class='sec'>By city</h2><div class='tabs'>"+ctabs+"</div>"+cpan+
      "<script>document.querySelectorAll('.tab').forEach(function(b){b.onclick=function(){"
      "document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));"
      "document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));"
      "b.classList.add('active');document.getElementById(b.dataset.t).classList.add('active');};});"
      "var f=document.querySelector('.tab');if(f){f.classList.add('active');document.getElementById(f.dataset.t).classList.add('active');}</script>"
      "</div></body></html>")
    with open(os.path.join(OUT_DIR,"index.html"),"w",encoding="utf-8") as fp: fp.write(html)

def unit_str(u): return "2u" if u>=2 else "1.5u" if u>=1.5 else "1u" if u>=1 else "0u"

# Plain-English glossary (FUTURE 4). Every metric on this page is a term of
# art, and a track record nobody can read is a track record nobody can check.
# Rendered on BOTH the populated and the empty results page: a reader looking
# at their first board, before anything has settled, is exactly who needs it.
# Collapsed by default so it never competes with the numbers; no JS.
GLOSSARY=("<h2 class='sec'>What these words mean</h2>"
              "<details class='gloss'><summary>Plain English, one line each</summary>"
              "<dl>"
              "<dt>Brier / RPS</dt><dd>Scores for how good the probabilities were, not just "
              "whether a bet won. Lower is better. RPS is the fairer one here because it gives "
              "partial credit for missing by one degree instead of five.</dd>"
              "<dt>CRPS</dt><dd>The same idea for the whole forecast range rather than one bucket. "
              "Lower is better.</dd>"
              "<dt>Calibration</dt><dd>Do things the model calls 70 percent actually happen about "
              "70 percent of the time? If yes the model is honest, and profit is then a question "
              "of prices and fees rather than of forecasting.</dd>"
              "<dt>sd(z)</dt><dd>Whether the model's confidence is right-sized. Near 1.0 is healthy. "
              "Below 1 means it is too cautious, above 1 means it is overconfident.</dd>"
              "<dt>Spread</dt><dd>How much the weather models disagree with each other today. "
              "Measured here: wide-spread days really do miss by more, so treat a wide tag as a "
              "reason for less conviction.</dd>"
              "<dt>Shift and width</dt><dd>Corrections the model learned from your own settled "
              "results. Shift shoves a city's forecast up or down; width sets how sure it is.</dd>"
              "<dt>CLV</dt><dd>Whether the market moved toward your position after you entered. "
              "Positive means you got a better price than the market later agreed on, which is "
              "the earliest honest sign of an edge, long before win-loss noise settles down.</dd>"
              "<dt>Edge and net</dt><dd>Edge is how far the model disagrees with the market price. "
              "Net is what survives after the spread and Kalshi's fee. Only net is real.</dd>"
              "<dt>ROI</dt><dd>Profit divided by the money actually put at risk, fees included.</dd>"
              "<dt>Unit (1u)</dt><dd>One bet-sized chunk of the bankroll. Sizes are 2u, 1.5u, 1u "
              "or no bet.</dd>"
              "<dt>Frozen play</dt><dd>Once a pick appears on a board it is scored forever as it "
              "was, even if a later run would have picked differently. The tracker always matches "
              "a board you actually saw.</dd>"
              "<dt>Gated / quarantined</dt><dd>A city sat out because its data came in degraded. "
              "It is still recorded so the sit-out can be judged later.</dd>"
              "</dl></details>")

def render_results(rep,updated,health=None,alerts=None):
    if not rep.get("plays"):
        body=('<div class="empty"><b>No resolved bets yet.</b> This tracker fills in automatically once your '
              'logged plays settle on Kalshi. Every run pulls Kalshi\'s official result and settled temperature, '
              'marks each bet win/loss, and updates the charts, per-city and per-unit tables, and margins below. '
              'Give it a couple weeks of morning runs.</div>')
        html=(head("results",updated,_health_strip(health,alerts))+"<h2 class='sec'>Results tracker</h2>"
              +body+GLOSSARY+"</div></body></html>")
        with open(os.path.join(OUT_DIR,"results.html"),"w",encoding="utf-8") as fp: fp.write(html); return
    def _kpi_row(q,ev):
        c="up" if q["net"]>=0 else "red"
        return (f"<div class='kpi'>"
          f"<div class='kbox'><div class='v {c}'>{q['net_units']:+.1f}u</div><div class='l'>net units</div></div>"
          f"<div class='kbox'><div class='v'>{q['winrate']*100:.0f}%</div><div class='l'>win rate ({q['wins']}/{q['n']})</div></div>"
          f"<div class='kbox'><div class='v {c}'>{q['roi']*100:+.1f}%</div><div class='l'>ROI</div></div>"
          f"<div class='kbox'><div class='v'>{q['avg_margin']:+.1f}\u00b0</div><div class='l'>avg margin</div></div>"
          f"<div class='kbox'><div class='v'>{ev}</div><div class='l'>events</div></div></div>")
    p=rep["pnl"]
    # ERA TOGGLE (display only). SCOPES drives EVERY play-derived block below:
    # current engine first because that is the strategy actually running, all
    # time one tap away. Class-based rather than id-based so any number of
    # blocks can follow the toggle without new wiring.
    CUR=rep.get("cur")
    SCOPES=[(CUR,False),(rep,True)] if CUR else [(rep,False)]
    def _era(html,hidden):
        if CUR is None: return html
        return (f"<div class='era-all' style='display:none'>{html}</div>" if hidden
                else f"<div class='era-cur'>{html}</div>")
    def _blocks(fn): return "".join(_era(fn(v),h) for v,h in SCOPES)
    toggle=""
    if CUR:
        toggle=("<div class='eratog'><button id='eb-cur' class='on' type='button'>Current engine</button>"
              "<button id='eb-all' type='button'>All time</button></div>"
              "<div class='eranote'>Current engine = plays frozen under the audit build (Jul 6 on). "
              "All time adds the retired pre-audit engine. EVERY play-derived box, chart and table on this page "
              "follows this toggle. The forecast tables further down (calibration, learned corrections, forecast "
              "sources, spread) describe the FORECASTER rather than the betting and always count the whole "
              "record, as do every gate and kill criterion.</div>"
              "<script>(function(){var c=document.getElementById('eb-cur'),a=document.getElementById('eb-all');"
              "function sw(cur){var i,A=document.querySelectorAll('.era-cur'),B=document.querySelectorAll('.era-all');"
              "for(i=0;i<A.length;i++){A[i].style.display=cur?'':'none';}"
              "for(i=0;i<B.length;i++){B[i].style.display=cur?'none':'';}"
              "c.className=cur?'on':'';a.className=cur?'':'on';}"
              "c.onclick=function(){sw(true)};a.onclick=function(){sw(false)};})();</script>")
    kpis=toggle+_blocks(lambda v:_kpi_row(v["pnl"],v["n_events"]))
    def _honest(v):
        cells=""
        if v.get("edge_stated") is not None:
            ec="up" if v["edge_real"]>=v["edge_stated"] else "red"
            cells+=(f"<div class='kbox'><div class='v'>{v['edge_stated']*100:+.1f}\u00a2</div><div class='l'>stated edge /contract ({v.get('edge_stated_n',0)} plays)</div></div>"
                    f"<div class='kbox'><div class='v {ec}'>{v['edge_real']*100:+.1f}\u00a2</div><div class='l'>realized /contract</div></div>")
        elif v.get("edge_real") is not None:
            cells+=(f"<div class='kbox'><div class='v dim'>pending</div><div class='l'>stated edge /contract (plays before 2026-07-28 lack it)</div></div>"
                    f"<div class='kbox'><div class='v'>{v['edge_real']*100:+.1f}\u00a2</div><div class='l'>realized /contract</div></div>")
        if v.get("roi_ci"):
            lo,hi,nd=v["roi_ci"]
            cells+=f"<div class='kbox'><div class='v'>{lo*100:+.0f}% .. {hi*100:+.0f}%</div><div class='l'>ROI 90% CI (block by day, {nd}d)</div></div>"
        if v.get("clv"):
            c=v["clv"]
            if c["live"]:
                cv="up" if c["avg"]>0 else "red"
                cells+=(f"<div class='kbox'><div class='v'>{c['beat']}/{c['n']}</div><div class='l'>beat the close</div></div>"
                        f"<div class='kbox'><div class='v {cv}'>{c['avg']*100:+.1f}\u00a2</div><div class='l'>avg CLV (edge shows here first)</div></div>")
            else:
                cells+=f"<div class='kbox'><div class='v dim'>{c['n']} logged</div><div class='l'>CLV pending multi-board settlements</div></div>"
        return ("<div class='kpi'>"+cells+"</div>") if cells else ""
    honest=_blocks(_honest)
    srct=""
    if rep.get("sources"):
        rowsS="".join(f"<tr><td>{esc(k)}</td><td class='n'>{mae:.2f}\u00b0</td><td class='n'>{n}</td></tr>"
                      for k,mae,n in rep["sources"])
        srct=("<h2 class='sec'>Forecast sources</h2>"
          "<div class='note'>Mean absolute error of each source's daily-extreme forecast against Kalshi settlements. "
          "NBM and HRRR are logged references that never touch pricing; promotion is decided here, on settled "
          "evidence (50+ rows per source), never on reputation. Raw model rows accrue only on records logged "
          "after the audit build deployed.</div>"
          "<table><thead><tr><th>Source</th><th class='n'>MAE</th><th class='n'>Settled</th></tr></thead><tbody>"+rowsS+"</tbody></table>")
    if rep.get("rain"):
        rn=rep["rain"]
        srct+=("<h2 class='sec'>Rain shadow (evidence only)</h2>"
          "<div class='note'>KXRAIN daily measurable-rain markets, logged and graded beside the temperature book "
          "on the same CLI settlement reports and stations. No rain play is ever generated; the FUTURE 5b gate "
          "decides whether this ever becomes more than evidence. Lower Brier is better.</div>")
        if rn["n"]:
            srct+=("<div class='kpi'>"
              f"<div class='kbox'><div class='v'>{rn['n']}</div><div class='l'>graded city-days</div></div>"
              f"<div class='kbox'><div class='v'>{rn['brier_pool']:.4f}</div><div class='l'>model Brier (pooled wet fraction)</div></div>"
              f"<div class='kbox'><div class='v'>{rn['brier_mkt']:.4f}</div><div class='l'>market Brier (mid)</div></div>"
              f"<div class='kbox'><div class='v'>{rn['wet_rate']*100:.0f}%</div><div class='l'>settled wet</div></div>"
              f"<div class='kbox'><div class='v'>{rn['pend']}</div><div class='l'>awaiting settlement</div></div></div>")
        else:
            srct+=("<div class='kpi'>"
              f"<div class='kbox'><div class='v dim'>{rn['pend']} logged</div>"
              "<div class='l'>city-days collected, first grades land after the next settlements</div></div></div>")
    def _chart(v):
        ttl=("cumulative units P&L, current engine" if (CUR and v is CUR)
             else "cumulative units P&L, all time (incl. retired engine)" if CUR
             else "cumulative units P&L")
        return "<div class='card'>"+svg_line(v.get("cum",[]),title=ttl,dates=v.get("cum_dates"))+"</div>"
    chart=_blocks(_chart)
    calsec=""
    if rep.get("calib_series"):
        cs=rep["calib_series"]
        c1=svg_multi([cs["raw"],cs["cor"],cs["mkt"]],
                     ["uncorrected model MAE","corrected model MAE","market-implied MAE"],
                     ["#8b97a6","#5ad1c8","#e2b34d"])
        note=("<div class='note'>Rolling 30-settlement mean absolute error of the daily-extreme forecast, in "
              "resolution order. The grey line is what the raw ensemble would have said; the teal line is what "
              "Nimbus actually said after per-city corrections. The gap between them is the calibration engine, "
              "visible. Corrections have touched <b>%d</b> of the settled records so far, so the lines separate "
              "from that point on: they will overlap over the pre-activation history, which is the honest "
              "baseline, not a bug. Amber is the market's own implied forecast (computable on new-format records "
              "only): the bar both lines have to clear.</div>"%cs["active"])
        disp=""
        if rep.get("disp_series"):
            d1=svg_multi([rep["disp_series"]],["rolling sd(z), 30-settlement window"],["#5ad1c8"],ref=1.0)
            disp=("<div class='card'>"+d1+"</div>"
              "<div class='note'>Spread honesty. z is the forecast miss divided by the stated uncertainty; a "
              "well-calibrated model keeps the rolling sd(z) near the dashed 1.0 line. Above 1.0 the model is "
              "overconfident (spreads too tight, tail bets poisoned); below it, underconfident (edges understated). "
              "This converging to 1.0 is the leading indicator that the probabilities, and therefore the stated "
              "edges, can be believed. It moves weeks before P&amp;L can.</div>")
        erat=""
        if rep.get("eras"):
            rowsE="".join(f"<tr><td>{esc(k)}</td><td class='n'>{n}</td><td class='n'>{w}/{n-w}</td>"
                          f"<td class='n'>{st:.1f}u</td><td class='n {'up' if pn>=0 else 'red'}'>{pn:+.1f}u</td></tr>"
                          for k,n,w,st,pn in rep["eras"])
            erat=("<h2 class='sec'>By model era</h2>"
              "<div class='note'>Every play is stamped with the model version that froze it, so old and new "
              "engines never blend. The audit-era row is the number that answers whether the rebuild worked; "
              "judge it only at the pre-registered checkpoints, not daily.</div>"
              "<table><thead><tr><th>Era</th><th class='n'>Plays</th><th class='n'>W/L</th>"
              "<th class='n'>Risked</th><th class='n'>Net</th></tr></thead><tbody>"+rowsE+"</tbody></table>")
            if rep.get("book_split"):
                bs=rep["book_split"]; c,e=bs["core"],bs["exp"]
                erat+=("<div class='note'>Within the audit era: <b>core book</b> (entries above 0.20, win prob above 30 percent) "
                  f"{c['w']}/{c['n']-c['w']} for <b>{c['net_u']:+.1f}u</b> on {c['stake_u']:.1f}u risked. "
                  f"<b>Experimental cheap-entry cell</b> (docket item 1, gate {e['n']}/40): {e['w']}/{e['n']-e['w']} for {e['net_u']:+.1f}u. "
                  "The cell keeps trading until its pre-registered gate reads; its cost is the price of a verdict that "
                  "cannot be argued with. If the gate condition holds, a MIN_ENTRY floor of 0.20 ships automatically.</div>")
            if rep.get("spread_skill"):
                ss=rep["spread_skill"]
                rowsS="".join(f"<tr><td>{esc(l)}</td><td class='n'>{c}</td><td class='n'>{e:.2f}&deg;</td></tr>"
                              for l,c,e in ss["bands"])
                erat+=("<h2 class='sec'>Forecast spread vs actual error</h2>"
                  f"<div class='note'>The spread the model reports is an honest confidence signal: "
                  f"correlation with realized error is <b>{ss['corr']:+.2f}</b> over {ss['n']} settlements "
                  "(pre-registered check, gate n=100). A wide-spread day really is a worse day, so the "
                  "bets page now tags each pick. This measures the SIZE of the miss, not direction, and "
                  "it is a tendency across many days rather than a promise about any single one.</div>"
                  "<table><thead><tr><th>Spread band</th><th class='n'>Events</th>"
                  "<th class='n'>Avg miss</th></tr></thead><tbody>"+rowsS+"</tbody></table>")
            if rep.get("prod_gate"):
                metn=sum(1 for _,m,_ in rep["prod_gate"] if m)
                items="".join(f"<div>{'MET &middot; ' if m else 'open &middot; '}{esc(lbl)}: {esc(det)}</div>"
                              for lbl,m,det in rep["prod_gate"])
                erat+=(f"<h2 class='sec'>Path to production</h2>"
                  f"<div class='note'>Manual-money gate, approved by owner 2026-07-16: <b>{metn}/6 conditions met</b>. "
                  "Real dollars start small only when all six hold at once; the kill legs can still stop everything later.</div>"
                  f"<div class='card'>{items}</div>")
        calsec=("<h2 class='sec'>Calibration engine</h2>"+note+"<div class='card'>"+c1+"</div>"+disp+erat)
    # time-windowed win rate row
    W=rep.get("windows",{})
    def _wk(lbl,d):
        if not d: return f"<div class='kbox'><div class='v dim'>-</div><div class='l'>{lbl}</div></div>"
        return f"<div class='kbox'><div class='v'>{d['wr']*100:.0f}%</div><div class='l'>{lbl} ({d['w']}/{d['n']})</div></div>"
    def _winrow(v):
        w=v.get("windows") or {}
        return ("<div class='kpi'>"+_wk("win% past day",w.get("day"))+_wk("win% past week",w.get("week"))
                +_wk("win% overall",w.get("all"))+"</div>")
    winrow=_blocks(_winrow)
    def _edgesec(v):
        rows="".join(f'<tr><td>{lab}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
                   f'<td class="n">{(w/n*100):.0f}%</td><td class="n {"up" if pn>=0 else "red"}">{pn/BASE_UNIT_USD:+.1f}u</td></tr>'
                   for lab,n,w,pn in v.get("by_edge",[]))
        return ("<table><thead><tr><th>Edge</th><th class='n'>Bets</th><th class='n'>W/L</th>"
                "<th class='n'>Win%</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+rows+"</tbody></table>")
    def _citysec(v):
        rows="".join(f'<tr><td>{esc(l)}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
                   f'<td class="n">{(w/n*100):.0f}%</td><td class="n {"up" if pn>=0 else "red"}">{pn/BASE_UNIT_USD:+.1f}u</td></tr>'
                   for l,n,w,pn in v.get("by_city",[]))
        return ("<div class='card'>"+svg_bars([(l,pn) for l,n,w,pn in v.get("by_city",[])])+"</div>"
                "<table><thead><tr><th>City</th><th class='n'>Bets</th><th class='n'>W/L</th>"
                "<th class='n'>Win%</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+rows+"</tbody></table>")
    def _unitsec(v):
        rows="".join(f'<tr><td>{unit_str(u)}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
                   f'<td class="n">{(w/n*100):.0f}%</td><td class="n {"up" if pn>=0 else "red"}">{pn/BASE_UNIT_USD:+.1f}u</td></tr>'
                   for u,n,w,pn in v.get("by_unit",[]))
        return ("<table><thead><tr><th>Size</th><th class='n'>Bets</th><th class='n'>W/L</th>"
                "<th class='n'>Win%</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+rows+"</tbody></table>")
    edgesec=_blocks(_edgesec); citysec=_blocks(_citysec); unitsec=_blocks(_unitsec)
    # brier
    brier=""
    if rep.get("brier_model") is not None:
        bm,bkk=rep["brier_model"],rep["brier_market"]; v="up" if bm<bkk else "red"
        brier=("<div class='kpi'>"
          f"<div class='kbox'><div class='v'>{bm:.3f}</div><div class='l'>Brier model</div></div>"
          f"<div class='kbox'><div class='v'>{bkk:.3f}</div><div class='l'>Brier market</div></div>"
          f"<div class='kbox'><div class='v {v}'>{(bkk-bm):+.3f}</div><div class='l'>edge (lower wins; benchmark is the FINAL pre-settlement board)</div></div></div>")
        if rep.get("rps_n"):
            rv="up" if rep["rps_model"]<rep["rps_market"] else "red"
            brier+=("<div class='kpi'>"
              f"<div class='kbox'><div class='v'>{rep['rps_model']:.3f}</div><div class='l'>RPS model</div></div>"
              f"<div class='kbox'><div class='v'>{rep['rps_market']:.3f}</div><div class='l'>RPS market</div></div>"
              f"<div class='kbox'><div class='v {rv}'>{(rep['rps_market']-rep['rps_model']):+.3f}</div><div class='l'>RPS edge, n={rep['rps_n']} (distance-aware; the ladder headline. The benchmark is the final board, which folds in intraday obs the model does not ingest yet: red here is a sharpness gap vs a better-informed close, not miscalibration. Calibration health lives in the table below, sd(z), and the MAE chart; edge at ENTRY prices shows in CLV.)</div></div></div>")
        if rep.get("nowcast"):
            nw=rep["nowcast"]
            brier+=(f"<div class='note'>Nowcast shadow (same-day highs, FUTURE 5 gate = truncated wins CRPS and RPS at 30+ events): "
              f"n={nw['n']}, RPS truncated {nw['rps_t']:.3f} vs untruncated {nw['rps_u']:.3f}, "
              f"CRPS {nw['crps_t']:.2f} vs {nw['crps_u']:.2f}, truncated wins {nw['wins']}/{nw['n']}. "
              f"Plays stay on untruncated pricing until the gate passes.</div>")
        if rep.get("challenger_w"):
            ch=rep["challenger_w"]
            gate=("GATE MET, ships next session" if (ch["n_prosp"]>=150 and (ch["adv_prosp"] or 0)>0 and ch["ci_lo"]>0)
                  else ("RETIRED at gate" if (ch["n_prosp"]>=150 and (ch["adv_prosp"] or 0)<=0)
                  else f"gate {ch['n_prosp']}/150 prospective records"))
            ap="pending" if ch["adv_prosp"] is None else f"{ch['adv_prosp']:+.3f} deg"
            brier+=(f"<div class='note'>Challenger test line (docket item 4, skill-weighted providers, registered 2026-07-16): "
              f"full-sample advantage {ch['adv']:+.3f} deg MAE, 90 percent CI [{ch['ci_lo']:+.3f}, {ch['ci_hi']:+.3f}], n={ch['n']}; "
              f"prospective advantage {ap}. {gate}. Pricing is untouched until the gate holds; adoption is its own "
              f"single-knob version bump. The other live test lines: the nowcast shadow above and the cheap-entry cell in the era table.</div>")
    # raw
    # calibration curve: does an X% forecast happen X% of the time?
    caltab=""
    if rep.get("bins"):
        bt="".join(f'<tr><td>{int(lo*100)}-{int(lo*100)+10}%</td><td class="n">{n}</td>'
                   f'<td class="n">{fp*100:.0f}%</td><td class="n">{hr*100:.0f}%</td>'
                   f'<td class="n">{wlo*100:.0f}-{whi*100:.0f}%</td>'
                   f'<td class="n {"up" if wlo<=fp<=whi else "red"}">{(hr-fp)*100:+.0f}%</td></tr>'
                   for lo,n,fp,hr,wlo,whi in rep["bins"])
        caltab=("<h2 class='sec'>Calibration</h2>"
          "<div class='note'>Every ladder bucket ever logged, grouped by the model's stated probability. "
          "A calibrated model's actual column matches its forecast column. Rows are flagged red only when the stated "
          "probability falls OUTSIDE the 95% range of what actually happened (Wilson interval): with thin rows, "
          "a big-looking gap is usually just small-sample noise, and this column says which is which.</div>"
          "<table><thead><tr><th>Model prob</th><th class='n'>Buckets</th><th class='n'>Forecast</th>"
          "<th class='n'>Actual</th><th class='n'>95% range</th><th class='n'>Gap</th></tr></thead><tbody>"+bt+"</tbody></table>")
    # learned corrections currently applied
    lct=""
    if rep.get("calib"):
        rowsL="".join(f'<tr><td>{esc(l)}</td><td>{k.title()}</td><td class="n">{c:+.1f}\u00b0</td>'
                      f'<td class="n">{s:.1f}\u00b0</td><td class="n">{n}</td></tr>'
                      for l,k,c,s,n in rep["calib"])
        lct=("<h2 class='sec'>Learned corrections</h2>"
          "<div class='note'>Applied automatically before scoring, from each city's settled history: shift is the "
          "bias correction added to every ensemble member (shrunk when history is thin), width is the kernel "
          "dressing sigma (how much realized error exceeds raw ensemble spread). A persistent large shift usually "
          f"means the city's coordinates do not match Kalshi's settlement station. Pooled sigma: {rep.get('gsigma',DRESS_SIGMA_DEFAULT):.1f}\u00b0.</div>"
          "<table><thead><tr><th>City</th><th>Mkt</th><th class='n'>Shift</th><th class='n'>Width</th>"
          "<th class='n'>Settled</th></tr></thead><tbody>"+rowsL+"</tbody></table>")
    # by stated win probability: the go/no-go readout for betting only high-confidence cards
    def _pwsec(v):
        pr="".join(f'<tr><td>{lab}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
                   f'<td class="n">{ap*100:.0f}%</td><td class="n">{(w/n*100):.0f}%</td>'
                   f'<td class="n {"up" if pn>=0 else "red"}">{pn/BASE_UNIT_USD:+.1f}u</td>'
                   f'<td class="n {"up" if roi>=0 else "red"}">{roi*100:+.1f}%</td></tr>'
                   for lab,n,w,ap,pn,roi in v.get("by_pwin",[]))
        return ("<table><thead><tr><th>Stated</th><th class='n'>Bets</th><th class='n'>W/L</th><th class='n'>Avg stated</th>"
          "<th class='n'>Actual</th><th class='n'>P&amp;L</th><th class='n'>ROI</th></tr></thead><tbody>"+pr+"</tbody></table>")
    pwt=""
    if rep.get("by_pwin"):
        pwt=("<h2 class='sec'>By win probability</h2>"
          "<div class='note'>Each play grouped by the win probability the model stated when the bet was logged. "
          "Two things to check before betting only the high-confidence cards: does the actual column roughly match "
          "the stated column (calibration), and does the 80%+ row have positive ROI, not just a high win rate? "
          "High-probability plays win small and lose big, so a few points of overconfidence flips them negative "
          "while still feeling like winning.</div>"+_blocks(_pwsec))
    def _rawrows(v):
        return "".join(f'<tr><td>{esc(CITIES[r["code"]][3])}</td><td>{"H" if r["kind"]=="HIGH" else "L"} {r["target"][5:]}</td>'
                f'<td>{esc(r["sub"])}</td><td>{unit_str(r["units"])}</td><td class="pl">{r["side"]}@{r["entry"]*100:.0f}\u00a2</td>'
                f'<td class="n">{r["actual"]}\u00b0</td><td>{"WON" if r["won"] else "LOST"}</td>'
                f'<td class="n">{("%+.1f"%r["margin"]) if r["margin"] is not None else DOT}\u00b0</td>'
                f'<td class="n {"up" if r["pnl"]>=0 else "red"}">{r["pnl"]/BASE_UNIT_USD:+.1f}u</td></tr>'
                for r in v.get("recent",[])[:60])
    rawsec=_blocks(lambda v:("<table><thead><tr><th>City</th><th>Mkt</th><th>Bucket</th><th>Size</th><th>Bet</th>"
                             "<th class='n'>Actual</th><th>Result</th><th class='n'>Margin</th>"
                             "<th class='n'>P&amp;L</th></tr></thead><tbody>"+_rawrows(v)+"</tbody></table>"))
    html=(head("results",updated,_health_strip(health,alerts))+
      "<h2 class='sec'>Performance</h2>"+kpis+winrow+honest+chart+brier+calsec+GLOSSARY+
      "<h2 class='sec'>By city</h2>"+citysec+
      "<h2 class='sec'>By unit size</h2>"+unitsec+
      "<h2 class='sec'>By edge size</h2>"
      "<div class='note'>The calibration check that matters most: a bigger edge should win more often. "
      "If the 25%+ row wins less than the 8-15% row, those fat edges are the model being wrong, not free money.</div>"
      +edgesec+pwt+caltab+lct+srct+
      "<h2 class='sec'>Every resolved bet</h2>"+rawsec+
      "</div></body></html>")
    with open(os.path.join(OUT_DIR,"results.html"),"w",encoding="utf-8") as fp: fp.write(html)

# ------------------------------ main ------------------------------
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH,encoding="utf-8") as f: s=json.load(f)
        except Exception as e:
            # Never fall back to an empty state: on GitHub the workflow would
            # commit it and silently wipe the visible track record. Fail loudly;
            # a red run leaves the last good commit untouched.
            print("FATAL: weather_state.json is unreadable:",str(e)[:120])
            print("Refusing to start with a blank state. Restore weather_state.json from git history, then rerun.")
            sys.exit(3)
        if not (isinstance(s,dict) and isinstance(s.get("predictions"),dict) and isinstance(s.get("resolved"),list)):
            print("FATAL: weather_state.json schema is wrong (need a predictions dict and a resolved list).")
            print("Restore weather_state.json from git history, then rerun.")
            sys.exit(3)
        return s
    return {"predictions":{},"resolved":[]}

def save_state(s):
    tmp=STATE_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(s,f,indent=1,default=str)
    os.replace(tmp,STATE_PATH)

def load_archive():
    """Resolved records previously split out of the live state file, same shape
    as state["resolved"]. A MISSING archive is normal (nothing has split yet).
    An UNREADABLE one is fatal for the same reason a corrupt state file is:
    reporting would silently show a shorter track record than the one that
    exists, and a quietly truncated history is exactly the dishonesty the
    load_state guard was written to prevent."""
    if not os.path.exists(ARCHIVE_PATH): return []
    try:
        with open(ARCHIVE_PATH,encoding="utf-8") as f: a=json.load(f)
    except Exception as e:
        print("FATAL: weather_state_archive.json is unreadable:",str(e)[:120])
        print("Refusing to report on a partial track record. Restore it from git history, then rerun.")
        sys.exit(3)
    if not isinstance(a,list):
        print("FATAL: weather_state_archive.json schema is wrong (need a list of resolved records).")
        print("Restore it from git history, then rerun.")
        sys.exit(3)
    return a

def _rec_key(r): return (r.get("code"),r.get("kind"),r.get("target"))

def reporting_view(state):
    """Live state plus archived resolved records, for REPORTING ONLY.

    Never saved: save_state writes the live dict, so the split survives a run.
    Every gate in this project counts over the whole history (150 plays, 800
    buckets, 500 tail buckets), so reporting must see both halves or archiving
    would silently reset the counters the governance depends on.

    Dedupes by (code, kind, target): an interrupted split can leave a record in
    both files, and a duplicate would double-count in every aggregate."""
    arch=load_archive()
    if not arch: return state
    live=list(state.get("resolved",[]))
    seen={_rec_key(r) for r in live}
    return dict(state,resolved=[r for r in arch if _rec_key(r) not in seen]+live)

def archive_pass(state):
    """HANDOFF 7b, as amended 2026-07-28. Once the live file passes
    ARCHIVE_TRIGGER_MB, resolved records with a target older than
    ARCHIVE_KEEP_DAYS move into the archive file. The pricing path keeps
    reading the live file only, so calibration always learns from a bounded
    recent window; reporting reads both through reporting_view.

    Write order is deliberate and is the whole safety argument: the archive is
    written and replaced FIRST, and only then are those records dropped from
    the live dict. A crash in between leaves a record in BOTH files, which
    reporting_view dedupes and the next run re-splits cleanly. The opposite
    order could lose a settlement permanently, and the track record cannot be
    recreated at any price.

    Live and archived sets are complementary halves of one partition computed
    from a single predicate, so no record can fall between them."""
    try: size_mb=os.path.getsize(STATE_PATH)/1e6
    except OSError: return 0
    if size_mb<ARCHIVE_TRIGGER_MB: return 0
    cutoff=(TODAY-dt.timedelta(days=ARCHIVE_KEEP_DAYS)).isoformat()
    def old(r): return (r.get("target") or "9999-99-99")<cutoff
    movers=[r for r in state.get("resolved",[]) if old(r)]
    if not movers:
        print(f"  archive: live state {size_mb:.2f} MB is past the {ARCHIVE_TRIGGER_MB} MB trigger,"
              f" but no resolved record predates {cutoff} yet.")
        return 0
    arch=load_archive()
    seen={_rec_key(r) for r in arch}
    arch=arch+[r for r in movers if _rec_key(r) not in seen]
    tmp=ARCHIVE_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(arch,f,indent=1,default=str)
    os.replace(tmp,ARCHIVE_PATH)
    state["resolved"]=[r for r in state.get("resolved",[]) if not old(r)]
    print(f"  archive: moved {len(movers)} resolved records older than {cutoff}"
          f" into {os.path.basename(ARCHIVE_PATH)} ({len(arch)} archived in total)")
    return len(movers)

def notify_telegram(plays,health,alerts,rep):
    """Phone ping after each run (FUTURE item 4, shipped audit batch 10).
    Fires ONLY when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID exist in the
    environment (GitHub Actions secrets); otherwise a silent no-op. A
    notification failure must never fail the run."""
    tok=os.environ.get("TELEGRAM_BOT_TOKEN"); chat=os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat: return
    try:
        top=plays[0] if plays else None
        lines=["Nimbus "+dt.datetime.now(dt.timezone.utc).strftime("%b %d %H:%MZ"),
               f"{len(plays)} plays on the board, {health.get('new_24h',0)} new in 24h"]
        if top:
            lines.append(f"Top: {top['label']} {top['kind']} {top['bucket']} {top['side']} {top['units']}u @ {int(round(top['entry']*100))}c (p_win {int(round((top.get('p_win') or 0)*100))}%)")
        if rep.get("pnl"):
            p=rep["pnl"]; lines.append(f"Record {p['wins']}/{p['n']}  {p['net_units']:+.1f}u")
        if health.get("gated"): lines.append("Gated: "+", ".join(health["gated"][:3]))
        if alerts: lines.append("ALERT: "+alerts[0])
        url=os.environ.get("NIMBUS_PAGE_URL")
        if url: lines.append(url)
        body=json.dumps({"chat_id":chat,"text":chr(10).join(lines),"disable_web_page_preview":True}).encode()
        req=urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",data=body,
                                   headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=20) as r: r.read()
        print("Telegram: sent")
    except Exception as e:
        print("Telegram notify failed (non-fatal):",str(e)[:80])

def drift_alerts(state):
    """Display-only drift alarms (audit batch 7). These NEVER change behavior:
    they name a failure mode on the results header so the owner investigates
    before any knob moves. Auto-retuning beyond the existing bias/sigma
    learners stays forbidden; knob changes happen in owner sessions with a
    MODEL_VERSION bump (governance verdict, AUDIT_TODO section 11)."""
    al=[]
    res=[r for r in state.get("resolved",[]) if r.get("buckets") and not r.get("gated")]
    bk=[(b["mp"],b["hit"]) for r in res for b in r["buckets"] if b.get("mp") is not None]
    mk=[(b["mid"],b["hit"]) for r in res for b in r["buckets"] if b.get("mid") is not None]
    if len(bk)>=180 and len(mk)>=180:
        bm=lambda xs: sum((p-h)**2 for p,h in xs)/len(xs)
        gap_all=bm(bk)-bm(mk); gap_rec=bm(bk[-120:])-bm(mk[-120:])
        if gap_rec-gap_all>0.05:
            al.append("drift: recent Brier gap to market widened %+.2f"%(gap_rec-gap_all))
    bins=defaultdict(lambda:[0,0])
    for p,h in bk:
        i=min(9,int(p*10)); bins[i][0]+=1; bins[i][1]+=h
    for i in sorted(bins):
        n,k=bins[i]
        if n>=25 and abs(k/n-(i+0.5)/10)>0.20:
            al.append("calibration: %d-%d%% bin realizing %.0f%% (n=%d)"%(i*10,(i+1)*10,100*k/n,n))
    zs=[r["bias"]/r["psd"] for r in res[-60:] if r.get("bias") is not None and r.get("psd")]
    if len(zs)>=40:
        m=sum(zs)/len(zs); sdz=math.sqrt(sum((z-m)**2 for z in zs)/len(zs))
        if sdz>1.4: al.append("dispersion: sd(z)=%.2f, spreads too tight (overconfident)"%sdz)
        elif sdz<0.7: al.append("dispersion: sd(z)=%.2f, spreads too wide (underconfident)"%sdz)
    cal=calib_params(state); snap=state.get("calib_snapshot") or {}
    newsnap={}
    for k,v in cal.items():
        if isinstance(k,tuple):
            kk="%s|%s"%k; newsnap[kk]=round(v.get("corr",0.0),2)
            if kk in snap and v.get("n",0)>=8 and abs(newsnap[kk]-snap[kk])>1.0:
                al.append("correction jump: %s moved %+.1f -> %+.1f"%(kk,snap[kk],newsnap[kk]))
    state["calib_snapshot"]=newsnap
    return al

def main():
    os.makedirs(OUT_DIR,exist_ok=True)
    print("="*56); print("Nimbus  -",dt.datetime.now().strftime("%Y-%m-%d %H:%M")); print("="*56)
    state=load_state()
    if os.environ.get("NIMBUS_SHADOW_RUN")=="1":
        # Midday SHADOW run (checkpoint 1 build, FUTURE 5 stage 1): collect
        # paired nowcast snapshots and stop. No resolving, no board refresh,
        # no plays, no render, no Telegram: trading behavior and every
        # existing measurement (final-snapshot semantics, CLV close) are
        # untouched. Worst case this pass fails and nothing else notices.
        shadow_pass(state); save_state(state)
        print("\nShadow run complete."); return
    resolve_pending(state)
    shadow_pass(state)   # normal runs also collect when a city sits in the window (eastern cities hit it on the morning cron)
    # Rain evidence shadow (FUTURE 5b): fully isolated and non-fatal. A rain
    # failure of any kind must never cost a temperature board. Skipped on the
    # shadow-only run above to keep that run's semantics byte-clean.
    try:
        rain_resolve(state)
        rain_pass(state,dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
    except Exception as e:
        print("Rain shadow skipped:",str(e)[:90])
    rows,plays,health=score(state)
    # drift_alerts deliberately stays on the LIVE state: its four alarms are all
    # recent-window instruments, it writes calib_snapshot back into the state it
    # is handed, and its A4 leg reads the same live-only calibration production
    # prices from. After a split its A1 baseline becomes "recent vs the retained
    # window" rather than "recent vs all time", which is the more honest
    # comparison for a drift alarm anyway.
    alerts=drift_alerts(state)
    archive_pass(state)
    # Reporting reads live PLUS archive, so every pre-registered gate keeps
    # counting over the whole track record after a split.
    rep=compute_report(reporting_view(state))
    save_state(state)
    updated=dt.datetime.now().astimezone().strftime("%b %d %Y, %I:%M %p %Z")
    try:
        health["state_kb"]=os.path.getsize(STATE_PATH)//1024
        health["resolved_n"]=len(state.get("resolved",[]))
        if os.path.exists(ARCHIVE_PATH):
            health["archived_n"]=len(load_archive())
    except OSError: pass
    render_bets(rows,plays,updated,health); render_results(rep,updated,health,alerts)
    notify_telegram(plays,health,alerts,rep)
    print(f"\nPlays today: {len(plays)} | resolved: {rep.get('n_events',0)}")
    if rep.get("pnl"): print(f"Paper P&L: {rep['pnl']['net_units']:+.1f}u ({rep['pnl']['wins']}/{rep['pnl']['n']})")
    print("Dashboards ->",OUT_DIR)
    if os.environ.get("CI")!="true":
        try: webbrowser.open("file://"+os.path.join(OUT_DIR,"index.html"))
        except Exception: pass

if __name__=="__main__":
    try: main()
    except Exception as e:
        import traceback; traceback.print_exc(); print("ERROR:",e)
        # On GitHub a swallowed crash exits 0, the commit step runs, and a broken
        # run publishes as if it were healthy. Red runs are the honest signal.
        if os.environ.get("CI")=="true": sys.exit(1)
    if os.environ.get("CI")!="true" and sys.stdin.isatty():
        try: input("\nPress Enter to close...")
        except EOFError: pass
