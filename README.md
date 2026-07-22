# Nimbus

*Fully audited 2026-07-04 to 07-06 (12 batches): every finding, fix, and design decision is in `audit/AUDIT_TODO.md` and the `HANDOFF.md` changelog. A 23-test suite runs before every scheduled board and blocks publishing on failure.*

Runs itself on GitHub (three times a day), so your office network never touches Kalshi.
You just open two web pages on your phone.

## What you get
- **Today's bets** (`index.html`): each play sized **2u / 1.5u / 1u / no bet**, listed
  highest win probability first. Probabilities come from a ~143-member multi-model ensemble
  (GFS + ECMWF + ICON + GEM) that self-calibrates: it learns each city's forecast bias and
  error spread from Kalshi's own settlements and corrects for them automatically.
- **Results tracker** (`results.html`): win/loss, P&L, ROI, Brier vs market, per-city and
  per-unit breakdowns, margin of victory, and a raw table. Wins come straight from Kalshi's
  official settlement, not a guess.

## One-time setup (about 5 minutes)
1. Create a new GitHub repo (Private is fine) and upload every file in this folder,
   keeping the structure (`kalshi_weather.py`, `.github/workflows/run.yml`, `docs/`).
2. Repo **Settings -> Pages**: Source = "Deploy from a branch", Branch = `main`, folder = `/docs`. Save.
3. Repo **Settings -> Actions -> General**: under "Workflow permissions" pick
   **Read and write permissions**. Save. (Lets the bot commit updated boards.)
4. **Actions tab -> kalshi-weather-edge -> Run workflow** to do the first run now.

Your pages will be at:
- `https://<your-user>.github.io/<repo>/`            (today's bets)
- `https://<your-user>.github.io/<repo>/results.html` (tracker)

## Put it on your iPhone
Open each URL in Safari or Chrome -> Share -> **Add to Home Screen**. Two taps to check bets.

## Schedule
Runs three times a day (Dallas summer time): ~7:17 AM (morning board, freshest overnight
models), ~4:38 PM (capture run: by then the complete midday model cycle has landed AND
Kalshi has listed tomorrow's markets, so tomorrow's lows and highs enter the tracker here
on the freshest data), and ~9:07 PM (evening board + settling results). Times sit off the
hour on purpose: GitHub delays on-the-hour crons the most, sometimes by hours. Winter times
are one hour later. Edit the `cron` lines in `.github/workflows/run.yml` to change them.
GitHub pauses schedules if the repo has no activity for 60 days (click Run workflow to wake it).

Two honesty features to know about:
- **Frozen plays.** Once a play appears on a board, the tracker scores THAT version forever,
  even if a later run would have picked differently. The tracker always matches a board you
  actually saw.
- **Data gate.** If a city's forecast comes in degraded (missing weather models, a thin
  ensemble, or a market ladder that fails a structure check), that city is sat out for the
  run and named in the header instead of being priced on bad data. The degraded forecast is
  still recorded behind the scenes, so every sit-out can be judged later against the actual
  settlement.
- **Exposure caps.** At most 6 units ride any single day and 2 units any single market,
  best plays first. The header shows how many overflow plays were trimmed.
- **Drift alarms.** The results header raises a flag when the model starts losing ground
  to the market, a probability bucket runs far off its stated rate, spreads look over- or
  under-confident, or a learned city correction jumps suddenly.
- **Stale-board banner.** If the page you are looking at was built more than 16 hours ago
  (a run or the Pages deploy failed), an orange banner says so. Do not bet from a flagged board.
  Failed runs show red in the Actions tab and commit nothing, so the last good board stays up.

## Tuning (top of kalshi_weather.py)
- `UNIT_MAP`   tier -> units (currently S=2u, A=1.5u, B=1u, C=no bet)
- `TIER_CUTS`  score thresholds for S/A/B/C
- `BANKROLL`, `BASE_UNIT_USD`, `PLAY_NET_EDGE`, `BIAS_TOL`, `MIN_OI`
- `LEAD_CAP_DAYS` caps plays 3+ days out at 1u; `HICONF_PWIN` sets the high-confidence tag
- Calibration knobs (`DRESS_SIGMA_*`, `BIAS_*`) rarely need touching; they learn on their own

## Honest use
Paper trade until the Results tab shows the model Brier consistently below the market Brier
and green P&L over 100+ bets. A city cannot earn a 2u until it has proven itself there. At a
sub-$500 bankroll this is skill-building, not income.

## Your data is safe when you change the code
All results live in `weather_state.json`, a SEPARATE file from the code. The zip you get never contains it, so replacing `kalshi_weather.py` or the dashboards never touches your history.
- Never delete `weather_state.json`. It is your entire track record.
- The workflow commits it back after every run, so your GitHub commit history is a full backup. If it is ever corrupted, restore the previous version from the repo history.
- Every bet is stamped with the model version it was logged under, and new metrics read old records defensively, so a tune starts a fresh version alongside your old results instead of overwriting them.

## What "today's results" means
The Results tab fills in when a bet SETTLES on Kalshi, which is after the day ends. Today's picks show up there tomorrow, not the same evening. That is not lost data, it is just not settled yet.
