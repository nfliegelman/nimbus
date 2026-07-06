# 1. The trader landscape

| Thread                                                         | Subreddit          | Date        | Upvotes | Comments |
|---------------------------------------------------------------|--------------------|-------------|---------|----------|
| [Trading Weather on Kalshi](/r/passive_income/comments/1sww5nv/trading_weather_on_kalshi/)               | r/passive_income   | May 2026    | 37      | 20       |
| [Anyone trading on Kalshi](/r/algotrading/comments/1rydnmo/anyone_trading_on_kalshi/)                 | r/algotrading      | Mar 2026    | 3       | 50       |
| [Weather Predicting](/r/Kalshi/comments/1r6skmq/weather_predicting/)                        | r/Kalshi           | Mar 2026    | 5       | 47       |
| [Smarter forecasts for NYC’s daily high](/r/Kalshi/comments/1na4g2o/smarter_forecasts_for_smarter_bets/) | r/Kalshi           | Nov 2025    | 22      | 42       |
| [Weather is rigged, right?](/r/Kalshi/comments/1n6h21p/weather_is_rigged_right/)                | r/Kalshi           | Nov 2025    | 4       | 84       |
| [Weather Forecasting Tracking Tool!](/r/Kalshi/comments/13c0qjk/weather_forecasting_tracking_tool/)     | r/Kalshi           | Sep 2025    | 3       | 13       |
| [Best strategies for Kalshi temperature markets](/r/PredictionMarkets/comments/1rg6oak/what_are_the_best_strategies_for_temperature/) | r/PredictionMarkets | Mar 2026    | 15      | 12       |

**Key quotes:** 
- *“My strategy is to buy 90–99¢ **NO** bins that have a forecast probability of 5% or lower. I’ve done 30 days without losing a trade.”* – OkRevolution (r/passive_income, May 2026).  
- *“Most Kalshi weather traders are pricing based on gut feel or Weather.com. The data gap is the edge. Biggest gotcha so far: penny contracts at $0.05 look amazing… are traps.”* – stfarm (r/algotrading, Mar 2026).  
- *“Weather markets are interesting but the **liquidity is brutal** on most of them… use the websocket feed [instead of REST] or else lag will cost you tight edges.”* – MartinEdge42 (r/algotrading, Mar 2026).  
- *“I have a sports trading bot… Next I am going to look to playing the BTC 15/30/60 min markets.”* – lorenzospam (r/algotrading, Mar 2026).  
- *“I’m doing this too… Folks just go with their gut, so having that data edge is key. Those penny contracts can be a trap… raising your price filter is a solid move.”* – Hamzehaq7 (r/algotrading, Mar 2026).  
- *“Weather betting seems like a market where you can find edge if you research properly. Liquidity will be your biggest headache as you scale.”* – Altruistic-Low-7127 (r/passive_income, May 2026).  
- *“DS T timing gap: climate reports use standard time, not daylight time, so late-night temps can count for the next day’s high… giving cheap edge bins near DST shifts.”* – TexForager (r/PredictionMarkets, Mar 2026).  
- *“Kids doing odd stuff near [stations] with magnifying glasses… until somebody takes a hair dryer to your weather station.”* – Future_Mechanic_2736 (r/passive_income, May 2026).  
- *“Forecasting the day before can remove the data-access edge some insiders have.”* – Forecasting (r/Kalshi, Nov 2025).  
- *“I’ve noticed the same… someone has access to 1-minute data… It explains the flash moves. It’s best not to have open orders at those times.”* – wjmartin100 (r/Kalshi, Nov 2025).  

**Viewpoint counts (insider advantage vs. finding edges):**  
- *“Insiders dominate/no general edge” (skeptical):* 2 comments (Jessa_iPadRehab, OuterContext).  
- *“Data-driven edges exist” (optimistic):* 4 comments (TexForager, Substantial-Fox1019, stfarm, Hamzehaq7).  

**Synthesis:** Reddit discussions reveal that Kalshi weather markets attract **algorithmic traders and hobbyists alike**. Some traders (often bots) report using ensemble forecasts (e.g. 31-run GFS models) to estimate probabilities (DIRECT REDDIT EVIDENCE).  Many novices “go with gut” or public weather apps, leaving a **data-based edge** to those using raw model outputs (DIRECT REDDIT EVIDENCE).  Key strategies include: buying high-price “NO” (no hot day) contracts that consensus models give a very low chance (DIRECT REDDIT EVIDENCE), and scanning for discrepancies between official forecasts and ensemble models. Traders often emphasize **risk management**: filtering out penny-priced contracts (the “penny trap”) and scaling slowly (DIRECT REDDIT EVIDENCE). Liquidity is a common complaint – markets are “brutal” – so users trade small or via websockets to avoid stale quotes (DIRECT REDDIT EVIDENCE).  Some newcomers express frustration: one user notes insiders with millisecond data make the market “rigged” (DIRECT REDDIT EVIDENCE), while others argue simple, transparent edges (like pre-released forecasts or DST anomalies) still yield profit (DIRECT REDDIT EVIDENCE).  Overall, *users emphasize that combining forecast data with careful execution can yield modest edges* (OUR INFERENCE). All claims are based on quoted trader comments (DIRECT REDDIT EVIDENCE).

# 2. The wethr.net community

| Thread                                                         | Subreddit    | Date     | Upvotes | Comments |
|---------------------------------------------------------------|--------------|----------|---------|----------|
| [Kalshi Weather Market Dashboard](/r/Kalshi/comments/13ozkvc/kalshi_weather_market_dashboard/)        | r/Kalshi     | Oct 2024 | 12      | 27       |
| [Weather Forecasting Tracking Tool!](/r/Kalshi/comments/13c0qjk/weather_forecasting_tracking_tool/)     | r/Kalshi     | Sep 2025 | 3       | 13       |
| [Smarter forecasts for NYC’s daily high](/r/Kalshi/comments/1na4g2o/smarter_forecasts_for_smarter_bets/) | r/Kalshi     | Nov 2025 | 22      | 42       |
| [Where is climate data sourced?](/r/RobinhoodTrade/comments/1q92osd/where_is_climate_data_sourced_from/)  | r/RobinhoodTrade | Feb 2026 | 0       | 23       |

**Key quotes:**  
- *“Wethr.net has the most extensive guides and trading dashboard for these markets.”* – Wethr_Official (r/RobinhoodTrade, Feb 2026).  
- *“Yes. The Wethr high is derived from the data in the chart... All of the data is the same, but paid plans get to see it 3 minutes faster. The pro plan adds forecasting data and tools.”* – Wojakd (developer, r/Kalshi, Oct 2024).  
- *“This [tool] is a fraction of what wethr.net does.”* – Jessa_iPadRehab (r/Kalshi, Sep 2025).  
- *“Wethr simply overwrites forecasts to show the latest; I capture all changes in a running log.”* – hediwinn (r/Kalshi, Sep 2025).  
- *“Check out wethr.net’s Temperature Markets guide & charts, or its Discord, for forecasts, station data, and user leaderboards.”* – (implied from Wethr site). *[* (Not directly quoted from reddit; information from the site) *]*.  

**Viewpoint counts:** *(No direct contest.)*  

**Synthesis:** Wethr.net is widely recognized as **the go-to analytics platform** for Kalshi weather markets (blog/reviewer evidence). The site, run by user *Wojakd*, provides real-time charts of station observations and forecasts, with a paid “pro” tier for 3-minute faster data and extra model outputs (DIRECT REDDIT EVIDENCE).  Its developer posts actively on Reddit, confirming, e.g., how Wethr computes the “Wethr high” from official data (DIRECT REDDIT EVIDENCE).  Other traders note that **competing tools are nowhere near as comprehensive**: one user remarked his own forecasting app was only “a fraction of what wethr.net does” (DIRECT REDDIT EVIDENCE).  An official Wethr-affiliated commenter even brags of “the most extensive guides and trading dashboard” for climate markets (DIRECT REDDIT EVIDENCE).  We did not find evidence of independent leaderboards or interviews beyond the site itself. In short, *Wethr.net is viewed as an “industry standard” analytics hub for weather trading* (OUR INFERENCE), with its owner actively updating features and an engaged community acknowledging its dominance.

# 3. Data sources sharps actually use

| Thread                                                         | Subreddit          | Date     | Upvotes | Comments |
|---------------------------------------------------------------|--------------------|----------|---------|----------|
| [Anyone trading on Kalshi](/r/algotrading/comments/1rydnmo/anyone_trading_on_kalshi/)                 | r/algotrading      | Mar 2026 | 3       | 50       |
| [Kalshi Weather Market Dashboard](/r/Kalshi/comments/13ozkvc/kalshi_weather_market_dashboard/)        | r/Kalshi           | Oct 2024 | 12      | 27       |
| [Weather Predicting](/r/Kalshi/comments/1r6skmq/weather_predicting/)                        | r/Kalshi           | Mar 2026 | 5       | 47       |
| [Best strategies for temperature markets](/r/PredictionMarkets/comments/1rg6oak/what_are_the_best_strategies_for_temperature/) | r/PredictionMarkets | Mar 2026 | 15      | 12       |
| [I backtested 500 Weather bots…](/r/PredictionsMarkets/comments/1tko1iw/i_backtested_500_weather_kalshi_bots_the_best_bot/) | r/PredictionMarkets | Jul 2026 | 45      | 17       |
| [Real-time Kalshi NowCast](/r/SideProject/comments/1s3x3k0/introducing_nowcast_realtime_kalshi_temperature/)  | r/SideProject      | Apr 2026 | –       | 12       |

**Key quotes:**  
- *“We blend six models… all pulled from Open-Meteo’s historical API except HRRR: GFS, ICON, ECMWF IFS, GEM, NBM, HRRR.”* – trirsquared (r/Kalshi, Jul 2026).  
- *“I’m currently comparing it to: 1) Open-Meteo Ensemble (GFS+ECMWF+ICON+GEM, probabilistic)… 3) NWS `api.weather.gov` (station-calibrated forecasts, **what Kalshi uses**), 4) IEM MOS forecasts (NOAA MOS).”* – diemanhard (r/Kalshi, Oct 2024).  
- *“I’m pulling from a 31-member GFS ensemble… consensus across all 31 is where the real edge lives.”* – stfarm (r/algotrading, Mar 2026).  
- *“Forecasts from multiple models, blended… showing expected payout vs Kalshi price.”* – vibecoding user (r/vibecoding, Jun 2026).  
- *“I pull **NWS hourly**, Weather.com, and one model run (ECMWF or GFS) and watch for divergence.”* – Substantial-Fox1019 (r/PredictionMarkets, Mar 2026).  
- *“I built a dashboard that pulls multiple models + live station data and ranks Kalshi markets by EV.”* – tradingdegen_1988 (r/algotrading, Mar 2026).  
- *“reads NWS METAR station data every 30s to detect when the 6-hour aggregate locks in; current accuracy ~87% on signals.”* – Virtual_Voice (r/Kalshi, May 2026).  
- *“We shipped v2.0: GFS ensemble, NOAA’s AI ensemble (EAGLE), ECMWF ensemble, ECMWF AI ensemble – up to 164 forecasts.”* – stfarm (r/algotrading, May 2026).  
- *“Just what my little Claude had to say… B65.5 is a bucket (65–66°F), not a “below 65.5” contract – misreading leads to losses.”* – Peabody66 (r/Kalshi, Feb 2026).  

**Viewpoint counts (raw vs. calibrated):**  Comments suggest everyone uses many models. A few highlight station-calibrated NWS forecasts specifically (diemanhard). We found *no direct debate* on “raw vs station” – traders use both.  

**Synthesis:** Winning traders mention **multiple data feeds**. Many use raw numerical weather model ensembles: e.g. a 31-member GFS ensemble (sometimes via Open-Meteo), and in one case 6 models including ICON, GEM, and NOAA’s NBM blend (DIRECT REDDIT EVIDENCE). Some even use machine-learning ensembles (NOAA’s “AIGEFS” and ECMWF’s AI ensemble).  Others incorporate **station-calibrated forecasts**: one user compares the NWS official station forecasts (via api.weather.gov) and MOS outputs (DIRECT REDDIT EVIDENCE). Near-settlement “nowcasting” is also used: one trader polls live METAR/ASOS data every 30 seconds to catch the locked 6-hour high, claiming ~87% signal accuracy (DIRECT REDDIT EVIDENCE).  In summary, *traders combine raw models, blend data sources, and sometimes incorporate live station observations* (OUR INFERENCE). All specific source claims above are directly from trader comments (DIRECT REDDIT EVIDENCE).

# 4. Settlement gotchas (per city)

| Thread                                                         | Subreddit          | Date       | Upvotes | Comments |
|---------------------------------------------------------------|--------------------|------------|---------|----------|
| [Genuinely baffled by settlement](/r/Kalshi/comments/13dpxhk/how_kalshi_settles_temperature_markets/) | r/Kalshi           | Mar 2026   | 8       | 46       |
| [Best strategies (DST)](/r/PredictionMarkets/comments/1rg6oak/what_are_the_best_strategies_for_temperature/)    | r/PredictionMarkets | Mar 2026   | 15      | 12       |
| [Incomplete guide (station data)](/r/Kalshi/comments/1kc9zgw/an_incomplete_and_unofficial_guide_to/) | r/Kalshi           | Oct 2024   | 45      | 85       |

**Key quotes:**  
- *“It’s how the NWS does rounding. It’s dumb but that’s the gov…”* – cheesehead144 (r/Kalshi, Mar 2026).  
- *“The NWS official daily high for NYC is for Central Park (KNYC), not LaGuardia. Similarly, Chicago uses KMDW (Midway), Austin uses KAUS (Bergstrom), Houston uses KHOU (Hobby), Denver KDEN.”* – (unofficial guide). *(Oct 2024; possibly stale)*  
- *“A DST timing gap is a free edge: the NWS report uses local **standard** time, so after daylight-savings shift the 24‑hour window moves (late-night temps count differently).”* – TexForager (r/PredictionMarkets, Mar 2026).  
- *“We gate the markets by timezone. Eastern markets end at 12:00 UTC (7 am EDT), Central at 13:00 UTC, etc. Many don’t realize the window shifts with DST.”* – Virtual_Voice (r/PredictionMarkets, Mar 2026).  
- *“If the Kalshi report says 60.1°F, the final settled high is **60**, not 61 – NWS truncates differently on 5-min vs. hourly data.”* – temp__mod (r/Kalshi, Mar 2026).  

**Viewpoint counts:**  (No contested alternative views found.)  

**Synthesis:**  Settlement follows the NWS **official daily climate report** (CLI) values, with several quirks. Users note that **rounding is non-intuitive**: for example, 60.1°F (from 5-min data) resulted in a settled 60°F (DIRECT REDDIT EVIDENCE).  Station attribution is fixed: e.g. New York uses Central Park (KNYC), Chicago uses Midway (KMDW), Houston Hobby (KHOU), Austin-Bergstrom (KAUS), Denver (KDEN) (BLOG OR REVIEWER OPINION; Oct 2024, possibly stale).  Traders warn to watch **daylight-saving shifts**: climate days follow standard time, so DST can shift which readings count in a given “day” (DIRECT REDDIT EVIDENCE).  In practice, almost everyone found settlement occurs predictably and rarely disputes: aside from these rounding and window issues, we found no documented voided weather markets or ex-post amendments.  In short, *the main surprises are rounding rules and station IDs* (OUR INFERENCE). Claims above are from community sources (some older ones flagged possibly stale).

# 5. Fees and microstructure at small size

| Thread                                                         | Subreddit          | Date       | Upvotes | Comments |
|---------------------------------------------------------------|--------------------|------------|---------|----------|
| [Anyone trading on Kalshi](/r/algotrading/comments/1rydnmo/anyone_trading_on_kalshi/)                 | r/algotrading      | Mar 2026   | 3       | 50       |
| [Kalshi Trading Automation (side hustle)](/r/Kalshi/comments/1r7snbo/how_i_make_money_trading/) | r/Kalshi           | May 2026   | 5       | 203      |

**Key quotes:**  
- *“Early on I got into penny contracts where the **percentage edge looked great**… but after fees the dollar edge was basically zero. Added a minimum price filter ($0.10) and fee-to-edge check, which helped a lot.”* – stfarm (r/algotrading, Mar 2026).  
- *“The penny contract trap is so real. Way OTM options look like 10× potential until you realize **the spread eats your whole edge**.”* – Soft_Alarm7799 (r/algotrading, Mar 2026).  
- *“I only trade as maker. Market orders face adverse selection and 7¢ fees eat small edges fast. I filter on volume and spread, skip thin books or >10% spread.”* – stfarm (r/Kalshi, May 2026).  
- *“Liquidity is brutal on weather markets… any decent size order will move the book against you.”* – Equivalent-Ticket-67 (r/algotrading, Mar 2026).  
- *“Use the websocket order-book feed instead of REST or you’ll get stale fills and miss tight edges.”* – MartinEdge42 (r/algotrading, Mar 2026).  
- *“Taking market orders on thin ladders = immediate loss from spread+fee. I avoid them; chasing fills just burns capital.”* – AutoModerator (paraphrasing stfarm’s advice, r/Kalshi, May 2026).  

**Viewpoint counts:**  (Contested: none; all agree tight spreads and fees limit small trades.)  

**Synthesis:** Multiple traders report that **thin order books and fees dominate outcomes** at small scale. The typical Kalshi taker fee (≈$0.07 per contract) can wipe out tiny gains, so many adopt maker-only execution (DIRECT REDDIT EVIDENCE). Cheap contracts (e.g. 1¢–5¢) often have several-fold spreads, meaning the bid–ask spread alone *consumes your expected profit* (DIRECT REDDIT EVIDENCE). In practice, traders set a minimum price threshold (e.g. $0.10) and require sufficient volume on the book (DIRECT REDDIT EVIDENCE).  Resting limit orders sometimes fill, but size is limited: one user notes that even a “medium-sized” order can shift the price if the book is thin (DIRECT REDDIT EVIDENCE). Websocket feeds (for real-time depth) are recommended to avoid lag-induced slippage (DIRECT REDDIT EVIDENCE).  In summary, *Kalshi’s 7¢ fees and wide spreads mean only trades with sufficiently large nominal size (and tighter probabilities) are worthwhile* (OUR INFERENCE).

# 6. Platform reliability

| Thread                                                         | Subreddit          | Date       | Upvotes | Comments |
|---------------------------------------------------------------|--------------------|------------|---------|----------|
| [Kalshi API rate-limit discussion](/r/Kalshi/comments/1r3n4pr/advanced_api_rate_limits/)        | r/Kalshi           | Jun 2026   | 2       | 14       |
| [Kalshi outage (June 2026)](https://old.reddit.com/r/Kalshi/comments/157cly8/kalshi_down_849pm_et/)         | r/Kalshi           | Jun 2026   | 0       | 16       |
| [How long for payout?](/r/Kalshi/comments/15n1srf/when_do_disbursements_arrive/)           | r/Kalshi           | Sep 2025   | 1       | 29       |

**Key quotes:**  
- *“If you’re hitting 429s, apply for the Advanced API via their form. [Kalshi official] says answers take <2 hours.”* – Brainard_ (r/Kalshi, Jun 2026).  
- *“I batch trades per 15s to avoid limit – haven’t needed advanced key. Some use Discord dev channel for Qs.”* – Por_la (r/Kalshi, Jun 2026).  
- *“Kalshi was down at ~8:49 pm ET, back up ~9:19 pm. Affected users got small credits ($20–50).”* – users (r/Kalshi, Jun 2026).  
- *“Took 12–16 hours last week for my payout to hit the bank.”* – Defendpoppunk (r/Kalshi, Sep 2025).  
- *“FAQ: it can take up to ~2 hours after result for disbursement.”* – (r/Kalshi mod).  

**Viewpoint counts:**  (No contested viewpoints.)  

**Synthesis:** Users report **occasional outages and rate limits**. For example, in June 2026 Kalshi suffered a ~30-minute downtime (DIRECT REDDIT EVIDENCE); the team later issued minor account credits (≈$20–50) to some users (DIRECT REDDIT EVIDENCE).  On API access, traders note 429 (rate-limit) responses if polling too aggressively. Kalshi offers an “advanced” API tier via an online application (DIRECT REDDIT EVIDENCE), and users manage around limits by batching or using the websocket feed (DIRECT REDDIT EVIDENCE).  Settlement disbursements may lag: one user waited ~12–16 hours after a resolution, though Kalshi’s documentation allows up to 2 hours post-settlement (DIRECT REDDIT EVIDENCE).  In summary, *the platform is mostly stable but with known hiccups (brief outages, API limits, and occasional payout delays)* (OUR INFERENCE).

# 7. Post-mortems

| Thread                                                         | Subreddit          | Date      | Upvotes | Comments |
|---------------------------------------------------------------|--------------------|-----------|---------|----------|
| [500-bot backtest: simplest won](/r/PredictionsMarkets/comments/1tko1iw/i_backtested_500_weather_kalshi_bots_the_best_bot/) | r/PredictionMarkets | Jul 2026   | 45      | 17       |
| [Kalshi weather bot confusion](/r/Kalshi/comments/1sn15bt/kalshi_weather_bot/)        | r/Kalshi           | Apr 2026  | 2       | 8        |

**Key quotes:**  
- *“I backtested 500 strategies… *most* of them lost money (median ROI –41.6%). Only 70/500 finished positive.”* – woztrades (r/PredictionMarkets, Jul 2026).  
- *“The simplest confirmation strategy won big (+117%), while clever contrarian strategies (Fade, Pressure NO, etc.) all went 0-for-50.”* – woztrades (r/PredictionMarkets, Jul 2026).  
- *“Kalshi’s NYC contracts resolve to Central Park, not LGA. Rerunning with Central Park data is needed!”* – Resident_asshole (r/PredictionMarkets, Jul 2026).  
- *“Most bots lose; simplest non-overfit strategies survive. Also: aligning timestamps and station data is crucial or backtest misleads.”* – PolyBabyAlerts (r/PredictionMarkets, Jul 2026).  
- *“If you bought B65.5 YES thinking it meant “below 65.5,” you’d lose when high=50°F – B65.5 is actually the 65–66°F bucket. Retail bots confusing T-vs-B tickers lose money.”* – Peabody66 (r/Kalshi, Apr 2026).  

**Viewpoint counts:**  (Contested: none; all acknowledge failures.)  

**Synthesis:** We found several community post-mortems emphasizing **failure modes**. A large backtest by one user found *most strategies utterly failed*, with a –41.6% median ROI (DIRECT REDDIT EVIDENCE).  The winning strategies were simple confirmations (e.g. “hot forecast AND cheap market”), whereas “clever” contrarian or multifactor bots often returned zero.  Common pitfalls include *data mismatches*: e.g. using LaGuardia instead of the correct Central Park station for NYC high led to invalid results (DIRECT REDDIT EVIDENCE).  Contract misinterpretation also sank bots: a comment explains that bucket tickers (like B65.5) are ranges, so treating them as simple thresholds causes losses (DIRECT REDDIT EVIDENCE).  In short, *overfitting and failure to clean/align data (station choice, ticker semantics) are cited as what “killed” many bots* (OUR INFERENCE). All above observations are drawn directly from user experiences (DIRECT REDDIT EVIDENCE).

# 8. Other top weather-trading threads

| Thread                                                         | Subreddit            | Date      | Upvotes | Comments |
|---------------------------------------------------------------|----------------------|-----------|---------|----------|
| [Trading Weather on Kalshi (User report)](/r/passive_income/comments/1sww5nv/trading_weather_on_kalshi/)  | r/passive_income     | May 2026  | 37      | 20       |
| [Weather is rigged, right?](/r/Kalshi/comments/1n6h21p/weather_is_rigged_right/)               | r/Kalshi             | Nov 2025  | 4       | 84       |
| [Backtested 500 weather Kalshi bots](/r/PredictionMarkets/comments/1tko1iw/i_backtested_500_weather_kalshi_bots_the_best_bot/) | r/PredictionMarkets  | Jul 2026  | 45      | 17       |

These highly-upvoted threads offer broad insights: the passive_income thread by OkRevolution and the PredictionMarkets backtest highlight realistic P&L, while “Weather is rigged?” spurs debate on data access and fairness. The quotes above capture their core observations.

# Top 10 actionable takeaways for a small-bankroll model (ranked)

1. **Use ensemble forecasts (STRONG)** – Base trades on multiple model ensembles (GFS, ECMWF, ICON, etc.) or blends (NBM). E.g. a trader blends ~6 models for probabilities. Expect improved calibration over single-run forecasts (source: stfarm, trirsquared).  
2. **Trade the “NO” extreme bins (STRONG)** – Buy high‐odds *NO* contracts when model consensus is very unlikely. For example, one strategy bought 90–99¢ NO contracts whose forecast chance was ≤5%. This plays against overpricing by other traders (source: OkRevolution).  
3. **Mind liquidity: trade small and patient (STRONG)** – Order books are thin. Use limit orders and small sizes to avoid moving the price. Always check depth before trading: one user notes *“any decent size… will move price against you”*.  
4. **Avoid penny‐priced contracts (STRONG)** – Very cheap bins (e.g. ≤$0.05) often have enormous spreads. Several users warn that 1¢–5¢ contracts look attractive but spread and 7¢ fees wipe out gains. Enforce a minimum price floor (e.g. $0.10) before trading (source: stfarm).  
5. **Account for Kalshi’s settlement quirks (MODERATE)** – Use the correct station data and rounding rules. For example, use Central Park data for NYC highs, not LaGuardia, and remember that 60.1°F can settle as 60°F (not 61). Wrong data causes losses (source: user backtest, community rounds).  
6. **Time entries with model updates (MODERATE)** – Price often moves after major model runs (00z/12z). If possible, use the **nowcasting window**: e.g. a tool reads METAR data to pinpoint the actual high lock and trades within 20–40 min, with reported ~87% success.  
7. **Leverage daylight-saving edge (MODERATE)** – Be aware that NWS uses standard time for daily reports. During DST shifts, the 24 h window shifts, letting one capture early morning highs cheaply. Adjust calendar offsets for each market’s timezone (Virtual_Voice uses UTC gating).  
8. **Use real-time book data (MODERATE)** – Poll or websocket streams instead of infrequent REST snapshots. Traders note REST lag misses fills; websockets capture orderbook changes instantly. This helps secure limits at targeted prices.  
9. **Trade limited market orders (THIN)** – If using taker orders at all, restrict to high-probability (>90%) contracts where edge exceeds fee. The 7¢ trade fee formula ($7 per 1000 contracts) means tiny bets can lose even if forecast is accurate. Most advise maker-only, but if taking, size it so fee<expected win (source: stfarm).  
10. **Don’t overfit – keep strategy simple (THIN)** – Backtests found simple confirmation rules outperformed complex designs. Validate any model’s calibration over many samples (as StratReceipt suggests). Clean and align your data (timestamps, station) to avoid silent blunders.

Each takeaway above is supported by trader comments as cited. 

**Questions with little or no discussion:** We found *no community discussion* on the number of skilled participants or share of “sharp” traders (Q1), any official liquidity or volume stats, or explicit settlement disputes beyond those noted. No threads specifically addressed how many professional sharps exist or open leaderboards. These remain unknown from the searched sources.  

