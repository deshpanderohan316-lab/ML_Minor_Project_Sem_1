# IPL Winner Prediction

Predict who wins IPL matches, and from that, who wins the tournament, using 18 years of match and ball-by-ball data (2008–2026).

> **Project status:** the **data-cleaning stage is complete and tested**. Feature engineering, modelling, the season simulator and the app are planned and described in the [Roadmap](#roadmap). No model has been trained yet, so this repository makes no accuracy claims.

---

## Table of contents

1. [Approach](#approach)
2. [The data](#the-data)
3. [Quick start](#quick-start)
4. [What the cleaning script produces](#what-the-cleaning-script-produces)
5. [Using the cleaned data safely](#using-the-cleaned-data-safely)
6. [Roadmap](#roadmap)
7. [Project structure](#project-structure)
8. [Known limitations](#known-limitations)
9. [Troubleshooting](#troubleshooting)
10. [Data source and license](#data-source-and-license)

---

## Approach

"IPL winner" can mean the season champion, but there are only about 19 champions in the data, which is far too few to train a model on. So the project is split into two layers:

1. **Match-level model:** a calibrated probability that Team A beats Team B, using only information known *before* the match.
2. **Season simulator (Monte Carlo):** play the whole tournament thousands of times using those probabilities, apply the points-table and playoff rules, and count how often each team wins. That share is the champion probability.

An optional third layer is a live in-match win-probability model built from the ball-by-ball data.

## The data

Three raw CSV files are required (names are case-sensitive):

| File | Rows | Coverage | One row is | Notes |
|---|---|---|---|---|
| `matches.csv` | 1,095 | 2008–2024 | one match | Has `match_type` (league, qualifier, final), margins, `target_runs`. |
| `Match_dataset.csv` | 1,243 | 2008–2026 | one match | Adds the **playing XIs** and the 2025–26 seasons. Row order is shuffled. |
| `deliveries_ball_by_ball.csv` | 260,920 | the same 1,095 matches as `matches.csv` | one delivery | Ball-by-ball stops at 2024. |

The files overlap rather than duplicate each other. `Match_dataset.csv` is used as the backbone, and the other two add what it lacks. Details are in [`data_cleaning_explained.md`](data_cleaning_explained.md).

## Quick start

**Requirements:** Python 3.10 or newer, `pandas`, `numpy`. The script was tested on Python 3.12 with pandas 2.2.3 and pandas 3.0.2, and both versions produce identical output. Older pandas versions are untested.

```bash
pip install pandas numpy
```

**1. Put the three raw files in `data/raw/`**

```
data/raw/matches.csv
data/raw/Match_dataset.csv
data/raw/deliveries_ball_by_ball.csv
```

**2. Run the cleaning script**

```bash
python clean_data.py --input-dir data/raw --output-dir data/processed
```

**3. Check the result.** The script prints a summary and writes `data/processed/cleaning_report.json`. The expected counts are:

| Check | Expected |
|---|---|
| Raw shapes | 1,095 / 1,243 / 260,920 rows |
| Team names | 19 raw names reduced to 15 franchises |
| Venue names | 60 raw names reduced to 36 grounds |
| `matches_clean.csv` | 1,243 matches |
| `matches_model.csv` | 1,234 matches (the 9 no-results removed) |
| `deliveries_clean.csv` | 260,759 balls (161 super-over balls moved out) |

If any built-in assertion fails, the script stops with a message instead of producing wrong data.

## What the cleaning script produces

| File | Rows | Purpose |
|---|---|---|
| `matches_clean.csv` | 1,243 | Every match, with all flags and the `post_` columns. Use for exploration. |
| `matches_model.csv` | 1,234 | Usable matches only, with **no** `post_` columns. Use for modelling. Label: `team1_won`. |
| `deliveries_clean.csv` | 260,759 | Innings 1–2 with helper columns for batting and bowling statistics. |
| `deliveries_super_over.csv` | 161 | Super-over balls (innings 3 and above), kept separate. |
| `player_name_review.csv` | 93 | Possible duplicate player names, for **manual** review. Never auto-merged. |
| `cleaning_report.json` | | Counts of every fix and check. |

**What it fixes, in short:** standardises renamed teams and duplicated venue and city names, parses dates and sorts matches in time order, merges the two match files and cross-checks them, fills in `match_type` for 2025–26 using a validated rule, resolves tie and no-result winners, separates super overs, flags impossible overs in the source data, and marks every post-match column with a `post_` prefix. The reasoning, and the alternatives that were rejected, are in [`data_cleaning_explained.md`](data_cleaning_explained.md).

### Key columns

**`matches_model.csv`**

| Column | Meaning |
|---|---|
| `match_id`, `date`, `season`, `match_idx` | Identity and chronological order. `match_idx` is the global time order; use it for time-based splits. |
| `team1`, `team2`, `venue`, `city` | Standardised team, ground and city names. |
| `toss_winner`, `toss_decision`, `batting_first` | Known after the toss, before the first ball. |
| `team1_players`, `team2_players` | Playing XI, joined with `\|` (11 players, or 12 from 2023). |
| `match_type`, `is_playoff`, `match_type_source` | Stage of the tournament. `match_type_source` says whether it came from `matches.csv` or from the validated rule. |
| `has_ball_by_ball` | `False` for 2025–26, which have no ball-by-ball data. |
| `team1_won` | **The label.** 1 if `team1` won, else 0. |

**`deliveries_clean.csv`** keeps the original columns and adds: `is_legal_ball`, `bowler_runs` (excludes byes and leg-byes), `team_wicket`, `bowler_wicket`, `legal_balls_cum`, `runs_cum`, `wickets_cum`, `over_has_extra_legal_ball`, `date` and `season`.

## Using the cleaned data safely

- **Never use outcome columns as features.** That means everything prefixed `post_` (not in `matches_model.csv`), plus `winner_final`, `team1_won`, `is_tie` and `outcome_type`. They are only known after the match.
- **Split by time, never at random.** Train on earlier seasons and test on later ones. Random splitting lets the model see the future.
- **Build "form" features in order.** Sort by `match_idx`, and make each match's features from earlier matches only.
- **Do not auto-merge player names.** See `player_name_review.csv`; for example `R Bishnoi` (2009) and `Ravi Bishnoi` (2020+) are different people.
- **Treat 2025–26 carefully.** They have lineups but no ball-by-ball data, and 75 of the 261 players in those lineups have no earlier history. They need average priors in feature engineering.

Loading example:

```python
import pandas as pd

m = pd.read_csv("data/processed/matches_model.csv", parse_dates=["date"])
m["team1_xi"] = m["team1_players"].str.split("|")   # list of player names
train = m[m["season"] <= 2022]                      # time-based split
test = m[m["season"] >= 2023]
```

## Roadmap

| Stage | Status |
|---|---|
| 1. Problem framing, metrics and split rule | Planned |
| 2. **Data cleaning and validation** | **Done** (`clean_data.py`) |
| 3. Feature engineering: Elo rating, rolling form, head-to-head, venue and toss statistics, player ratings aggregated over the playing XI | Planned |
| 4. Modelling: baselines, logistic regression, random forest, gradient boosting, probability calibration | Planned |
| 5. Evaluation on a 2025–26 hold-out, plus SHAP explanations and error analysis | Planned |
| 6. Season simulator: 10,000 simulations, giving champion and top-4 probabilities | Planned |
| 7. Streamlit or Gradio app, report and demo | Planned |
| 8. Optional: live in-match win-probability model | Planned |

**Evaluation plan:** walk-forward validation by season, reporting log loss, Brier score, accuracy and AUC against simple baselines (toss winner, higher Elo rating). Pre-match cricket models usually land in the high 50s to mid 60s in accuracy. If a model scores far above that, check for leakage first.

## Project structure

```
ipl-winner-prediction/
├── README.md
├── clean_data.py                  # the cleaning pipeline
├── data_cleaning_explained.md     # problems found, decisions made, alternatives rejected
└── data/
    ├── raw/                       # put the three original CSVs here (not generated)
    └── processed/                 # created by clean_data.py
```

New code for later stages (features, models, simulator, app) should live alongside these.

## Known limitations

- **Judgement calls from domain knowledge.** The team and venue mappings (for example, treating Mullanpur and New Chandigarh as one ground, or Subrata Roy Sahara Stadium as the Pune MCA ground) are mine, not derivable from the data. They are easy to review in the `VENUES` table in `clean_data.py`.
- **2025–26 results were used as given.** They could not be checked against an outside source.
- **One source-data error is flagged, not fixed.** 28 overs in 27 matches contain 7 legal deliveries (0.07% of overs). They are marked `over_has_extra_legal_ball`.
- **The playoff rule for 2025–26 is validated only on 2019–2024.** The script refuses to apply it if that validation ever fails.
- **No model results exist yet.**

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| `FileNotFoundError` | A raw file is missing or misnamed. File names are case-sensitive: `matches.csv`, `Match_dataset.csv`, `deliveries_ball_by_ball.csv`. |
| `ValueError: ... venue name(s) not in VENUES table` | New data has a ground the script has not seen. Add it to `VENUES` in `clean_data.py`, or run with `--no-strict` to keep the raw name and only log a warning. |
| `AssertionError: ... disagrees ...` | The files no longer agree with each other. This is intentional: check the raw data rather than bypassing the check. |
| Different numbers than the table in [Quick start](#quick-start) | Your raw files differ from the ones this project was built on. Compare against `cleaning_report.json`. |

## Data source and license

The origin and license of the raw CSV files are not recorded in this project. **Add the source (and its license terms) here before sharing or publishing the repository.**

No license has been chosen for the code yet. Add a `LICENSE` file when you decide how others may use it.
