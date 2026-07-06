"""Nimbus self-test suite (audit batch 12).

Consolidates every assertion the audit proved by hand into a committed,
network-free harness that CI runs BEFORE every board generation. If any test
fails, the workflow goes red and nothing publishes. Zero network: every
fetcher is monkeypatched; anything that slips through raises loudly.

Run: python test_nimbus.py        (stdlib unittest only, ~2 seconds)
"""
import unittest, os, sys, json, math, tempfile, datetime as dtm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kalshi_weather as kw


def _no_network(*a, **k):
    raise AssertionError("network call escaped the test harness")


class TestMath(unittest.TestCase):
    def test_wilson(self):
        lo, hi = kw._wilson(7, 10)
        self.assertTrue(0.39 < lo < 0.42 and 0.88 < hi < 0.92)

    def test_fee_rate_exact(self):
        self.assertAlmostEqual(kw.fee(0.5), 0.0175, places=6)
        self.assertAlmostEqual(kw.fee(0.3), 0.07 * 0.3 * 0.7, places=6)

    def test_round_nws_half_up(self):
        self.assertEqual(kw.round_nws(60.5), 61)
        self.assertEqual(kw.round_nws(60.49), 60)
        self.assertEqual(kw.round_nws(60.1), 60)   # 60.1 settles as 60, not 61

    def test_crps_gauss_closed_form(self):
        # CRPS of N(0,1) at y=0 is 2*phi(0) - 1/sqrt(pi) = 0.23369
        self.assertAlmostEqual(kw._crps_gauss(0.0, 0.0, 1.0), 0.234, places=3)

    def test_ladder_contiguity(self):
        good = [("less", None, 90), ("between", 90, 91), ("between", 92, 93), ("greater", 93, None)]
        gap = [("less", None, 90), ("between", 90, 91), ("between", 93, 94), ("greater", 94, None)]
        self.assertTrue(kw._ladder_contiguous(good))
        self.assertFalse(kw._ladder_contiguous(gap))


class TestCalibration(unittest.TestCase):
    def _rec(self, bias, corr=0.0, gated=None, tgt="2026-07-01"):
        r = {"code": "DAL", "kind": "HIGH", "target": tgt, "bias": bias,
             "bias_corr": corr, "sd": 1.0, "sigma": 1.1}
        if gated: r["gated"] = gated
        return r

    def test_sign_and_shrinkage(self):
        # six settlements with raw bias +3 and no applied correction:
        # corr must approach -3 * 6/(6+5) = -1.636 (the batch 3 fix)
        st = {"resolved": [self._rec(3.0, tgt=f"2026-07-0{i+1}") for i in range(6)], "predictions": {}}
        corr = kw.calib_params(st)[("DAL", "HIGH")]["corr"]
        self.assertTrue(-1.75 < corr < -1.50, corr)

    def test_reconstruction_uses_minus(self):
        # stored bias = raw + corr; with corr=-2 applied and raw=+3, stored=+1.
        # Correct reconstruction recovers +3; the pre-audit "+corr" bug got -1.
        st = {"resolved": [self._rec(1.0, corr=-2.0, tgt=f"2026-07-0{i+1}") for i in range(6)], "predictions": {}}
        corr = kw.calib_params(st)[("DAL", "HIGH")]["corr"]
        self.assertTrue(corr < -1.5, corr)   # learning toward -3*shrink, not toward +1*shrink

    def test_quarantine_excluded_from_learning(self):
        st = {"resolved": [self._rec(3.0, tgt=f"2026-07-0{i+1}") for i in range(6)]
              + [self._rec(50.0, gated="ladder structure", tgt="2026-07-09")], "predictions": {}}
        corr = kw.calib_params(st)[("DAL", "HIGH")]["corr"]
        self.assertTrue(-1.75 < corr < -1.50, corr)


class TestReport(unittest.TestCase):
    def _ev(self, mps, hit_idx, tgt, pnl, won, clv):
        return {"code": "DAL", "kind": "HIGH", "target": tgt, "lead": 1, "actual": 91,
                "mean": 90.4, "bias": -0.6, "sd": 1, "psd": 1.5, "bias_corr": 0, "sigma": 1.1,
                "members_by_model": {"gfs025": {"n": 31, "mean": 90.0, "sd": 1.0}},
                "ref": {"nbm": 91.2, "hrrr": 90.1},
                "buckets": [{"mp": m, "mid": 0.2, "hit": 1 if i == hit_idx else 0, "rep": 88.5 + i}
                            for i, m in enumerate(mps)],
                "plays": [{"code": "DAL", "kind": "HIGH", "target": tgt, "sub": "x", "side": "Buy YES",
                           "entry": 0.5, "tier": "B", "units": 1.0, "stake": 10.0, "contracts": 20,
                           "won": won, "pnl": pnl, "margin": 1.0, "actual": 91, "mp": 0.55, "mid": 0.5,
                           "edge": 0.06, "net": 0.05, "lead": 1, "close_mid": 0.5 + (clv or 0),
                           "clv": clv, "model_version": "t"}]}

    def _state(self):
        flat = [0.05, 0.10, 0.70, 0.10, 0.05]
        return {"resolved": [self._ev(flat, 2, f"2026-07-0{i+1}", 3.0 if i % 2 else -8.0,
                                      bool(i % 2), 0.04 if i % 2 else -0.02) for i in range(4)],
                "predictions": {}}

    def test_rps_distance_awareness(self):
        flat = [0.2] * 5
        base = self._state()
        right = dict(base); right["resolved"] = [self._ev([0.05, 0.10, 0.70, 0.10, 0.05], 2, "2026-07-01", 1, True, 0)]
        by2 = dict(base); by2["resolved"] = [self._ev([0.70, 0.10, 0.05, 0.10, 0.05], 2, "2026-07-01", 1, True, 0)]
        by1 = dict(base); by1["resolved"] = [self._ev([0.05, 0.70, 0.10, 0.10, 0.05], 2, "2026-07-01", 1, True, 0)]
        r_r, r_2, r_1 = (kw.compute_report(x) for x in (right, by2, by1))
        self.assertLess(r_r["rps_model"], r_r["rps_market"])
        self.assertGreater(r_2["rps_model"], r_2["rps_market"])
        self.assertLess(r_1["rps_model"], r_2["rps_model"])

    def test_honesty_and_bootstrap_determinism(self):
        rep1 = kw.compute_report(self._state()); rep2 = kw.compute_report(self._state())
        self.assertIn("edge_stated", rep1); self.assertIn("roi_ci", rep1)
        self.assertEqual(rep1["roi_ci"], rep2["roi_ci"])   # replay guarantee
        self.assertEqual(rep1["clv"]["n"], 4)
        self.assertTrue(any("NBM" in k for k, _, _ in rep1["sources"]))

    def test_calibration_series_and_eras(self):
        st = self._state()
        st["resolved"] = st["resolved"] * 3   # 12 rows clears the 8-row gate
        rep = kw.compute_report(st)
        cs = rep.get("calib_series")
        self.assertTrue(cs and len(cs["raw"]) == len(cs["cor"]) == len(cs["mkt"]))
        self.assertTrue(rep.get("disp_series") and len(rep["disp_series"]) == len(cs["raw"]))
        self.assertTrue(rep.get("eras") and rep["eras"][0][0].startswith(("Audit", "Legacy")))
        small = {"resolved": self._state()["resolved"][:2], "predictions": {}}
        self.assertNotIn("calib_series", kw.compute_report(small))

    def test_gated_records_never_enter_aggregates(self):
        st = self._state()
        st["resolved"].append({"code": "PHX", "kind": "HIGH", "target": "2026-07-09", "lead": 1,
                               "actual": 90, "mean": 95.0, "bias": 5.0, "sd": 1, "psd": 1.5,
                               "bias_corr": 0, "sigma": 1.1, "gated": "ladder structure",
                               "buckets": [{"mp": 0.5, "mid": 0.5, "hit": 1, "rep": 90.5}], "plays": []})
        rep = kw.compute_report(st)
        self.assertEqual(rep["n_events"], 4)


class TestPipeline(unittest.TestCase):
    """Gate, caps, freeze, and resolution: the batch 7-8 harnesses, committed."""

    def setUp(self):
        self._saved = (kw.pull_weather_markets, kw.fetch_members, kw.fetch_ref,
                       kw.fetch_run_meta, kw.fetch_settled_event, kw.fget)
        kw.fget = _no_network
        self.tom = (dtm.datetime.now(dtm.timezone.utc) + dtm.timedelta(days=1)).date()
        self.day = self.tom.isoformat()

    def tearDown(self):
        (kw.pull_weather_markets, kw.fetch_members, kw.fetch_ref,
         kw.fetch_run_meta, kw.fetch_settled_event, kw.fget) = self._saved

    def _bkt(self, t, f, c, st, yb, ya):
        return {"ticker": t, "floor": f, "cap": c, "stype": st, "sub": "", "yb": yb, "ya": ya, "oi": 900}

    def _lad(self, code, ok=True):
        return {"code": code, "kind": "HIGH", "date": self.tom, "event_ticker": "E" + code,
                "structure_ok": ok, "buckets": [
                    self._bkt(code + "L", None, 90, "less", 0.12, 0.14),
                    self._bkt(code + "B1", 90, 91, "between", 0.26, 0.28),
                    self._bkt(code + "B2", 92, 93, "between", 0.36, 0.38),
                    self._bkt(code + "G", 93, None, "greater", 0.22, 0.24)]}

    def _fm(self, lat, lon, tz):
        d = self.day
        pm = {m: {"hi": {d: [90.6 + j * 0.052 for j in range(35)]}, "lo": {d: [70.0] * 35}}
              for j, m in enumerate(kw.ENSEMBLE_MODELS)}
        hi = [v for m in pm.values() for v in m["hi"][d]]
        return {d: hi}, {d: [70.0] * 140}, -18000, pm

    def _wire(self, lads, fm=None):
        kw.pull_weather_markets = lambda: lads
        kw.fetch_members = fm or self._fm
        kw.fetch_ref = lambda *a: {}
        kw.fetch_run_meta = lambda: {}

    def test_gate_caps_freeze(self):
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy] + [self._lad("PHX", ok=False)])
        state = {"predictions": {}, "resolved": []}
        rows, plays, health = kw.score(state)
        per_day = {}
        per_ev = {}
        for p in plays:
            per_day[p["date"]] = per_day.get(p["date"], 0) + p["units"]
            per_ev[p["code"]] = per_ev.get(p["code"], 0) + p["units"]
        self.assertTrue(plays and health["capped"] > 0)
        self.assertTrue(all(v <= kw.DAILY_UNIT_CAP + 1e-9 for v in per_day.values()))
        self.assertTrue(all(v <= kw.EVENT_UNIT_CAP + 1e-9 for v in per_ev.values()))
        phx = state["predictions"][f"PHX|HIGH|{self.day}"]
        self.assertEqual(phx.get("gated"), "ladder structure"); self.assertEqual(phx["plays"], [])
        logged = sum(len(v["plays"]) for v in state["predictions"].values() if not v.get("gated"))
        self.assertEqual(logged, len(plays))
        self.assertTrue(all(v.get("cfg") == kw.CONFIG_HASH for v in state["predictions"].values()))
        # degraded rerun (same minute) must not touch DAL's frozen plays
        before = json.loads(json.dumps(state["predictions"][f"DAL|HIGH|{self.day}"]))
        def fm2(lat, lon, tz):
            if abs(lat - 32.8975) < .01:
                d = self.day
                return {d: [91.0] * 40}, {d: [70.0] * 40}, -18000, \
                       {"gfs025": {"hi": {d: [91.0] * 40}, "lo": {d: [70] * 40}}}
            return self._fm(lat, lon, tz)
        kw.fetch_members = fm2
        kw.score(state)
        dal = state["predictions"][f"DAL|HIGH|{self.day}"]
        self.assertEqual(dal["plays"], before["plays"])
        self.assertEqual(dal.get("plays_logged_at"), before.get("plays_logged_at"))
        self.assertIsNone(dal.get("gated"))

    def test_caps_count_previously_frozen_units(self):
        # Deploy-day regression: a target already holding frozen units (from an
        # earlier run or an inherited legacy board) must consume the daily and
        # event budgets, so later runs cannot rotate fresh units past the caps.
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        state = {"predictions": {f"ZZZ|HIGH|{self.day}": {
            "code": "ZZZ", "kind": "HIGH", "target": self.day, "event_ticker": "EZ",
            "logged_at": "2026-07-06T15:31", "lead": 1, "mean": 90.0, "sd": 1, "psd": 1.4,
            "bias_corr": 0, "sigma": 1.1, "model_version": "legacy", "biased": False,
            "offset": -18000, "buckets": [], "plays_lead": 1,
            "plays_logged_at": "2026-07-06T15:31", "plays_model_version": "legacy",
            "plays": [{"ticker": "ZA", "bid": "x", "sub": "x", "side": "Buy YES",
                       "entry": 0.5, "net": 0.05, "edge": 0.06, "tier": "A",
                       "units": 5.5, "stake": 55.0, "p_win": 0.6, "mp": 0.55, "mid": 0.5}]}},
            "resolved": []}
        rows, plays, health = kw.score(state)
        new_units = sum(p["units"] for p in plays)
        self.assertLessEqual(new_units, kw.DAILY_UNIT_CAP - 5.5 + 1e-9)
        legacy = state["predictions"][f"ZZZ|HIGH|{self.day}"]
        self.assertEqual(len(legacy["plays"]), 1)   # inherited history untouched
        total_frozen = sum(pl["units"] for v in state["predictions"].values()
                           for pl in v.get("plays", []) if v["target"] == self.day)
        self.assertLessEqual(total_frozen, kw.DAILY_UNIT_CAP + 1e-9)

    def test_resolution_fee_and_clv(self):
        state = {"predictions": {"DAL|HIGH|2026-07-01": {
            "code": "DAL", "kind": "HIGH", "target": "2026-07-01", "event_ticker": "EVT",
            "logged_at": "x", "lead": 1, "plays_lead": 1, "mean": 95.2, "sd": 1.4, "psd": 1.8,
            "bias_corr": 0.0, "sigma": 1.1, "model_version": "t", "cfg": "deadbeef",
            "buckets": [
                {"ticker": "A", "bid": "94-95", "sub": "94-95", "floor": 94, "cap": 95,
                 "stype": "between", "mp": 0.42, "mid": 0.40, "yb": 0.38, "ya": 0.42, "oi": 500},
                {"ticker": "B", "bid": "96+", "sub": "96+", "floor": 96, "cap": None,
                 "stype": "greater", "mp": 0.20, "mid": 0.30, "yb": 0.28, "ya": 0.32, "oi": 500}],
            "plays": [{"ticker": "A", "bid": "94-95", "sub": "94-95", "side": "Buy YES",
                       "entry": 0.42, "net": 0.05, "edge": 0.06, "tier": "A", "units": 1.5,
                       "stake": 15.0, "p_win": 0.42, "mp": 0.42, "mid": 0.34}]}},
            "resolved": []}
        kw.fetch_settled_event = lambda evt: {"A": ("yes", 95.0), "B": ("no", 95.0)}
        kw.TODAY = dtm.date(2026, 7, 5)
        kw.resolve_pending(state)
        r = state["resolved"][0]; pl = r["plays"][0]
        contracts = int(15.0 // 0.42)
        fee = math.ceil(0.07 * contracts * 0.42 * 0.58 * 100) / 100
        self.assertEqual(pl["pnl"], round(contracts * (1 - 0.42) - fee, 2))
        self.assertEqual(pl["clv"], 0.06); self.assertEqual(pl["close_mid"], 0.40)
        self.assertEqual(r.get("cfg"), "deadbeef")
        self.assertIsNotNone(r.get("crps"))


class TestState(unittest.TestCase):
    def test_load_state_refuses_bad_files(self):
        # STATE_PATH is module-relative (absolute); it MUST be monkeypatched to a
        # tempdir here, never written where it points: in CI that is the real
        # state file, and this very suite caught its own first draft doing so.
        saved = kw.STATE_PATH
        with tempfile.TemporaryDirectory() as td:
            kw.STATE_PATH = os.path.join(td, "weather_state.json")
            try:
                self.assertEqual(kw.load_state(), {"predictions": {}, "resolved": []})
                with open(kw.STATE_PATH, "w") as f: f.write("{ corrupt")
                with self.assertRaises(SystemExit): kw.load_state()
                with open(kw.STATE_PATH, "w") as f: json.dump({"predictions": []}, f)
                with self.assertRaises(SystemExit): kw.load_state()
            finally:
                kw.STATE_PATH = saved


if __name__ == "__main__":
    unittest.main(verbosity=1)
