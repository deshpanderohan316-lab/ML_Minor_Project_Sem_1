## 1. What the datasets contain

| File | Size | Coverage | One row = |
|---|---|---|---|
| `matches.csv` | 1,095 × 20 | 2008-2024 | one match |
| `Match_dataset.csv` | 1,243 × 14 | 2008-2026 | one match |
| `deliveries_ball_by_ball.csv` | 260,920 × 17 | the same 1,095 matches as `matches.csv` (2008-2024) | one delivery |

**`matches.csv`** holds the match summary:
- Context: season, date, city, venue, `match_type` (League, Qualifier, Eliminator, Final, etc.), team1, team2.
- Toss: `toss_winner`, `toss_decision`.
- Outcome: `winner`, `result` (runs, wickets, tie, no result), `result_margin`, `target_runs`, `target_overs`, `super_over`, `method` (D/L).
- Extras: `player_of_match` and two umpires.

**`Match_dataset.csv`** is a leaner match table with two things `matches.csv` lacks:
- Playing XIs in `team1_players` and `team2_players`.
- 148 extra matches (74 each from 2025 and 2026).

It has no `match_type` or result margin. Its `eliminator` column is actually the super-over winner.

**`deliveries_ball_by_ball.csv`** has every ball: batter, bowler, non-striker, runs, extras, wicket, dismissal type and fielder. It covers 673 batters and 530 bowlers. Innings 3-6 are super overs from 14 matches.

## 2. Are all three necessary?

They are complementary, not redundant, but they matter to different degrees.

- **`Match_dataset.csv` is essential.** It is the only file with 2025-26 and the only one with lineups. The 1,095 shared matches agree 100% with `matches.csv` on teams, toss, date and venue, so use it as your backbone.
- **`deliveries_ball_by_ball.csv` is essential if you want a good model.** Team names, toss and venue alone will give you near coin-flip accuracy. The ball-by-ball data lets you compute player and team strength (batting average, strike rate, economy, death-over bowling) and also supports a live in-match win-probability model.
- **`matches.csv` is optional but worth keeping.** Its rows are almost entirely a subset of `Match_dataset`. What you'd lose without it is:
  - `match_type`, which identifies playoffs and finals.
  - Margins and `target_runs`.
  - The `Y/N` super-over flag.

  Join it on `id = match_number`. Be careful with the match-outcome columns (see leakage in section 3).

One limitation: ball-by-ball data stops at 2024. 75 of the 261 players in 2025-26 lineups have no history in it, which is a cold-start problem. You can fill the gap with free 2025-26 ball-by-ball data from Cricsheet, or accept it and use average priors for those players.

## 3. Data issues to handle

- **Team renames:** 19 names are really 15 franchises. Delhi Daredevils became Delhi Capitals, Kings XI Punjab became Punjab Kings, Royal Challengers Bangalore became Bengaluru, and "Rising Pune Supergiant(s)" is a duplicate spelling. Deccan Chargers and Sunrisers Hyderabad are separate franchises, so don't merge them.
- **Venue names:** 60 raw names collapse to about 42 just by dropping the city suffix (e.g. "Wankhede Stadium" vs "Wankhede Stadium, Mumbai"). True renames like Feroz Shah Kotla → Arun Jaitley Stadium need a manual mapping.
- **Season labels** are inconsistent ("2007/08", "2009/10", "2020/21" next to plain years). Derive the year from the date.
- **Ties and no-results:** `Match_dataset` leaves `winner` empty for 25 rows (16 ties and 9 no-results). For the 16 ties, the super-over winner is in `eliminator`. Drop no-results and decide whether to keep ties.
- **Row order:** `Match_dataset` is shuffled. Sort by date before building any "past form" feature, or you'll leak the future.
- **Lineup size:** it is 11 until 2022 and 12 from 2023 (Impact Player rule), so treat it as an era shift.
- **Missing values:** the 51 missing cities are all UAE venues (Dubai and Sharjah). The mostly-empty dismissal columns in `deliveries` are legitimate (they only fill on wicket balls).
- **Leakage columns:** never feed `player_of_match`, `result_margin`, `target_runs`, umpires or anything from the same match's deliveries into a pre-match model.
- **Class balance:** it is nearly even. team1 wins 50.9%, the toss winner wins 50.9%, and the chasing side wins 53.7%. So your baseline is about 50-54%.
