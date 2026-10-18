## 4. Suggested methodology

**Reframe the target.** "IPL winner" can mean the season champion, but you only have about 19 champion labels, which is too few to train on. The stronger design has two layers:

1. **Match-level model** that outputs a calibrated win probability for Team A vs Team B.
2. **Monte Carlo season simulator** that plays out the fixtures with those probabilities, applies the points table and playoffs (top 4, Qualifier 1, Eliminator, Qualifier 2, Final), and repeats it about 10,000 times. The share of simulations each team wins is its championship probability.

**Step 1: Clean and integrate.** Standardize teams and venues, use `Match_dataset` as the spine, merge `matches.csv` for `match_type`, and sort by date.

**Step 2: Feature engineering, using only information from before each match.**
- **Team form:** an Elo rating (with partial reset between seasons), rolling win % over the last 5 and 10 matches, head-to-head record.
- **Squad strength:** per-player batting and bowling ratings from past deliveries, with recency weighting and shrinkage toward the league average for players with few balls. Aggregate over the playing XI (top-order rating, bowling rating, number of all-rounders, death-over economy).
- **Venue and context:** home advantage, venue average first-innings score, chase win % at the ground, toss decision × venue, match number in the season, playoff flag, rest days.
- **Era:** a flag for the Impact Player rule.

Frame each match as A vs B using difference features, and add a swapped copy of every match so the model can't learn the team1/team2 ordering.

**Step 3: Modeling.** Build up in stages:
- Baselines: always pick the higher Elo, or the toss winner.
- Logistic regression.
- Random forest.
- Gradient boosting (XGBoost, LightGBM or CatBoost).
- Calibrate the probabilities (Platt or isotonic), because the simulator depends on them being trustworthy.

**Step 4: Validation.** Never use random K-fold, because it lets the model see the future.
- Use walk-forward validation: train on seasons up to year N, test on year N+1.
- Hold out 2025-26 as the final test.
- Report accuracy, log loss, Brier score, ROC-AUC and a calibration plot.
- Be realistic: pre-match cricket models typically reach the high 50s to mid 60s in accuracy. Anything above about 70% should make you suspect leakage.

**Step 5: Season simulation.** Backtest by simulating past seasons from their actual fixtures and checking how highly the real champion was ranked. With so few seasons this is illustrative rather than statistical proof, so rely on match-level metrics for rigor.

**Step 6: Explainability.** Use SHAP or feature importance to show what drives wins (toss, venue, bowling depth, form), which makes the project more insightful than a pure accuracy chase.

**Step 7: Deliverable.** A Streamlit or Gradio app where you pick two teams, a venue and lineups to get a win probability, plus a "championship probability" bar chart from the simulator.

**Stretch goal, in-match prediction.** Use `deliveries` to build a live win-probability model (runs, wickets, balls left, required run rate, batting-first or chasing). It uses the ball-by-ball data to the fullest and makes a strong showcase.
