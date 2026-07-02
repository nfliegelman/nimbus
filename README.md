# Kalshi Weather Edge

Runs itself on GitHub (twice a day), so your office network never touches Kalshi.
You just open two web pages on your phone.

## What you get
- **Today's bets** (`index.html`): each play sized **2u / 1.5u / 1u / no bet** from a
  confidence score (edge x forecast lead x ensemble tightness x that city's track record).
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
Runs at 12:00 and 02:00 UTC (~7 AM and 9 PM Dallas in summer). Edit the `cron` lines in
`.github/workflows/run.yml` to change times. Notes: GitHub can delay scheduled runs by a few
minutes, and it pauses schedules if the repo has no activity for 60 days (just push or click
Run workflow to wake it).

## Tuning (top of kalshi_weather.py)
- `UNIT_MAP`   tier -> units (currently S=2u, A=1.5u, B=1u, C=no bet)
- `TIER_CUTS`  score thresholds for S/A/B/C
- `BANKROLL`, `BASE_UNIT_USD`, `PLAY_NET_EDGE`, `BIAS_TOL`, `MIN_OI`

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
