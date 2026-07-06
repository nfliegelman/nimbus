# Section R: Reddit Deep Research Prompt (paste everything below the line into ChatGPT deep research)

Authored by audit batch 4 on 2026-07-05. Owner runs this in ChatGPT (superior Reddit index) and pastes the full output back into the Nimbus audit chat. Findings ingest at audit Batch 6.

---

I am building and paper-trading a small hobbyist model for Kalshi's daily high and low temperature markets (20 US cities, settled against NWS Climatological Report Daily products at specific stations, e.g. CLINYC Central Park, CLIMDW Chicago Midway, CLIHOU Houston Hobby, CLIAUS Austin Bergstrom). I need a deep research pass over Reddit and adjacent community sources about how people actually trade these markets. This is competitive intelligence and failure-mode research, not investment advice.

STRICT EVIDENCE RULES, follow all of them:
1. Do not summarize Reddit sentiment unless you found actual Reddit threads. Link every thread used.
2. Quote the specific comments that influenced each conclusion, with the subreddit and approximate date.
3. For every contested question, count how many comments support each viewpoint.
4. Label every claim as one of: DIRECT REDDIT EVIDENCE, BLOG OR REVIEWER OPINION, or YOUR INFERENCE. Never blend them.
5. Kalshi's fees, rules, and settlement practices have changed over time. Date-stamp every claim and flag anything older than 12 months as possibly stale.
6. If you cannot find discussion on a question, say exactly that. A confirmed absence of community discussion is a useful result. Do not fill gaps with plausible-sounding fabrication.
7. Show sources before conclusions in every section.
8. Do not use em dashes anywhere in your output.

RESEARCH QUESTIONS, work through all eight:

1. The trader landscape. Who is actively trading Kalshi weather markets? Search r/Kalshi, r/PredictionMarkets, r/weather, r/meteorology, r/algotrading, Hacker News, and public blogs or X threads. What strategies do people describe in their own words? Which claimed edges do participants say are dead, and which do they say still exist? Any estimates of how many sharp participants these markets have?

2. The wethr.net community specifically. What is wethr.net, who runs it, what tooling or data do its members use, and are there public writeups, leaderboards, or interviews? How do Reddit commenters characterize competing against them?

3. Data sources sharps actually use. Look for mentions of: NBM (National Blend of Models), MOS or LAMP guidance, HRRR, raw GEFS or ECMWF ensembles, Open-Meteo, Meteomatics, live ASOS or METAR station observations for near-settlement nowcasting, and anything else named. For each mention, quote it and note whether the user claimed it worked. I especially want evidence on: do winning traders lean on station-calibrated products (NBM, MOS) or raw model output, and does anyone describe truncating or updating forecasts intraday using the running observed max or min?

4. Settlement gotchas, per city where possible. Preliminary vs final or corrected CLI reports: has Kalshi ever settled on a number that NWS later amended, and what happened? Station-specific quirks people complain about (Central Park sensor behavior, Midway vs O'Hare confusion, Houston Hobby vs IAH, Austin Camp Mabry vs Bergstrom, Denver, Phoenix). Daylight saving oddities in the CLI day window. Any settlement disputes, voided markets, or rule changes in these series.

5. Fees and microstructure at small size. Real experiences with fill quality on temperature ladders: typical spreads by time of day, whether resting maker orders fill, whether market orders eat the book on thin ladders, and how the roughly 7 cents times price times one minus price taker fee changes which trades are worth doing. How quickly do these books react after the 00z and 12z model cycles land? Are there hours when prices are reliably stale, and do commenters name them?

6. Kalshi platform reliability. API complaints, rate limits, outage reports, and settlement timing: how long after the CLI report posts does settlement actually land, per community reports?

7. Post-mortems. Find anyone who built a temperature-market bot or systematic strategy and quit or blew up. What killed it: fees, competition, station mismatch, overfitting, settlement risk, boredom? Quote them.

8. Anything I did not ask. Surface the two or three most upvoted or most insightful threads about Kalshi weather trading overall, even if they fit none of the categories above.

OUTPUT FORMAT:
- One section per question. Each section: a table of threads used (link, subreddit, date, upvotes, comment count), then key quotes, then viewpoint counts, then a synthesis paragraph with every claim labeled per the evidence rules.
- Final section: the ten most actionable takeaways for a small-bankroll paper-trading model, ranked by expected impact, each tagged with its evidence strength (strong, moderate, thin) and the thread it came from.
- Close with an explicit list of the questions where you found little or nothing.
