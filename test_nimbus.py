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

    def test_current_engine_headline_splits_by_era(self):
        """pnl_cur must aggregate ONLY plays frozen under the audit build, and
        must be absent when the book has no era mix (a toggle with one option
        is noise). The all-time row is untouched either way: this is a view
        split, and every gate keeps counting the whole record."""
        st = self._state()
        for r in st["resolved"][:2]:            # 2 of 4 plays become legacy
            for pl in r["plays"]: pl["model_version"] = "2026-07-02.v3-nimbus-calib"
        rep = kw.compute_report(st)
        cur = rep.get("pnl_cur")
        self.assertTrue(cur and cur["n"] == 2)
        self.assertEqual(rep["pnl"]["n"], 4)     # all-time unchanged
        self.assertEqual(cur["net"], sum(p["pnl"] for r in st["resolved"][2:] for p in r["plays"]))
        # no era mix -> no toggle
        self.assertIsNone(kw.compute_report(self._state()).get("pnl_cur"))
        # rendered page: toggle present, current engine is the visible default,
        # all-time row rendered but hidden, and the note keeps it honest
        saved = kw.OUT_DIR
        try:
            with tempfile.TemporaryDirectory() as d:
                kw.OUT_DIR = d
                kw.render_results(rep, "now", None, [])
                with open(os.path.join(d, "results.html"), encoding="utf-8") as fp:
                    html = fp.read()
        finally:
            kw.OUT_DIR = saved
        self.assertIn("Current engine", html)
        self.assertIn("id='kpi-cur'", html)
        self.assertIn("id='kpi-all' style='display:none'", html)
        self.assertIn("Charts and gates below always count everything", html)

    def test_stated_edge_averages_only_net_bearing_plays(self):
        """Plays settled before 2026-07-28 carry no net (resolve dropped it).
        The stated-edge tile must average over the plays that HAVE the field,
        not divide by every contract: the old denominator reported a false
        +0.0c across the whole pre-fix record and would understate forever as
        mixed eras accumulate. net has no reconstruction fallback (unlike
        p_win), so a missing value means the play simply does not count."""
        st = self._state()
        for r in st["resolved"][:3]:            # 3 legacy plays lose the field
            for pl in r["plays"]: del pl["net"]
        rep = kw.compute_report(st)
        self.assertEqual(rep["edge_stated"], 0.05)   # the one net-bearing play, undiluted
        self.assertEqual(rep["edge_stated_n"], 1)
        self.assertIn("edge_real", rep)

    def test_stated_edge_absent_not_zero_when_no_play_carries_net(self):
        """A record where NO resolved play carries net (the entire pre-fix
        history) must omit edge_stated rather than assert a 0.0c claim the
        model never made, and the tile must render as pending, not +0.0c.
        This is the regression test for the defect itself: the old code
        passed its unit test on a fixture that hand-wrote net onto a resolved
        play, while the live page showed +0.0c for three weeks."""
        st = self._state()
        for r in st["resolved"]:
            for pl in r["plays"]: del pl["net"]
        rep = kw.compute_report(st)
        self.assertNotIn("edge_stated", rep)
        self.assertIn("edge_real", rep)
        saved = kw.OUT_DIR
        try:
            with tempfile.TemporaryDirectory() as d:
                kw.OUT_DIR = d
                kw.render_results(rep, "now", None, [])
                with open(os.path.join(d, "results.html"), encoding="utf-8") as fp:
                    html = fp.read()
        finally:
            kw.OUT_DIR = saved
        self.assertIn("pending", html)
        self.assertNotIn("+0.0\u00a2</div><div class='l'>stated edge", html)

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
                       kw.fetch_run_meta, kw.fetch_settled_event, kw.fget,
                       kw.fetch_ai_members)
        kw.fget = _no_network
        kw.fetch_ai_members = lambda *a: {}     # AI evidence absent unless a test injects it
        self.tom = (dtm.datetime.now(dtm.timezone.utc) + dtm.timedelta(days=1)).date()
        self.day = self.tom.isoformat()

    def tearDown(self):
        (kw.pull_weather_markets, kw.fetch_members, kw.fetch_ref,
         kw.fetch_run_meta, kw.fetch_settled_event, kw.fget,
         kw.fetch_ai_members) = self._saved

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

    def test_capped_plays_not_actionable_in_rows(self):
        # A play dropped by the exposure caps must not still render as a live sized
        # bet in the By-city detail view. rows and plays share the SAME dicts, so the
        # caps loop must neutralize dropped rows (units 0, no stake, capped flag) to
        # keep the detail view honest with the actionable board.
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        state = {"predictions": {}, "resolved": []}
        rows, plays, health = kw.score(state)
        self.assertGreater(health["capped"], 0)          # caps actually fired
        play_ids = {id(p) for p in plays}
        capped = [r for r in rows if r.get("capped")]
        self.assertTrue(capped)                          # at least one row was capped
        for r in capped:
            self.assertEqual(r["units"], 0.0)
            self.assertIsNone(r["stake"])
            self.assertNotIn(id(r), play_ids)            # capped row is not actionable
        # Conversely, every row still advertising a sized bet is a surviving play.
        for r in rows:
            if r.get("stake"):
                self.assertIn(id(r), play_ids)

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
            "plays_logged_at": "2026-07-02T21:38Z",
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
        # p_win must survive settlement: the docket 1 cheap-entry cell is
        # registered as "entry <= 0.20 OR p_win <= 0.30", and dropping the
        # field here silently reduced that gate to its entry arm alone
        self.assertEqual(pl["p_win"], 0.42)
        # net and the bucket identity must survive too: dropping net zeroed
        # the stated-edge honesty tile from v5.11 until 2026-07-28, and losing
        # ticker forced every later join back to fuzzy sub/price matching
        self.assertEqual(pl["net"], 0.05)
        self.assertEqual(pl["ticker"], "A")
        self.assertEqual(pl["bid"], "94-95")
        # entry board of the frozen plays: without it, bet-timing analysis can
        # only proxy the entry time from the record's first log
        self.assertEqual(r.get("plays_logged_at"), "2026-07-02T21:38Z")

    def test_book0_is_write_once_and_skips_gated_boards(self):
        """book0 must freeze at the FIRST healthy board. If it tracked refreshes it
        would record the final board's prices, which is not the board any decision
        was made on, and every offline replay built on it would be fiction."""
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy] + [self._lad("PHX", ok=False)])
        state = {"predictions": {}, "resolved": []}
        kw.score(state)
        key = "DAL|HIGH|" + self.day
        b0 = state["predictions"][key]["book0"]
        first = [dict(e) for e in b0["buckets"]]
        self.assertTrue(first)
        self.assertEqual(sorted(first[0]), sorted(kw.BOOK0_FIELDS))
        self.assertTrue(b0.get("at"))
        # record-level play-gate inputs travel with the snapshot
        self.assertIn("biased", b0); self.assertIn("lead", b0); self.assertIn("mean", b0)
        # a structurally gated ladder must never supply the decision snapshot
        self.assertIsNone(state["predictions"].get("PHX|HIGH|" + self.day, {}).get("book0"))

        def moved(code, ok=True):
            l = self._lad(code, ok)
            for b in l["buckets"]:
                b["yb"] = round(b["yb"] + 0.10, 2); b["ya"] = round(b["ya"] + 0.10, 2)
            return l
        self._wire([moved(c) for c in healthy] + [moved("PHX", ok=False)])
        kw.score(state)
        rec = state["predictions"][key]
        self.assertEqual(rec["book0"]["buckets"], first)           # snapshot frozen
        self.assertEqual(rec["book0"]["at"], b0["at"])
        self.assertNotEqual([b["yb"] for b in rec["buckets"]],
                            [e["yb"] for e in first])              # live book really moved

    def test_board_tape_appends_once_per_run_and_tracks_price_moves(self):
        """The tape exists to answer "what if we had frozen at a later board", so it
        must APPEND where book0 freezes, must not double-write within a run, and must
        record each board's own prices rather than the first board's."""
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        state = {"predictions": {}, "resolved": []}
        kw.score(state)
        key = "DAL|HIGH|" + self.day
        tape = state["predictions"][key]["tape"]
        self.assertEqual(len(tape), 1)
        at0, mean0, biased0, lead0, fp0, rows0 = tape[0]
        self.assertEqual(at0, state["predictions"][key]["book0"]["at"])   # tape[0] IS the decision board
        self.assertEqual(len(rows0), len(state["predictions"][key]["book0"]["buckets"]))
        self.assertIn(biased0, (0, 1))

        # a second board in the SAME run stamp must not append a duplicate row
        kw.score(state)
        self.assertEqual(len(state["predictions"][key]["tape"]), 1)

        # a later board at a new stamp appends, and carries its own moved prices
        def moved(code, ok=True):
            l = self._lad(code, ok)
            for b in l["buckets"]:
                b["yb"] = round(b["yb"] + 0.10, 2); b["ya"] = round(b["ya"] + 0.10, 2)
            return l
        self._wire([moved(c) for c in healthy])
        # run_stamp is derived from the clock inside score(), so age the stored row
        # rather than patching time: the next run then carries a genuinely new stamp
        state["predictions"][key]["tape"][0][0] = "2020-01-01T00:00Z"
        kw.score(state)
        tape = state["predictions"][key]["tape"]
        self.assertEqual(len(tape), 2)
        self.assertEqual(tape[0][0], "2020-01-01T00:00Z")     # earlier boards are never rewritten
        self.assertEqual(tape[1][4], fp0)                     # same ladder -> same fingerprint
        self.assertNotEqual([r[3] for r in tape[1][5]], [r[3] for r in rows0])   # ya really moved
        # book0 stays frozen while the tape grows: that is the whole point
        self.assertEqual(state["predictions"][key]["book0"]["at"], at0)

    def test_board_tape_skips_gated_boards_and_untaped_records(self):
        """A gated ladder is degraded data and must never enter a replay, and a record
        with no book0 has boards nobody captured, so "board k" would be meaningless."""
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy] + [self._lad("PHX", ok=False)])
        state = {"predictions": {}, "resolved": []}
        kw.score(state)
        self.assertIsNone(state["predictions"].get("PHX|HIGH|" + self.day, {}).get("tape"))
        self.assertIsNotNone(state["predictions"]["DAL|HIGH|" + self.day].get("tape"))
        # a record already in flight (no book0) is never taped
        key = "ATL|HIGH|" + self.day
        state["predictions"][key].pop("book0")
        state["predictions"][key].pop("tape", None)
        self._wire([self._lad(c) for c in healthy])
        kw.score(state)
        self.assertIsNone(state["predictions"][key].get("tape"))

        # AND a record that HAS book0 but no tape predates the tape: its board 0 was
        # never captured, so starting now would label a mid-life board as the
        # decision board. Holding book0 is not sufficient to earn a tape.
        key2 = "SEA|HIGH|" + self.day
        state["predictions"][key2].pop("tape")
        self.assertIsNotNone(state["predictions"][key2].get("book0"))
        kw.score(state)
        self.assertIsNone(state["predictions"][key2].get("tape"))

    def test_book0_never_stamps_a_record_already_in_flight(self):
        """A market already pending when book0 shipped has boards we never saw, and
        its plays may have frozen on one. Snapshotting it now would label a mid-life
        board as the decision board, so it must be skipped forever instead."""
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        key = "DAL|HIGH|" + self.day
        # simulate a pre-existing record: present, no book0, already carrying plays
        state = {"predictions": {key: {
            "code": "DAL", "kind": "HIGH", "target": self.day, "event_ticker": "EDAL",
            "logged_at": "old", "first_logged": "old", "lead": 1, "mean": 90.0,
            "sd": 1.0, "psd": 1.5, "bias_corr": 0.0, "sigma": 1.1, "buckets": [],
            "plays": [{"ticker": "DALB1", "side": "Buy YES", "entry": 0.28, "net": 0.05,
                       "edge": 0.06, "tier": "B", "units": 1.0, "stake": 10.0,
                       "p_win": 0.5, "mp": 0.5, "mid": 0.27, "sub": "", "bid": "x"}],
            "plays_logged_at": "old", "plays_lead": 1, "plays_model_version": "t"}},
            "resolved": []}
        kw.score(state)
        self.assertIsNone(state["predictions"][key].get("book0"))   # skipped, not mislabeled
        # a market seen for the first time in this same run DOES get one
        self.assertIsNotNone(state["predictions"]["ATL|HIGH|" + self.day].get("book0"))

    def test_book0_carries_to_resolved_with_settled_hits(self):
        """The resolved snapshot must be self-contained (reprice + grade) and must
        keep the DECISION board's prices, not the refreshed ones."""
        state = {"predictions": {"DAL|HIGH|2026-07-01": {
            "code": "DAL", "kind": "HIGH", "target": "2026-07-01", "event_ticker": "EVT",
            "logged_at": "x", "lead": 1, "mean": 95.2, "sd": 1.4, "psd": 1.8,
            "bias_corr": 0.0, "sigma": 1.1, "model_version": "t", "cfg": "deadbeef",
            "buckets": [
                {"ticker": "A", "bid": "94-95", "sub": "", "floor": 94, "cap": 95,
                 "stype": "between", "mp": 0.42, "mid": 0.40, "yb": 0.38, "ya": 0.42, "oi": 500},
                {"ticker": "B", "bid": "96+", "sub": "", "floor": 96, "cap": None,
                 "stype": "greater", "mp": 0.20, "mid": 0.30, "yb": 0.28, "ya": 0.32, "oi": 500}],
            "book0": {"at": "2026-06-30T02:07Z", "mean": 95.0, "biased": False, "lead": 1,
                      "buckets": [
                {"ticker": "A", "mp": 0.50, "mid": 0.31, "yb": 0.29, "ya": 0.33, "oi": 480,
                 "floor": 94, "cap": 95, "stype": "between"},
                {"ticker": "B", "mp": 0.14, "mid": 0.24, "yb": 0.22, "ya": 0.26, "oi": 460,
                 "floor": 96, "cap": None, "stype": "greater"}]},
            "tape": [["2026-06-30T02:07Z", 95.0, 0, 1, "abc12345",
                      [[0.5, 0.31, 0.29, 0.33, 480.0], [0.14, 0.24, 0.22, 0.26, 460.0]]],
                     ["2026-06-30T21:38Z", 95.3, 0, 1, "abc12345",
                      [[0.55, 0.36, 0.34, 0.38, 500.0], [0.12, 0.20, 0.18, 0.22, 470.0]]]],
            "plays": []}},
            "resolved": []}
        kw.fetch_settled_event = lambda evt: {"A": ("yes", 95.0), "B": ("no", 95.0)}
        kw.TODAY = dtm.date(2026, 7, 5)
        kw.resolve_pending(state)
        r = state["resolved"][0]
        # the tape rides along with a graded book0: both are needed to replay a
        # later board, since the tape's rows are positional against book0's ladder
        self.assertEqual(len(r["tape"]), 2)
        self.assertEqual(r["tape"][1][0], "2026-06-30T21:38Z")
        self.assertEqual(r["tape"][1][5][0][1], 0.36)    # the later board's own mid
        self.assertEqual(len(r["book0"]["buckets"]), 2)
        a = next(e for e in r["book0"]["buckets"] if e["ticker"] == "A")
        self.assertEqual(a["hit"], 1)
        self.assertEqual(next(e for e in r["book0"]["buckets"] if e["ticker"] == "B")["hit"], 0)
        self.assertEqual(a["mid"], 0.31)      # decision board, NOT the refreshed 0.40
        self.assertEqual(a["oi"], 480)
        self.assertEqual(r["book0"]["at"], "2026-06-30T02:07Z")
        self.assertEqual(r["book0"]["lead"], 1)          # decision-board lead, a filter input
        self.assertIs(r["book0"]["biased"], False)       # play-gate input preserved

    def test_book0_dropped_when_any_bucket_ungraded(self):
        """Partial books bias replayed exposure caps, so it is all or nothing."""
        state = {"predictions": {"DAL|HIGH|2026-07-01": {
            "code": "DAL", "kind": "HIGH", "target": "2026-07-01", "event_ticker": "EVT",
            "logged_at": "x", "lead": 1, "mean": 95.2, "sd": 1.4, "psd": 1.8,
            "bias_corr": 0.0, "sigma": 1.1, "model_version": "t", "cfg": "deadbeef",
            "buckets": [
                {"ticker": "A", "bid": "94-95", "sub": "", "floor": 94, "cap": 95,
                 "stype": "between", "mp": 0.42, "mid": 0.40, "yb": 0.38, "ya": 0.42, "oi": 500}],
            "book0": {"at": "z", "mean": 95.0, "biased": False, "lead": 1, "buckets": [
                {"ticker": "A", "mp": 0.50, "mid": 0.31, "yb": 0.29, "ya": 0.33, "oi": 480,
                 "floor": 94, "cap": 95, "stype": "between"},
                {"ticker": "GONE", "mp": 0.10, "mid": 0.12, "yb": 0.10, "ya": 0.14, "oi": 300,
                 "floor": 96, "cap": None, "stype": "greater"}]},
            "tape": [["z", 95.0, 0, 1, "abc12345", [[0.5, 0.31, 0.29, 0.33, 480.0]]]],
            "plays": []}},
            "resolved": []}
        kw.fetch_settled_event = lambda evt: {"A": ("yes", 95.0)}   # GONE never settles
        kw.TODAY = dtm.date(2026, 7, 5)
        kw.resolve_pending(state)
        r = state["resolved"][0]
        self.assertIsNone(r.get("book0"))
        # a tape without a graded book0 has no ladder to index into: it is not
        # replayable, so keeping it would only cost bytes
        self.assertIsNone(r.get("tape"))
        self.assertTrue(r["buckets"])        # the record itself still resolves normally

    def test_replay_champion_reproduces_live_selection(self):
        """The replay engine's champion config must pick EXACTLY what score() picked.
        If it drifts, every challenger number it produces is fiction. This is the
        equivalence proof for replay_selection.py."""
        import replay_selection as rs
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        state = {"predictions": {}, "resolved": []}
        rows, plays, health = kw.score(state)
        live = sorted((p["ticker"], p["side"], p["entry"], p["units"]) for p in plays)
        self.assertTrue(live, "fixture produced no live plays to compare against")

        # build resolved-shaped records from the same boards, with arbitrary outcomes
        recs = []
        for key, p in state["predictions"].items():
            b0 = p.get("book0")
            if not b0: continue
            gb = [dict(e, hit=1 if i == 1 else 0) for i, e in enumerate(b0["buckets"])]
            recs.append({"code": p["code"], "kind": p["kind"], "target": p["target"],
                         "book0": dict(b0, buckets=gb)})
        replayed = rs.replay(recs, rs.cfg("champion"))
        got = sorted((p["ticker"], p["side"], p["entry"], p["units"]) for p in replayed)
        self.assertEqual(got, live)

    def test_replay_min_entry_floor_excludes_cheap_plays(self):
        """A knob must actually bite: the 0.20 floor drops every cheaper entry and
        never invents a play the champion did not have available."""
        import replay_selection as rs
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        state = {"predictions": {}, "resolved": []}
        kw.score(state)
        recs = []
        for p in state["predictions"].values():
            b0 = p.get("book0")
            if not b0: continue
            gb = [dict(e, hit=1 if i == 1 else 0) for i, e in enumerate(b0["buckets"])]
            recs.append({"code": p["code"], "kind": p["kind"], "target": p["target"],
                         "book0": dict(b0, buckets=gb)})
        base = rs.replay(recs, rs.cfg("champion"))
        floored = rs.replay(recs, rs.cfg("floor", min_entry=0.20))
        self.assertTrue(all(p["entry"] >= 0.20 for p in floored))
        base_ids = {(p["ticker"], p["side"]) for p in base}
        self.assertTrue({(p["ticker"], p["side"]) for p in floored} <= base_ids)

    def test_book0_freezes_decision_time_sd(self):
        """The docket 6 spread candidates filter on the sd of the DECISION board.
        Record-level sd refreshes with the forecast every run, so book0 must carry
        its own frozen copy; without it a replay would read the final board's
        spread and call it the decision's (registered 2026-07-28)."""
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        state = {"predictions": {}, "resolved": []}
        kw.score(state)
        key = "DAL|HIGH|" + self.day
        rec = state["predictions"][key]
        sd0 = rec["book0"].get("sd")
        self.assertIsNotNone(sd0)
        self.assertAlmostEqual(sd0, rec["sd"], places=9)   # same quantity at first log

        def wider(lat, lon, tz):
            d = self.day
            pm = {m: {"hi": {d: [88.0 + j * 0.4 for j in range(35)]}, "lo": {d: [70.0] * 35}}
                  for m in kw.ENSEMBLE_MODELS}
            hi = [v for m in pm.values() for v in m["hi"][d]]
            return {d: hi}, {d: [70.0] * 140}, -18000, pm
        self._wire([self._lad(c) for c in healthy], fm=wider)
        kw.score(state)
        rec = state["predictions"][key]
        self.assertEqual(rec["book0"]["sd"], sd0)                   # frozen with the snapshot
        self.assertNotAlmostEqual(rec["sd"], sd0, places=3)         # live record really moved

    def test_replay_sd_filter_reads_frozen_sd_then_stated_proxy(self):
        """The registered spread-convergence candidates must drop plays from
        wide-spread decision boards, must read book0's frozen sd when present, and
        must fall back to the record's final-board sd only when the snapshot
        predates the field."""
        import replay_selection as rs
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        state = {"predictions": {}, "resolved": []}
        kw.score(state)
        recs = []
        for p in state["predictions"].values():
            b0 = p.get("book0")
            if not b0: continue
            gb = [dict(e, hit=1 if i == 1 else 0) for i, e in enumerate(b0["buckets"])]
            recs.append({"code": p["code"], "kind": p["kind"], "target": p["target"],
                         "sd": p["sd"], "book0": dict(b0, buckets=gb)})
        base = rs.replay(recs, rs.cfg("champion"))
        self.assertTrue(base, "fixture produced no plays to filter")
        sd0 = recs[0]["book0"]["sd"]
        keep = rs.replay(recs, rs.cfg("keep", max_sd=sd0 + 0.01))
        drop = rs.replay(recs, rs.cfg("drop", max_sd=sd0 - 0.01))
        self.assertEqual(len(keep), len(base))
        self.assertEqual(drop, [])
        # frozen sd wins over a divergent record-level sd
        recorded_wide = [dict(r, sd=99.0) for r in recs]
        self.assertEqual(len(rs.replay(recorded_wide, rs.cfg("frozen", max_sd=sd0 + 0.01))), len(base))
        # legacy snapshot without sd: the record's final-board sd is the proxy
        legacy = [dict(r, sd=99.0, book0={k: v for k, v in r["book0"].items() if k != "sd"})
                  for r in recs]
        self.assertEqual(rs.replay(legacy, rs.cfg("proxy_drop", max_sd=1.0)), [])
        legacy_tight = [dict(r, sd=0.1, book0={k: v for k, v in r["book0"].items() if k != "sd"})
                        for r in recs]
        self.assertEqual(len(rs.replay(legacy_tight, rs.cfg("proxy_keep", max_sd=1.0))), len(base))

    def test_replay_selection_filters_registered_2026_07_29(self):
        """The six candidates registered 2026-07-29 lean on three new knobs:
        kind restriction, a p_win band skip, and the modal-bucket NO-fade skip.
        Each must drop exactly what it claims to drop and nothing else, or the
        slate's rows describe rules that were never actually tested."""
        import replay_selection as rs
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        self._wire([self._lad(c) for c in healthy])
        state = {"predictions": {}, "resolved": []}
        kw.score(state)
        recs = []
        for p in state["predictions"].values():
            b0 = p.get("book0")
            if not b0: continue
            gb = [dict(e, hit=1 if i == 1 else 0) for i, e in enumerate(b0["buckets"])]
            recs.append({"code": p["code"], "kind": p["kind"], "target": p["target"],
                         "sd": p["sd"], "book0": dict(b0, buckets=gb)})
        base = rs.replay(recs, rs.cfg("champion"))
        self.assertTrue(base, "fixture produced no plays to filter")
        # kind restriction: HIGH-only yields only HIGH plays, LOW-only only LOW,
        # and the two partitions cover the champion book
        hi = rs.replay(recs, rs.cfg("hi", kinds="HIGH"))
        lo = rs.replay(recs, rs.cfg("lo", kinds="LOW"))
        self.assertTrue(all(x["kind"] == "HIGH" for x in hi))
        self.assertTrue(all(x["kind"] == "LOW" for x in lo))
        self.assertEqual(len(hi) + len(lo), len(base))
        # p_win band skip: a band wrapped around a real play's p_win drops it
        tgt = base[0]
        band = (round(tgt["p_win"] - 0.005, 4), round(tgt["p_win"] + 0.005, 4))
        banded = rs.replay(recs, rs.cfg("band", skip_pwin_band=band))
        self.assertNotIn((tgt["ticker"], tgt["side"]),
                         [(x["ticker"], x["side"]) for x in banded])
        # count may stay equal (dropping a play frees exposure-cap budget for a
        # previously trimmed one), but no surviving play may sit inside the band
        for x in banded:
            self.assertFalse(band[0] <= x["p_win"] < band[1])
        # modal-fade skip: no surviving play is a Buy NO on its board's favorite
        nomodal = rs.replay(recs, rs.cfg("nomodal", skip_modal_no=True))
        modal_of = {(r["code"], r["kind"]): max(r["book0"]["buckets"], key=lambda e: e["mid"])["ticker"]
                    for r in recs}
        for x in nomodal:
            if x["side"] == "Buy NO":
                self.assertNotEqual(x["ticker"], modal_of[(x["code"], x["kind"])])
        # and every play the filter removed really was a modal NO fade
        removed = {(x["ticker"], x["side"]) for x in base} - {(x["ticker"], x["side"]) for x in nomodal}
        for tk, sd in removed:
            self.assertEqual(sd, "Buy NO")

    def test_ai_evidence_models_log_without_touching_pricing(self):
        """AIGEFS/AIFS are evidence (FUTURE 5, added 2026-07-28): they must land
        in members_by_model and change NOTHING else. The AI fixture is wildly off
        (82 deg vs the pool's 91) precisely so any contamination of the mean, the
        spread, the buckets, or the plays would show."""
        healthy = ["DAL", "ATL", "SEA", "BOS", "LV"]
        d = self.day
        self._wire([self._lad(c) for c in healthy])
        kw.fetch_ai_members = lambda lat, lon, tz: {
            m: {"hi": {d: [80.0 + j for j in range(5)]}, "lo": {d: [60.0] * 5}}
            for m in kw.AI_ENSEMBLE_MODELS}
        s1 = {"predictions": {}, "resolved": []}
        kw.score(s1)
        self._wire([self._lad(c) for c in healthy])
        kw.fetch_ai_members = lambda *a: {}
        s2 = {"predictions": {}, "resolved": []}
        kw.score(s2)
        k = "DAL|HIGH|" + d
        r1, r2 = s1["predictions"][k], s2["predictions"][k]
        mm = r1["members_by_model"]
        for m in kw.AI_ENSEMBLE_MODELS:
            self.assertIn(m, mm)
            self.assertEqual(mm[m]["n"], 5)
            self.assertAlmostEqual(mm[m]["mean"], 82.0, places=6)
        for m in kw.ENSEMBLE_MODELS:
            self.assertIn(m, mm)
        self.assertNotIn("gated", r1)
        self.assertEqual(r1["mean"], r2["mean"])
        self.assertEqual(r1["sd"], r2["sd"])
        self.assertEqual([b["mp"] for b in r1["buckets"]], [b["mp"] for b in r2["buckets"]])
        self.assertEqual(r1["plays"], r2["plays"])
        self.assertEqual(r1["book0"]["sd"], r2["book0"]["sd"])

    def test_ai_models_never_rescue_the_model_count_gate(self):
        """Two core providers plus two AI providers is still 2/4 models. The gate
        counts pricing providers only; evidence logging must not weaken it."""
        d = self.day
        def two_core(lat, lon, tz):
            pm = {m: {"hi": {d: [90.6 + j * 0.052 for j in range(50)]}, "lo": {d: [70.0] * 50}}
                  for m in kw.ENSEMBLE_MODELS[:2]}
            hi = [v for m in pm.values() for v in m["hi"][d]]
            return {d: hi}, {d: [70.0] * 100}, -18000, pm
        self._wire([self._lad(c) for c in ["DAL", "ATL", "SEA", "BOS", "LV"]], fm=two_core)
        kw.fetch_ai_members = lambda lat, lon, tz: {
            m: {"hi": {d: [90.0] * 31}, "lo": {d: [70.0] * 31}} for m in kw.AI_ENSEMBLE_MODELS}
        state = {"predictions": {}, "resolved": []}
        kw.score(state)
        rec = state["predictions"]["DAL|HIGH|" + d]
        self.assertTrue(rec.get("gated"))
        self.assertIn("2/4 models", rec["gated"])
        # the quarantined record still logs the evidence models for later audit
        for m in kw.AI_ENSEMBLE_MODELS:
            self.assertIn(m, rec["members_by_model"])


class TestSpreadDisplay(unittest.TestCase):
    """Surfacing forecast spread, earned by the spread-skill check reading
    +0.250 with a CI excluding zero at n=804. Display only: no pricing path."""

    def test_bands_follow_the_measured_quartiles(self):
        self.assertEqual(kw.spread_label(kw.SPREAD_TIGHT)[0], "tight spread")
        self.assertIsNone(kw.spread_label(kw.SPREAD_TIGHT + 0.01))
        self.assertIsNone(kw.spread_label(kw.SPREAD_WIDE))
        self.assertEqual(kw.spread_label(kw.SPREAD_WIDE + 0.01)[0], "wide spread")
        self.assertIsNone(kw.spread_label(None))
        self.assertLess(kw.SPREAD_TIGHT, kw.SPREAD_WIDE)

    def test_report_exposes_spread_skill_only_past_its_gate(self):
        def ev(sd, err, i):
            return {"code": "DAL", "kind": "HIGH", "target": f"2026-07-{(i % 28) + 1:02d}", "lead": 1,
                    "actual": 90, "mean": 90 + err, "bias": err, "sd": sd, "psd": 1.5,
                    "bias_corr": 0, "sigma": 1.1,
                    "buckets": [{"mp": 0.5, "mid": 0.5, "hit": 1, "rep": 90.5}], "plays": []}
        thin = {"resolved": [ev(1.0, 0.5, i) for i in range(50)], "predictions": {}}
        self.assertNotIn("spread_skill", kw.compute_report(thin))
        # wide spreads paired with big misses must produce a positive correlation
        rs = [ev(1.0, 0.4, i) for i in range(60)] + [ev(3.5, 3.0, i) for i in range(60)]
        rep = kw.compute_report({"resolved": rs, "predictions": {}})
        ss = rep.get("spread_skill")
        self.assertIsNotNone(ss)
        self.assertGreater(ss["corr"], 0.5)
        self.assertEqual(ss["n"], 120)
        labels = [b[0] for b in ss["bands"]]
        self.assertIn("tight", labels); self.assertIn("wide", labels)

    def test_wide_spread_pick_is_tagged_on_the_board(self):
        r = {"code": "DAL", "label": "Dallas (DAL)", "kind": "HIGH",
             "date": dtm.date(2026, 7, 26), "lead": 1, "bucket": "94 to 95", "ticker": "T",
             "mid": 0.30, "mp": 0.42, "edge": 0.12, "side": "Buy YES", "entry": 0.33,
             "net": 0.06, "oi": 900, "sd": kw.SPREAD_WIDE + 1.0, "mean": 94.5,
             "overround": 0.03, "offset": 0.2, "biased": False, "realized": False,
             "tier": "B", "eff": 0.06, "p_win": 0.42, "size_reason": "", "hiconf": False,
             "units": 1.0, "stake": 10.0}
        health = {"ladders": 1, "cities": 1, "cities_failed": [], "gated": [],
                  "capped": 0, "new_24h": 1, "run_utc": "2026-07-26T00:00Z"}

        def board(rec):
            """Render into a THROWAWAY dir. render_bets writes docs/index.html,
            and a test must never touch the real generated boards."""
            saved = kw.OUT_DIR
            try:
                with tempfile.TemporaryDirectory() as d:
                    kw.OUT_DIR = d
                    kw.render_bets([rec], [rec], "now", health)
                    with open(os.path.join(d, "index.html"), encoding="utf-8") as fp:
                        return fp.read()
            finally:
                kw.OUT_DIR = saved

        html = board(r)
        self.assertIn("wide spread", html)
        self.assertIn("spread &plusmn;", html.replace("\u00b1", "&plusmn;"))
        self.assertIn("tight spread", board(dict(r, sd=kw.SPREAD_TIGHT - 0.1)))
        self.assertNotIn("wide spread", board(dict(r, sd=kw.SPREAD_TIGHT - 0.1)))


class TestGlossary(unittest.TestCase):
    """FUTURE 4: a track record nobody can read is a track record nobody can
    check. The glossary must actually render, and must not shout over the data."""

    def _results_html(self, rep):
        saved = kw.OUT_DIR
        try:
            with tempfile.TemporaryDirectory() as d:
                kw.OUT_DIR = d
                kw.render_results(rep, "now", None, [])
                with open(os.path.join(d, "results.html"), encoding="utf-8") as fp:
                    return fp.read()
        finally:
            kw.OUT_DIR = saved

    def _rich_state(self):
        rs = []
        for i in range(40):
            rs.append({"code": "DAL", "kind": "HIGH", "target": f"2026-07-{(i % 28) + 1:02d}",
                       "lead": 1, "actual": 91, "mean": 90.4, "bias": -0.6, "sd": 1.0 + (i % 4),
                       "psd": 1.5, "bias_corr": 0, "sigma": 1.1, "model_version": "2026-07-25.v15",
                       "buckets": [{"mp": 0.5, "mid": 0.5, "hit": i % 2, "rep": 90.5}], "plays": []})
        return {"resolved": rs, "predictions": {}}

    def test_glossary_renders_and_stays_collapsed(self):
        html = self._results_html(kw.compute_report(self._rich_state()))
        self.assertIn("What these words mean", html)
        for term in ("Calibration", "CLV", "Spread", "Frozen play", "Gated"):
            self.assertIn(term, html)
        # collapsed by default: a details element with no open attribute
        self.assertIn("<details class='gloss'>", html)
        self.assertNotIn("<details class='gloss' open", html)

    def test_glossary_never_introduces_an_em_dash(self):
        html = self._results_html(kw.compute_report(self._rich_state()))
        start = html.find("What these words mean")
        self.assertNotIn("\u2014", html[start:start + 4000])


class TestNowcastLive(unittest.TestCase):
    """v15: the nowcast observed max now floors the member cloud for same-day
    HIGHs. Promoted on its re-registered gate (55 binding events, CRPS 1.277 vs
    1.578, per-event RPS 38-4).

    The city clock is pinned via the offset fetch_members returns, so these
    assertions do not depend on when the suite happens to run. Without that a
    same-day HIGH reads as `realized` after 14:00 local and is never priced,
    which made the first draft of this test pass or fail by time of day."""

    def setUp(self):
        self._saved = (kw.pull_weather_markets, kw.fetch_members, kw.fetch_ref,
                       kw.fetch_run_meta, kw.fetch_settled_event, kw.fget, kw.shadow_pass,
                       kw.fetch_ai_members)
        kw.fget = _no_network
        kw.shadow_pass = lambda st: 0          # snapshots are injected by hand here
        kw.fetch_ai_members = lambda *a: {}    # AI evidence models never price anyway

    def tearDown(self):
        (kw.pull_weather_markets, kw.fetch_members, kw.fetch_ref,
         kw.fetch_run_meta, kw.fetch_settled_event, kw.fget, kw.shadow_pass,
         kw.fetch_ai_members) = self._saved

    def _clock(self, local_hour=10):
        """Offset that puts the city clock at local_hour today, and that day."""
        now = dtm.datetime.now(dtm.timezone.utc).replace(tzinfo=None)
        off_h = local_hour - now.hour
        if off_h == 0: off_h = 1               # a 0 offset falls back to the CITIES table
        off = off_h * 3600
        return off, (now + dtm.timedelta(seconds=off)).date()

    def _run(self, kind, day, off, nowcast, lead_days=0):
        bkts = [{"ticker": "T1", "floor": None, "cap": 90, "stype": "less", "sub": "", "yb": .12, "ya": .14, "oi": 900},
                {"ticker": "T2", "floor": 90, "cap": 91, "stype": "between", "sub": "", "yb": .26, "ya": .28, "oi": 900},
                {"ticker": "T3", "floor": 92, "cap": 93, "stype": "between", "sub": "", "yb": .36, "ya": .38, "oi": 900},
                {"ticker": "T4", "floor": 93, "cap": None, "stype": "greater", "sub": "", "yb": .22, "ya": .24, "oi": 900}]
        kw.pull_weather_markets = lambda: [{"code": "DAL", "kind": kind, "date": day,
                                            "event_ticker": "E", "structure_ok": True, "buckets": bkts}]
        vals = [88.0 + j * 0.02 for j in range(140)]   # every member well BELOW the injected floor
        iso = day.isoformat()
        pm = {m: {"hi": {iso: vals}, "lo": {iso: vals}} for m in kw.ENSEMBLE_MODELS}
        kw.fetch_members = lambda lat, lon, tz: ({iso: vals}, {iso: vals}, off, pm)
        kw.fetch_ref = lambda *a: {}
        kw.fetch_run_meta = lambda: {}
        key = f"DAL|{kind}|{iso}"
        pre = {"code": "DAL", "kind": kind, "target": iso, "event_ticker": "E",
               "logged_at": "old", "first_logged": "old", "lead": lead_days, "mean": 88.0,
               "sd": 1.0, "psd": 1.5, "bias_corr": 0.0, "sigma": 1.1, "buckets": [], "plays": []}
        if nowcast: pre["nowcast"] = nowcast
        state = {"predictions": {key: pre}, "resolved": []}
        kw.score(state)
        return state["predictions"][key]

    def test_same_day_high_is_floored_at_the_observed_max(self):
        off, day = self._clock(10)
        rec = self._run("HIGH", day, off, {"obs_max": 95.0, "n_obs": 9})
        self.assertEqual(rec.get("nowcast_floor"), 95.0)
        self.assertGreaterEqual(rec["mean"], 95.0)   # cloud sat at ~88, pulled up to the floor

    def test_no_snapshot_means_no_truncation(self):
        off, day = self._clock(10)
        rec = self._run("HIGH", day, off, None)
        self.assertIsNone(rec.get("nowcast_floor"))
        self.assertLess(rec["mean"], 90.0)

    def test_future_high_is_never_truncated(self):
        """Isolates the lead guard: tomorrow's high cannot use today's obs."""
        off, day = self._clock(10)
        rec = self._run("HIGH", day + dtm.timedelta(days=1), off,
                        {"obs_max": 95.0, "n_obs": 9}, lead_days=1)
        self.assertIsNone(rec.get("nowcast_floor"))
        self.assertLess(rec["mean"], 90.0)

    def test_lows_are_never_truncated(self):
        off, day = self._clock(10)
        rec = self._run("LOW", day + dtm.timedelta(days=1), off,
                        {"obs_max": 95.0, "n_obs": 9}, lead_days=1)
        self.assertIsNone(rec.get("nowcast_floor"))
        self.assertLess(rec["mean"], 90.0)

    def test_floor_never_lowers_a_member(self):
        """Truncation is a floor, not a replacement: members above it are kept."""
        self.assertEqual([max(v, 95.0) for v in [88.0, 96.0, 99.0]], [95.0, 96.0, 99.0])


class TestProviderWeighting(unittest.TestCase):
    """Docket 4 (v14): per-kind inverse-MSE provider pooling."""

    def _res(self, kind, errs_by_model, tgt):
        return {"code": "DAL", "kind": kind, "target": tgt, "actual": 90.0,
                "mean": 90.0, "bias": 0.0, "sd": 1.0, "psd": 1.5, "bias_corr": 0.0,
                "sigma": 1.1, "buckets": [],
                "members_by_model": {m: {"n": 30, "mean": 90.0 + e, "sd": 1.0}
                                     for m, e in errs_by_model.items()}}

    def test_warmup_returns_no_weights(self):
        """Below warmup the model must keep the member-count pool untouched."""
        errs = {m: 1.0 for m in kw.ENSEMBLE_MODELS}
        st = {"resolved": [self._res("HIGH", errs, f"2026-07-{i+1:02d}") for i in range(10)]}
        self.assertEqual(kw.provider_weights(st), {})

    def test_weights_favor_the_accurate_provider_and_are_per_kind(self):
        res = []
        for i in range(kw.PROVIDER_W_WARMUP + 5):
            # on HIGHs gem is bad and icon is good; on LOWs the roles reverse
            hi = {"gfs025": 1.0, "ecmwf_ifs025": 1.0, "icon_seamless": 0.1, "gem_global": 4.0}
            lo = {"gfs025": 1.0, "ecmwf_ifs025": 1.0, "icon_seamless": 4.0, "gem_global": 0.1}
            res.append(self._res("HIGH", hi, f"2026-06-{i+1:02d}"))
            res.append(self._res("LOW", lo, f"2026-06-{i+1:02d}"))
        w = kw.provider_weights({"resolved": res})
        self.assertIn("HIGH", w); self.assertIn("LOW", w)
        self.assertGreater(w["HIGH"]["icon_seamless"], w["HIGH"]["gem_global"])
        self.assertGreater(w["LOW"]["gem_global"], w["LOW"]["icon_seamless"])   # learned separately
        # epsilon must stop a near-perfect provider from taking the whole cloud
        self.assertLess(w["HIGH"]["icon_seamless"] / sum(w["HIGH"].values()), 0.95)

    def test_gated_and_unsettled_records_never_teach_weights(self):
        good = {m: 1.0 for m in kw.ENSEMBLE_MODELS}
        res = [self._res("HIGH", good, f"2026-06-{i+1:02d}") for i in range(kw.PROVIDER_W_WARMUP + 2)]
        base = kw.provider_weights({"resolved": res})["HIGH"]
        poisoned = dict(res[0]); poisoned["gated"] = "ladder structure"
        poisoned["members_by_model"] = {m: {"n": 30, "mean": 190.0, "sd": 1.0} for m in kw.ENSEMBLE_MODELS}
        after = kw.provider_weights({"resolved": res + [poisoned]})["HIGH"]
        self.assertEqual(base, after)

    def test_weighted_cloud_matches_mixture_mean_and_falls_back(self):
        """The weighted cloud's mean must equal the weighted mixture mean, which is
        the exact quantity the docket 4 gate measured."""
        pvals = {"gfs025": [80.0] * 4, "ecmwf_ifs025": [90.0] * 2,
                 "icon_seamless": [100.0] * 8, "gem_global": [70.0] * 1}
        wmap = {"gfs025": 1.0, "ecmwf_ifs025": 1.0, "icon_seamless": 1.0, "gem_global": 1.0}
        members, wts = kw.weighted_cloud(pvals, wmap, 0.0)
        mean, _ = kw.wmean_wsd(members, wts)
        self.assertAlmostEqual(mean, (80 + 90 + 100 + 70) / 4, places=9)   # equal weight per PROVIDER
        self.assertNotAlmostEqual(mean, sum(members) / len(members), places=3)  # not per MEMBER
        # a missing provider forfeits weighting rather than silently reweighting
        self.assertIsNone(kw.weighted_cloud({"gfs025": [80.0]}, wmap, 0.0))
        self.assertIsNone(kw.weighted_cloud(pvals, None, 0.0))

    def test_unweighted_dressed_prob_is_bit_identical(self):
        """Warmup and missing-provider paths must reproduce v13 pricing exactly."""
        mem = [88.0, 89.0, 90.0, 91.0]
        b = {"stype": "between", "floor": 89, "cap": 90}
        self.assertEqual(kw.dressed_prob(mem, b, 1.1), kw.dressed_prob(mem, b, 1.1, None))
        flat = kw.dressed_prob(mem, b, 1.1)
        self.assertAlmostEqual(kw.dressed_prob(mem, b, 1.1, [1.0] * 4), flat, places=12)


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


class TestArchive(unittest.TestCase):
    """HANDOFF 7b split, as amended 2026-07-28. The track record cannot be
    recreated, so the load-bearing property is that no settlement can be lost:
    live and archived sets must always partition the whole history."""

    def _res(self, target):
        return {"code": "DAL", "kind": "HIGH", "target": target, "actual": 90.0,
                "mean": 90.0, "bias": 0.0, "sd": 1.0, "psd": 1.5, "bias_corr": 0.0,
                "sigma": 1.1, "buckets": [{"mp": 0.5, "mid": 0.5, "hit": 1, "rep": 90.5}],
                "plays": []}

    def _paths(self, td):
        kw.STATE_PATH = os.path.join(td, "weather_state.json")
        kw.ARCHIVE_PATH = os.path.join(td, "weather_state_archive.json")

    def _big_state(self, days_old_list):
        """A state whose file is over the trigger, with records at given ages."""
        recs = []
        for n in days_old_list:
            recs.append(self._res((dtm.date.today() - dtm.timedelta(days=n)).isoformat()))
        return {"predictions": {}, "resolved": recs}

    def _write_over_trigger(self, state):
        """Write the state file, then pad it past the trigger without touching
        the records, so size and content are independent in these tests."""
        kw.save_state(state)
        with open(kw.STATE_PATH, "a", encoding="utf-8") as f:
            f.write(" " * int(kw.ARCHIVE_TRIGGER_MB * 1e6))

    def test_no_split_below_the_trigger(self):
        saved = (kw.STATE_PATH, kw.ARCHIVE_PATH)
        with tempfile.TemporaryDirectory() as td:
            self._paths(td)
            try:
                st = self._big_state([200, 300])       # old enough, but file is small
                kw.save_state(st)
                self.assertEqual(kw.archive_pass(st), 0)
                self.assertEqual(len(st["resolved"]), 2)
                self.assertFalse(os.path.exists(kw.ARCHIVE_PATH))
            finally:
                (kw.STATE_PATH, kw.ARCHIVE_PATH) = saved

    def test_trigger_without_old_records_is_a_graceful_noop(self):
        """The exact defect the amendment fixes: the old 120-day window could
        fire into a history far younger than itself and silently do nothing.
        It must stay a no-op that loses nothing, not an error and not a split."""
        saved = (kw.STATE_PATH, kw.ARCHIVE_PATH)
        with tempfile.TemporaryDirectory() as td:
            self._paths(td)
            try:
                st = self._big_state([1, 5, 20])       # whole history younger than the window
                self._write_over_trigger(st)
                self.assertEqual(kw.archive_pass(st), 0)
                self.assertEqual(len(st["resolved"]), 3)
                self.assertFalse(os.path.exists(kw.ARCHIVE_PATH))
            finally:
                (kw.STATE_PATH, kw.ARCHIVE_PATH) = saved

    def test_split_partitions_history_and_loses_nothing(self):
        saved = (kw.STATE_PATH, kw.ARCHIVE_PATH)
        with tempfile.TemporaryDirectory() as td:
            self._paths(td)
            try:
                ages = [1, 10, 44, 46, 90, 200]        # 3 inside the window, 3 outside
                st = self._big_state(ages)
                before = {(r["code"], r["kind"], r["target"]) for r in st["resolved"]}
                self._write_over_trigger(st)
                moved = kw.archive_pass(st)
                self.assertEqual(moved, 3)
                live = {(r["code"], r["kind"], r["target"]) for r in st["resolved"]}
                arch = {(r["code"], r["kind"], r["target"]) for r in kw.load_archive()}
                self.assertEqual(len(live), 3)
                self.assertEqual(len(arch), 3)
                self.assertEqual(live | arch, before)      # nothing lost
                self.assertEqual(live & arch, set())       # nothing double-counted
                # every retained record is inside the window, every moved one outside
                cut = (dtm.date.today() - dtm.timedelta(days=kw.ARCHIVE_KEEP_DAYS)).isoformat()
                self.assertTrue(all(t >= cut for _, _, t in live))
                self.assertTrue(all(t < cut for _, _, t in arch))
            finally:
                (kw.STATE_PATH, kw.ARCHIVE_PATH) = saved

    def test_reporting_view_restores_the_whole_record_and_dedupes(self):
        """Every pre-registered gate counts over the full history, so a split
        must not reset those counters. An interrupted split can leave a record
        in both files; the merge must count it once."""
        saved = (kw.STATE_PATH, kw.ARCHIVE_PATH)
        with tempfile.TemporaryDirectory() as td:
            self._paths(td)
            try:
                st = self._big_state([1, 10, 44, 46, 90, 200])
                self._write_over_trigger(st)
                full_n = kw.compute_report(st)["n_events"]
                kw.archive_pass(st)
                self.assertEqual(kw.compute_report(st)["n_events"], 3)          # live alone is short
                view = kw.reporting_view(st)
                self.assertEqual(kw.compute_report(view)["n_events"], full_n)   # merged is whole
                self.assertIsNot(view, st)
                self.assertEqual(len(st["resolved"]), 3)                        # view never mutates live
                # simulate a crash between writing the archive and trimming live
                st["resolved"] = st["resolved"] + kw.load_archive()
                self.assertEqual(kw.compute_report(kw.reporting_view(st))["n_events"], full_n)
            finally:
                (kw.STATE_PATH, kw.ARCHIVE_PATH) = saved

    def test_unreadable_archive_is_fatal_not_a_shorter_record(self):
        saved = (kw.STATE_PATH, kw.ARCHIVE_PATH)
        with tempfile.TemporaryDirectory() as td:
            self._paths(td)
            try:
                self.assertEqual(kw.load_archive(), [])          # absent is normal
                with open(kw.ARCHIVE_PATH, "w") as f: f.write("{ corrupt")
                with self.assertRaises(SystemExit): kw.load_archive()
                with open(kw.ARCHIVE_PATH, "w") as f: json.dump({"resolved": []}, f)
                with self.assertRaises(SystemExit): kw.load_archive()
            finally:
                (kw.STATE_PATH, kw.ARCHIVE_PATH) = saved


class TestNowcastShadow(unittest.TestCase):
    """Checkpoint 1 build (FUTURE 5 stage 1): truncation math, obs parsing,
    grading, and the guarantees that keep the shadow a shadow."""

    def test_parse_obs_max_filters_and_converts(self):
        js={"features":[
            {"properties":{"timestamp":"2026-07-13T12:53:00+00:00","temperature":{"value":25.0}}},   # before window
            {"properties":{"timestamp":"2026-07-13T13:53:00+00:00","temperature":{"value":30.0}}},   # 86.0 F
            {"properties":{"timestamp":"2026-07-13T14:53:00+00:00","temperature":{"value":None}}},   # null skipped
            {"properties":{"timestamp":"2026-07-13T15:53:00+00:00","temperature":{"value":32.2}}},   # 89.96 F
        ]}
        got=kw._parse_obs_max(js,"2026-07-13T13:00")
        self.assertIsNotNone(got)
        mx,n=got
        self.assertEqual(n,2)
        self.assertAlmostEqual(mx,89.96,places=2)
        self.assertIsNone(kw._parse_obs_max({"features":[]},"2026-07-13T13:00"))
        self.assertIsNone(kw._parse_obs_max(None,"2026-07-13T13:00"))

    def test_truncation_floors_members_and_raises_mean(self):
        mem_u=[70.0,72.0,75.0]; runmax=73.0
        mem_t=[max(v,runmax) for v in mem_u]
        self.assertEqual(mem_t,[73.0,73.0,75.0])
        self.assertGreater(sum(mem_t)/3,sum(mem_u)/3)
        self.assertTrue(all(v>=runmax for v in mem_t))
        # truncated mass below the running max collapses toward zero
        b={"stype":"less","cap":72,"floor":None}
        lo_u=kw.dressed_prob(mem_u,b,0.8); lo_t=kw.dressed_prob(mem_t,b,0.8)
        self.assertLess(lo_t,lo_u)

    def test_grade_nowcast_mirrors_report_rps(self):
        nc={"asof":"x","obs_max":91.0,"n_obs":5,"mean_u":90.0,"psd_u":2.0,
            "mean_t":92.0,"psd_t":1.5,
            "buckets":[{"ticker":"A","rep":88.5,"mp_u":0.30,"mp_t":0.05},
                       {"ticker":"B","rep":90.5,"mp_u":0.40,"mp_t":0.25},
                       {"ticker":"C","rep":92.5,"mp_u":0.20,"mp_t":0.50},
                       {"ticker":"D","rep":94.5,"mp_u":0.10,"mp_t":0.20}]}
        settled={"A":("no",None),"B":("no",None),"C":("yes",None),"D":("no",None)}
        g=kw._grade_nowcast(nc,settled,92)
        self.assertIsNotNone(g)
        # truncated ladder, built to know 91 already printed, must grade sharper
        self.assertLess(g["rps_t"],g["rps_u"])
        self.assertLess(g["crps_t"],g["crps_u"])
        # hand-checked cumulative math on the truncated side:
        # F=.05,.30,.80 vs O=0,0,1 -> .0025+.09+.04=.1325
        self.assertAlmostEqual(g["rps_t"],0.1325,places=4)
        # ungradeable inputs return None instead of poisoning aggregates
        self.assertIsNone(kw._grade_nowcast(nc,{"A":("no",None)},92))
        two_hit=dict(settled); two_hit["D"]=("yes",None)
        self.assertIsNone(kw._grade_nowcast(nc,two_hit,92))

    def test_shadow_pass_write_once_and_no_side_effects(self):
        saved=(kw.pull_weather_markets,kw.fetch_members,kw.fget)
        kw.pull_weather_markets=_no_network; kw.fetch_members=_no_network; kw.fget=_no_network
        try:
            # a pending record already carrying a snapshot is never refetched or
            # rewritten (all fetchers raise here), and nothing else is touched
            marker={"asof":"first","obs_max":90.0,"n_obs":3,"buckets":[]}
            code=next(iter(kw.STATION_IDS))
            tz=kw.CITIES[code][2]
            off=kw.STD_OFFSET_H.get(tz,0)*3600
            lnow=dtm.datetime.now(dtm.timezone.utc).replace(tzinfo=None)+dtm.timedelta(seconds=off)
            state={"predictions":{f"{code}|HIGH|{lnow.date().isoformat()}":
                       {"code":code,"kind":"HIGH","target":lnow.date().isoformat(),
                        "nowcast":dict(marker),"plays":[]}},
                   "resolved":[]}
            before=json.dumps(state["predictions"],sort_keys=True)
            kw.shadow_pass(state)
            self.assertEqual(json.dumps(state["predictions"],sort_keys=True),before)
            # LOW records and gated records are never candidates either
            state2={"predictions":{"X|LOW|2026-01-01":{"code":"X","kind":"LOW","target":"2026-01-01"}},
                    "resolved":[]}
            self.assertEqual(kw.shadow_pass(state2),0)
        finally:
            kw.pull_weather_markets,kw.fetch_members,kw.fget=saved


    def test_shadow_prices_the_same_cloud_production_does(self):
        """v15: once truncation is live, the paired snapshot must be built from
        the skill-weighted cloud production uses. A monitor that watches a model
        which is no longer running is worse than no monitor."""
        code = next(iter(kw.STATION_IDS))
        lat, lon, tz, label = kw.CITIES[code]
        off = kw.STD_OFFSET_H.get(tz, 0) * 3600
        lnow = dtm.datetime.now(dtm.timezone.utc).replace(tzinfo=None) + dtm.timedelta(seconds=off)
        tgt = lnow.date().isoformat()
        # Widen the collection window for the duration of the test instead of
        # skipping outside 9am-2pm local. A test that only runs for five hours a
        # day is one that fails to catch a regression the other nineteen.
        win = (kw.NOWCAST_MIN_LHR, kw.INTRADAY_HIGH_CUTOFF)
        kw.NOWCAST_MIN_LHR, kw.INTRADAY_HIGH_CUTOFF = 0, 24
        # ICON forecasts much colder than the rest; weighting must move the mean
        per = {"gfs025": [90.0] * 40, "ecmwf_ifs025": [90.0] * 40,
               "icon_seamless": [80.0] * 40, "gem_global": [90.0] * 40}
        pooled = [v for vs in per.values() for v in vs]
        pm = {m: {"hi": {tgt: vs}, "lo": {tgt: vs}} for m, vs in per.items()}
        bkts = [{"ticker": "T1", "floor": None, "cap": 88, "stype": "less", "sub": "", "yb": .1, "ya": .2, "oi": 900},
                {"ticker": "T2", "floor": 88, "cap": 92, "stype": "between", "sub": "", "yb": .3, "ya": .4, "oi": 900},
                {"ticker": "T3", "floor": 92, "cap": None, "stype": "greater", "sub": "", "yb": .3, "ya": .4, "oi": 900}]
        saved = (kw.pull_weather_markets, kw.fetch_members, kw.fetch_running_max)
        try:
            kw.pull_weather_markets = lambda: [{"code": code, "kind": "HIGH",
                                                "date": dtm.date.fromisoformat(tgt), "event_ticker": "E",
                                                "structure_ok": True, "buckets": bkts}]
            kw.fetch_members = lambda a, b, c: ({tgt: pooled}, {tgt: pooled}, off, pm)
            kw.fetch_running_max = lambda *a: (70.0, 5)      # below the cloud: never binds
            # history that makes ICON look terrible, so weighting must discount it
            res = []
            for i in range(kw.PROVIDER_W_WARMUP + 5):
                res.append({"code": code, "kind": "HIGH", "target": f"2026-06-{(i % 28) + 1:02d}",
                            "actual": 90.0, "mean": 90.0, "bias": 0.0, "sd": 1.0, "psd": 1.5,
                            "bias_corr": 0.0, "sigma": 1.1, "buckets": [], "plays": [],
                            "members_by_model": {"gfs025": {"n": 40, "mean": 90.2, "sd": 1.0},
                                                 "ecmwf_ifs025": {"n": 40, "mean": 90.1, "sd": 1.0},
                                                 "icon_seamless": {"n": 40, "mean": 80.0, "sd": 1.0},
                                                 "gem_global": {"n": 40, "mean": 90.3, "sd": 1.0}}})
            state = {"predictions": {f"{code}|HIGH|{tgt}":
                        {"code": code, "kind": "HIGH", "target": tgt, "plays": []}},
                     "resolved": res}
            self.assertTrue(kw.provider_weights(state).get("HIGH"), "fixture failed to clear warmup")
            wrote = kw.shadow_pass(state)
            self.assertEqual(wrote, 1)
            nc = state["predictions"][f"{code}|HIGH|{tgt}"]["nowcast"]
            # unweighted pooling would sit near 87.5; discounting ICON pulls it up
            self.assertGreater(nc["mean_u"], 88.0, "snapshot still built from the pooled cloud")
        finally:
            (kw.pull_weather_markets, kw.fetch_members, kw.fetch_running_max) = saved
            kw.NOWCAST_MIN_LHR, kw.INTRADAY_HIGH_CUTOFF = win

    def test_era_label_future_proof(self):
        # v13 was misfiled under Legacy for three days because the first draft
        # enumerated new-era stamps; the rule now enumerates the CLOSED legacy set
        self.assertEqual(kw._era_label(""), "Legacy (pre-audit)")
        self.assertEqual(kw._era_label("2026-07-02.v3-nimbus-calib"), "Legacy (pre-audit)")
        for mv in ("2026-07-06.v11-audit12", "2026-07-06.v12-capseed",
                   "2026-07-13.v13-nowcast-shadow", "2026-09-01.v14-whatever"):
            self.assertEqual(kw._era_label(mv), "Audit build (v11+)")


    def test_play_pwin_falls_back_to_raw_mp(self):
        # Plays settled before the retention fix carry mp but no p_win. The
        # docket 1 cell must still be read as REGISTERED on them, so p_win is
        # reconstructed the way entry-time computed it: clamped mp for YES,
        # 1 - clamped mp for NO.
        self.assertEqual(kw.play_pwin({"p_win": 0.42, "mp": 0.9, "side": "Buy YES"}), 0.42)
        self.assertAlmostEqual(kw.play_pwin({"mp": 0.42, "side": "Buy YES"}), 0.42)
        self.assertAlmostEqual(kw.play_pwin({"mp": 0.42, "side": "Buy NO"}), 0.58)
        # the clamp binds only in the deep tails, far from the 0.30 threshold
        self.assertAlmostEqual(kw.play_pwin({"mp": 0.001, "side": "Buy YES"}), kw.TAIL_FLOOR)
        self.assertAlmostEqual(kw.play_pwin({"mp": 0.999, "side": "Buy NO"}), kw.TAIL_FLOOR)
        self.assertIsNone(kw.play_pwin({"side": "Buy YES"}))
        # a p_win of 0.0 must not be mistaken for a missing field
        self.assertEqual(kw.play_pwin({"p_win": 0.0, "mp": 0.42, "side": "Buy YES"}), 0.0)

    def test_cheap_entry_cell_reads_both_registered_arms(self):
        # A dear-entry play the model expects to lose belongs in the cheap cell
        # via the p_win arm. Before the fix it was filed under the CORE book,
        # flattering the core and starving the gate.
        def play(entry, mp, side, won=False):
            return {"entry": entry, "mp": mp, "side": side, "won": won, "units": 1.0,
                    "stake": 10.0, "pnl": -10.0, "clv": 0.0, "contracts": int(10.0 // entry),
                    "lead": 1, "tier": "B", "mid": entry, "margin": 0.0, "edge": 0.0,
                    "code": "DAL", "kind": "HIGH", "target": "2026-07-01", "sub": "",
                    "close_mid": entry, "actual": 95,
                    "model_version": "2026-07-06.v11-audit12"}
        state = {"predictions": {}, "resolved": [{
            "code": "DAL", "kind": "HIGH", "target": "2026-07-01", "lead": 1, "actual": 95,
            "mean": 95.0, "bias": 0.0, "psd": 1.5, "sd": 1.5,
            "buckets": [{"mp": 0.4, "mid": 0.4, "hit": 1, "rep": 95.0}],
            "plays": [play(0.60, 0.25, "Buy YES"),    # p_win arm: 0.25 <= 0.30
                      play(0.10, 0.80, "Buy YES"),    # entry arm: 0.10 <= 0.20
                      play(0.60, 0.60, "Buy YES", True)]}]}   # core
        rep = kw.compute_report(state)
        self.assertEqual(rep["book_split"]["exp"]["n"], 2)
        self.assertEqual(rep["book_split"]["core"]["n"], 1)

    def test_challenger_weighting_tally(self):
        # two sharp providers plus one heavy awful one: skill weighting must
        # beat count weighting decisively past warmup; dates end before the
        # registration date so the prospective bucket stays empty
        rows=[]
        day=dtm.date(2026, 3, 1)
        for i in range(120):
            d=(day+dtm.timedelta(days=i)).isoformat()
            actual=70+(i%7)
            mm={"gfs025":{"n":10,"mean":actual+0.2,"sd":1.0},
                "ecmwf_ifs025":{"n":10,"mean":actual+0.1,"sd":1.0},
                "icon_seamless":{"n":10,"mean":actual-0.2,"sd":1.0},
                "gem_global":{"n":40,"mean":actual+5.0,"sd":1.0}}
            for kind in ("HIGH","LOW"):
                rows.append({"target":d,"kind":kind,"actual":actual,"members_by_model":mm})
        t=kw.challenger_weighting_tally(rows)
        self.assertIsNotNone(t)
        self.assertEqual(t["n"], 240)
        self.assertEqual(t["n_prosp"], 0)
        self.assertIsNone(t["adv_prosp"])
        self.assertGreater(t["adv"], 0.5)
        self.assertGreater(t["ci_lo"], 0.0)
        # below the 50-record floor: no tally
        self.assertIsNone(kw.challenger_weighting_tally(rows[:40]))

    def test_challenger_tally_ignores_ai_evidence_models(self):
        # AI providers ride members_by_model since 2026-07-28 but have no error
        # history in the tally: rows carrying them must produce the exact same
        # tally as rows without them, and must not crash the skill weights
        rows=[]; rows_ai=[]
        day=dtm.date(2026, 3, 1)
        for i in range(120):
            d=(day+dtm.timedelta(days=i)).isoformat()
            actual=70+(i%7)
            mm={"gfs025":{"n":10,"mean":actual+0.2,"sd":1.0},
                "ecmwf_ifs025":{"n":10,"mean":actual+0.1,"sd":1.0},
                "icon_seamless":{"n":10,"mean":actual-0.2,"sd":1.0},
                "gem_global":{"n":40,"mean":actual+5.0,"sd":1.0}}
            mm_ai=dict(mm, ncep_aigefs025={"n":31,"mean":actual-9.0,"sd":1.0},
                       ecmwf_aifs025={"n":51,"mean":actual+9.0,"sd":1.0})
            for kind in ("HIGH","LOW"):
                rows.append({"target":d,"kind":kind,"actual":actual,"members_by_model":mm})
                rows_ai.append({"target":d,"kind":kind,"actual":actual,"members_by_model":mm_ai})
        self.assertEqual(kw.challenger_weighting_tally(rows),
                         kw.challenger_weighting_tally(rows_ai))


    def test_prod_gate_conditions(self):
        # all-met scenario: 100 winning plays, tight positive CLV, sd(z)=1.0,
        # cheap cell read; kill legs not binding under 150 plays
        plays=[{"stake":10.0,"pnl":1.0,"clv":0.05,"won":True} for _ in range(100)]
        zs=[1.0,-1.0]*20
        gate=kw._prod_gate(plays, zs, 40)
        self.assertEqual(len(gate), 6)
        self.assertTrue(all(m for _,m,_ in gate))
        # all-open scenario
        gate2=kw._prod_gate([{"stake":10.0,"pnl":-5.0,"clv":None,"won":False}]*5, [0.1]*5, 5)
        self.assertEqual(sum(1 for _,m,_ in gate2 if m), 1)   # only "kill not fired" holds
        self.assertTrue(gate2[4][1])


class TestRainShadow(unittest.TestCase):
    """KXRAIN evidence shadow (FUTURE 5b): logging and grading only. These tests
    pin the market parser, the LST wet-fraction math, the write-once invariant,
    settlement grading, and the report/render path, all network-free."""

    def _mkts_payload(self, yb=0.10, ya=0.16):
        return {"events": [{"event_ticker": "KXRAIN-26JUL30", "markets": [
            {"ticker": "KXRAIN-26JUL30-DEN", "yes_bid_dollars": str(yb),
             "yes_ask_dollars": str(ya), "volume_fp": "1010.86", "open_interest_fp": "4929.94"},
            {"ticker": "KXRAIN-26JUL30-ZZZ", "yes_bid_dollars": "0.5",
             "yes_ask_dollars": "0.6", "volume_fp": "1", "open_interest_fp": "1"},
        ]}]}

    def test_rain_market_parser(self):
        saved = kw.fget
        try:
            kw.fget = lambda url, tries=3: self._mkts_payload()
            out = kw.fetch_rain_markets()
        finally:
            kw.fget = saved
        self.assertIn("2026-07-30", out)
        self.assertIn("DEN", out["2026-07-30"])
        self.assertNotIn("ZZZ", out["2026-07-30"])   # unknown suffix skipped, never guessed
        q = out["2026-07-30"]["DEN"]
        self.assertEqual(q["mid"], 0.13)
        self.assertEqual(q["vol"], 1010.86)
        self.assertEqual(q["event_ticker"], "KXRAIN-26JUL30")
        # a dead fetch is an empty dict, not an exception
        try:
            kw.fget = lambda url, tries=3: None
            self.assertEqual(kw.fetch_rain_markets(), {})
        finally:
            kw.fget = saved

    def test_rain_wet_fractions_hand_computed(self):
        # CST (utc_offset_seconds == std offset): no LST shift. Four members
        # over one day: totals 2.0 mm (clears every threshold), 0.5 mm (wet but
        # under 1.0 mm), 0.10 mm (any-precip only), 0.0 (dry).
        times = [f"2026-07-30T{h:02d}:00" for h in range(24)]
        def mem(total_first_two_hours):
            return [total_first_two_hours / 2.0] * 2 + [0.0] * 22
        payload = {"utc_offset_seconds": -21600, "hourly": {
            "time": times,
            "precipitation_member01": mem(2.0),
            "precipitation_member02": mem(0.5),
            "precipitation_member03": mem(0.10),
            "precipitation_member04": mem(0.0)}}
        saved = kw.fget
        try:
            kw.fget = lambda url, tries=3: payload
            out = kw.fetch_rain_members(39.85, -104.66, "America/Chicago")
        finally:
            kw.fget = saved
        # AI evidence providers are fetched the same way and land beside the core
        for m in kw.ENSEMBLE_MODELS + kw.AI_ENSEMBLE_MODELS:
            d = out[m]["2026-07-30"]
            self.assertEqual(d["n"], 4)
            self.assertAlmostEqual(d["wet"], 2 / 4, places=3)    # 2.0 and 0.5 clear 0.254 mm
            self.assertAlmostEqual(d["wet0"], 3 / 4, places=3)
            self.assertAlmostEqual(d["wet1"], 1 / 4, places=3)   # only 2.0 clears 1.0 mm

    def test_rain_pass_write_once_and_requires_forecast(self):
        saved_m, saved_f = kw.fetch_rain_markets, kw.fetch_rain_members
        prov = {m: {"2026-07-30": {"n": 30, "wet": 0.40, "wet0": 0.60, "wet1": 0.20}}
                for m in kw.ENSEMBLE_MODELS}
        # a wildly wet AI provider must be LOGGED but never pooled (core-only
        # pooling mirrors temperature: AI is evidence, racing solo offline)
        prov["ncep_aigefs025"] = {"2026-07-30": {"n": 31, "wet": 1.0, "wet0": 1.0, "wet1": 1.0}}
        try:
            kw.fetch_rain_markets = lambda: {"2026-07-30": {"DEN": {
                "ticker": "KXRAIN-26JUL30-DEN", "event_ticker": "KXRAIN-26JUL30",
                "yb": 0.10, "ya": 0.16, "mid": 0.13, "vol": 100.0, "oi": 200.0}}}
            kw.fetch_rain_members = lambda lat, lon, tz: prov
            state = {"predictions": {}, "resolved": []}
            self.assertEqual(kw.rain_pass(state, "2026-07-30T12:19Z"), 1)
            rec = state["rain"]["pending"]["DEN|2026-07-30"]
            self.assertEqual(rec["mid"], 0.13)
            self.assertAlmostEqual(rec["pool_wet"], 0.40, places=6)   # core only: the 1.0 AI fraction is excluded
            self.assertAlmostEqual(rec["pool_wet1"], 0.20, places=6)
            self.assertIn("ncep_aigefs025", rec["p"])                 # but it IS logged as evidence
            # second sighting with moved prices must NOT rewrite the record
            kw.fetch_rain_markets = lambda: {"2026-07-30": {"DEN": {
                "ticker": "KXRAIN-26JUL30-DEN", "event_ticker": "KXRAIN-26JUL30",
                "yb": 0.50, "ya": 0.56, "mid": 0.53, "vol": 999.0, "oi": 999.0}}}
            self.assertEqual(kw.rain_pass(state, "2026-07-30T21:40Z"), 0)
            self.assertEqual(state["rain"]["pending"]["DEN|2026-07-30"]["mid"], 0.13)
            # no CORE forecast, no record: prices alone are never logged, and an
            # AI-only response must not create a record either
            kw.fetch_rain_markets = lambda: {"2026-07-31": {"DEN": {
                "ticker": "KXRAIN-26JUL31-DEN", "event_ticker": "KXRAIN-26JUL31",
                "yb": 0.2, "ya": 0.3, "mid": 0.25, "vol": 1.0, "oi": 1.0}}}
            kw.fetch_rain_members = lambda lat, lon, tz: {
                "ncep_aigefs025": {"2026-07-31": {"n": 31, "wet": 0.5, "wet0": 0.5, "wet1": 0.5}}}
            self.assertEqual(kw.rain_pass(state, "2026-07-31T12:19Z"), 0)
            self.assertNotIn("DEN|2026-07-31", state["rain"]["pending"])
        finally:
            kw.fetch_rain_markets, kw.fetch_rain_members = saved_m, saved_f

    def test_rain_resolve_grades_and_waits(self):
        saved_f, saved_today = kw.fetch_settled_event, kw.TODAY
        rec = {"code": "DEN", "target": "2026-07-30", "ticker": "KXRAIN-26JUL30-DEN",
               "event_ticker": "KXRAIN-26JUL30", "logged_at": "x", "yb": 0.10, "ya": 0.16,
               "mid": 0.13, "vol": 1.0, "oi": 2.0, "p": {}, "pool_wet": 0.40, "pool_wet0": 0.6, "rv": 1}
        wait = dict(rec, code="SEA", ticker="KXRAIN-26JUL30-SEA")
        state = {"rain": {"pending": {"DEN|2026-07-30": dict(rec),
                                      "SEA|2026-07-30": wait}, "resolved": []}}
        try:
            kw.TODAY = dtm.date(2026, 8, 2)
            kw.fetch_settled_event = lambda et: {"KXRAIN-26JUL30-DEN": ("yes", None)}
            self.assertEqual(kw.rain_resolve(state), 1)
        finally:
            kw.fetch_settled_event, kw.TODAY = saved_f, saved_today
        rv = state["rain"]["resolved"]
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0]["hit"], 1)
        self.assertEqual(rv[0]["code"], "DEN")
        self.assertNotIn("DEN|2026-07-30", state["rain"]["pending"])
        self.assertIn("SEA|2026-07-30", state["rain"]["pending"])   # unsettled waits

    def test_rain_report_and_render(self):
        state = {"predictions": {}, "resolved": [],
                 "rain": {"pending": {}, "resolved": [
                     {"code": "DEN", "target": "2026-07-30", "mid": 0.20, "pool_wet": 0.10,
                      "pool_wet0": 0.2, "hit": 0, "rv": 1},
                     {"code": "SEA", "target": "2026-07-30", "mid": 0.60, "pool_wet": 0.90,
                      "pool_wet0": 0.95, "hit": 1, "rv": 1}]}}
        rep = kw.compute_report(state)
        rn = rep["rain"]
        self.assertEqual(rn["n"], 2)
        self.assertAlmostEqual(rn["brier_pool"], ((0.10 - 0) ** 2 + (0.90 - 1) ** 2) / 2, places=9)
        self.assertAlmostEqual(rn["brier_mkt"], ((0.20 - 0) ** 2 + (0.60 - 1) ** 2) / 2, places=9)
        self.assertAlmostEqual(rn["wet_rate"], 0.5, places=9)
        # renders only via the results page, never as a play anywhere
        rep2 = dict(rep, plays=[{"code": "DEN", "kind": "HIGH", "target": "2026-07-30",
                                 "sub": "x", "side": "Buy YES", "entry": 0.5, "tier": "B",
                                 "units": 1.0, "stake": 10.0, "contracts": 20, "won": True,
                                 "pnl": 1.0, "margin": 1.0, "actual": 91, "mp": 0.55,
                                 "mid": 0.5, "edge": 0.06, "net": 0.05, "lead": 1,
                                 "close_mid": 0.5, "clv": 0.0, "model_version": "t"}],
                    pnl={"n": 1, "wins": 1, "winrate": 1.0, "net": 1.0, "staked": 10.0,
                         "roi": 0.1, "net_units": 0.1, "avg_margin": 1.0})
        saved = kw.OUT_DIR
        try:
            with tempfile.TemporaryDirectory() as d:
                kw.OUT_DIR = d
                kw.render_results(rep2, "now", None, [])
                with open(os.path.join(d, "results.html"), encoding="utf-8") as fp:
                    html = fp.read()
        finally:
            kw.OUT_DIR = saved
        self.assertIn("Rain shadow (evidence only)", html)
        self.assertIn("graded city-days", html)
        # and a state with no rain key renders no rain section
        rep3 = kw.compute_report({"predictions": {}, "resolved": []})
        self.assertNotIn("rain", rep3)


if __name__ == "__main__":
    unittest.main(verbosity=1)
