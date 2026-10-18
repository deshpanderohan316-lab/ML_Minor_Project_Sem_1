# IPL dataset cleaning: problems, decisions and alternatives

This document explains what was wrong with the three raw files, what `clean_data.py` does about each problem, **why that method was chosen**, and **which other methods were considered and rejected**.

```bash
python clean_data.py --input-dir /path/to/raw --output-dir data/processed
```

## 0. Design philosophy (applies to every step)

| Principle | What it means here |
|---|---|
| **Explicit over clever** | Name fixes live in small, readable lookup tables, not in fuzzy-matching code. You can read and audit every decision. |
| **Fail loudly** | Every assumption is an `assert`. If the data does not behave as expected, the script stops with a message. |
| **Flag, don't delete** | Ambiguous rows (ties, no-results, super overs, odd overs) get a flag or their own file. Nothing is silently thrown away. |
| **Leakage-proof by construction** | Anything only known *after* a match is prefixed `post_` and excluded from the model file. |
| **Reproducible** | One script, same output every run, plus a `cleaning_report.json` with counts of everything changed. |

### Output files

| File | Rows | Purpose |
|---|---|---|
| `matches_clean.csv` | 1,243 | All matches, all flags, `post_` columns included (for EDA). |
| `matches_model.csv` | 1,234 | Usable matches only, **no** `post_` columns. Label is `team1_won`. |
| `deliveries_clean.csv` | 260,759 | Innings 1–2 only, with helper columns. |
| `deliveries_super_over.csv` | 161 | Super-over balls (innings 3+), kept separate. |
| `player_name_review.csv` | | Possible duplicate player names for **manual** review. |
| `cleaning_report.json` | | Counts of every fix and check. |

---

## 1. Three files that overlap but are not identical

**Problem.** `matches.csv` (1,095 matches, 2008–2024) and `Match_dataset.csv` (1,243 matches, 2008–2026) describe the same matches, but each has columns the other lacks. `Match_dataset` has playing XIs and the 2025–26 seasons. `matches.csv` has `match_type`, margins and `target_runs`.

**Method chosen.** Use `Match_dataset` as the spine, left-join the extra `matches.csv` columns on `match_id`, and **assert that the two files agree** on teams, toss, date, venue and city for all 1,095 shared matches (after cleaning names).

**Why.** The spine has every match. The join adds only what is missing. The assertion turns "I think these are the same matches" into a proven fact (it passed: 1,095 of 1,095).

**Alternatives considered.**
- *Use only `matches.csv`*: loses 2025–26 and all lineups.
- *Use only `Match_dataset`*: loses `match_type` and result margins.
- *Stack the files (`concat`)*: duplicates 1,095 matches and would double-count them in every rolling statistic.
- *Merge on (date, team1, team2)*: fragile, because team and venue names differ between files. The match id is exact.

---

## 2. Team names (19 names, 15 real franchises)

**Problem.** Franchises were renamed, and one name has two spellings:

| Raw name | Standard name |
|---|---|
| Delhi Daredevils | Delhi Capitals |
| Kings XI Punjab | Punjab Kings |
| Royal Challengers Bangalore | Royal Challengers Bengaluru |
| Rising Pune Supergiants | Rising Pune Supergiant |

If left alone, one franchise's history is split in two. Elo ratings, rolling form and head-to-head records would all restart at every rename.

**Method chosen.** A 4-entry dictionary applied to every team column in all three files.

**Why.** Four entries are trivial to audit. I deliberately did **not** merge Deccan Chargers with Sunrisers Hyderabad, or Gujarat Lions with Gujarat Titans, because they are different franchises.

**Alternatives considered.**
- *Fuzzy string matching (difflib / rapidfuzz)*: fails both ways. "Delhi Daredevils" vs "Delhi Capitals" scores low and is missed, while "Gujarat Lions" vs "Gujarat Titans" scores high and would be wrongly merged.
- *Franchise ID table from an external source*: the cleanest long-term solution, but needs data you did not provide.
- *Leave as is*: breaks every team-history feature.

---

## 3. Venue names and cities

**Problem.** There are **60 raw venue names for only 36 real grounds**:
- Suffix variants: `Wankhede Stadium` vs `Wankhede Stadium, Mumbai`.
- Spelling variants: `M Chinnaswamy Stadium` vs `M.Chinnaswamy Stadium`.
- True renames: Feroz Shah Kotla became Arun Jaitley Stadium, Sardar Patel Stadium (Motera) became Narendra Modi Stadium, and Sheikh Zayed Stadium is the Zayed Cricket Stadium.
- A sponsor name: Subrata Roy Sahara Stadium is the Maharashtra Cricket Association ground in Pune.

The `city` column is also inconsistent. It has Bangalore and Bengaluru, Mumbai and Navi Mumbai for the same stadium, and Mohali, Chandigarh and New Chandigarh for the Punjab grounds. 51 cities are missing (all Dubai and Sharjah).

**Method chosen.** One table, `VENUES`: canonical name, canonical city, and every raw spelling. The `city` column is then **derived from the venue**, so there is a single source of truth. In strict mode (the default) an unknown venue stops the script with a message telling you to add it.

**Why.** Venue statistics (average first-innings score, chase win %) are core features. If one ground is split across three names, each name gets a third of the data and the statistics become noisy. Deriving city from venue fixes the inconsistent and missing cities in one step.

**Alternatives considered.**
- *Regex that strips the `, city` suffix*: gets 60 down to about 42 only. It cannot know that Feroz Shah Kotla is Arun Jaitley Stadium.
- *Fuzzy matching*: the same false-positive and false-negative problem as team names.
- *Geocoding / Places API*: needs network access and keys, is overkill for 36 grounds, and resolves renames poorly.
- *Fill missing cities with the most common value*: invents data. Deriving from the venue is exact.
- *Do nothing and one-hot the raw names*: splits each ground's history, as described above.

> **Judgement calls to double-check (domain knowledge, not derivable from the data):** Dr DY Patil is filed under *Navi Mumbai*; the Mohali ground is filed under *Mohali* (the raw data says Chandigarh); Mullanpur and New Chandigarh are treated as one ground; Subrata Roy Sahara Stadium is merged with the MCA Pune ground. They are all one-line edits in `VENUES`.

---

## 4. Season labels and date format

**Problem.** `season` mixes formats (`2007/08`, `2009/10`, `2020/21` next to plain years). Dates are strings like `04-05-2023`.

**Method chosen.** Derive `season` from the parsed **calendar year**, and keep the raw label as `season_label_raw`. Dates are parsed with an explicit `format="%d-%m-%Y"`.

**Why.** One consistent integer is easy to group and split on. An explicit format matters because `04-05-2023` is ambiguous: a guessing parser can read it as April 5th, silently corrupting every date where the day is 12 or less.

**Alternatives considered.** Parsing the label text (`2007/08` to 2008) is custom logic that gives the same answer. A sequential season counter (1, 2, 3...) is less interpretable. Letting pandas infer the format risks the day/month swap above.

---

## 5. Rows are in random order

**Problem.** `Match_dataset.csv` is shuffled. Any "last 5 matches" feature computed in file order uses the future.

**Method chosen.** Sort by `(date, match_id)` and add `match_idx` (global order) and `match_no_in_season`.

**Why.** Date is the true order. `match_id` breaks ties on days with two matches. Nothing guarantees that ids are chronological, so I do not rely on them alone.

**Alternatives considered.** Sorting by id only (unproven assumption). Trusting the file order (wrong, it is shuffled).

---

## 6. `match_type` missing for 2025–26

**Problem.** `Match_dataset` has no `match_type`, so for 148 matches you cannot tell league games from playoffs.

**Method chosen.** A rule: *the last four matches of a season are Qualifier 1, Eliminator, Qualifier 2, Final.* The script first tests the rule against the **399 matches of 2019–2024 where the answer is known**. It was 100% accurate, and the script refuses to apply the rule if the accuracy drops.

**Why.** The rule is simple, testable and reproducible without outside data. Playoff vs league is a useful context feature (stakes, rest days, different team selection).

**Alternatives considered.**
- *Leave it empty*: playoff games would be treated as league games.
- *Scrape or look it up elsewhere*: not reproducible, and needs network access.
- *Infer from the points table*: complex (needs net run rate), and error-prone.
- *Label by hand*: does not scale to future seasons.
- *Apply the rule to all years*: wrong. Before 2019 there were semi-finals and a 3rd-place play-off, so the rule was only validated for the 4-match format.

---

## 7. Missing winners (ties and no-results)

**Problem.** `winner` is empty for 25 matches: 16 ties and 9 no-results. For ties, the actual winner (decided by a super over) is hidden in a column misleadingly named `eliminator`.

**Method chosen.**
- **Ties:** `winner_final` = the super-over winner (`is_tie = True` is kept so you can drop ties later). It matches `matches.csv` for every overlapping tie.
- **No-results:** `winner_final` stays empty and `is_usable = False`. They stay in `matches_clean.csv` but are removed from `matches_model.csv`.
- The label `team1_won` uses a nullable integer type, so "no winner" stays *missing* instead of turning into 0.

**Why.** A tied match's super-over winner gets the two league points, so it is a legitimate label. A no-result has no winner, so it cannot teach a win-prediction model anything. Pandas will happily turn `NaN == team1` into `False`, which would quietly label 9 matches as "team1 lost". The nullable type prevents that bug.

**Alternatives considered.**
- *Drop ties*: loses 16 valid labelled matches. The flag lets you do it later if you want.
- *Tie as a third class*: only 16 examples (1.3%), not learnable.
- *Fill missing winners with team1 or at random*: fabricates labels.
- *Keep no-results as 0.5 soft labels*: needs a different loss function, for just 9 matches.

---

## 8. Columns that leak the future

**Problem.** `player_of_match`, `result_margin`, `target_runs`, `target_overs`, the result detail (runs or wickets), the D/L flag and the super-over winner only exist **after** the match. Feeding any of them to a pre-match model produces fake, impressive accuracy.

**Method chosen.** Rename all of them with a **`post_` prefix**. `matches_model.csv` contains none of them. `winner_final`, `team1_won`, `is_tie` and `outcome_type` are outcome columns (labels and filters), never features, and the script docstring says so.

**Why.** A naming convention makes the mistake hard to commit by accident. You still keep the columns for EDA and for the cross-checks in this script.

**Alternatives considered.** Deleting them (loses useful analysis data). Keeping them unmarked and "remembering" to drop them (this is how leakage usually happens). Umpire columns were not carried over, as they add nothing for this project.

---

## 9. Playing XI columns

**Problem.** Each lineup is one comma-separated string. Sizes are 11 until 2022 and 12 from 2023 onward (the Impact Player rule), with 6 lineups of 13.

**Method chosen.** Split, strip whitespace, assert there are no duplicates and that sizes are 11–13, then store as a `|`-joined string and add `team1_lineup_size` / `team2_lineup_size`.

**Why.** No player name contains `|`, so the format round-trips safely through CSV. The 12th player is real information (the impact substitute), so I flag it rather than truncate it.

**Alternatives considered.**
- *Python lists*: CSV cannot store them.
- *One-hot columns per player*: 700+ mostly-empty columns. That belongs in feature engineering, not cleaning.
- *Exploded one-row-per-player table*: very useful later for joins, and cheap to build from this format.

---

## 10. Player names (checked, deliberately not merged)

**Problem.** Names use initials (`RG Sharma`) in some places and full first names (`Ravi Bishnoi`) in others, so the same person may appear under two names.

**What I found.** 34 groups of similar names (same surname and first initial). In **11 of them, two names appear in the same match's lineup**. That proves they are different people. `R Bishnoi` (played in 2009) and `Ravi Bishnoi` (2020 onward) look like one player but are clearly two.

**Method chosen.** Write these groups to `player_name_review.csv` for manual review. **Do not auto-merge.**

**Why.** A wrong merge is worse than a missing merge. It would hand a 2009 player's career to a 2020 debutant and corrupt the player ratings.

**Alternatives considered.** Fuzzy or initial-based auto-merge (rejected for the reason above). A player-ID registry such as the one published with Cricsheet data (the best long-term fix, but not in your files).

**Related facts reported, not "fixed".** 4 players in 2008–24 lineups have no balls recorded (benched, or never batted or bowled). 75 of the 261 players in 2025–26 lineups have **no ball-by-ball history at all**. That is a cold-start problem for feature engineering, where those players should get league-average priors.

---

## 11. Ball-by-ball data

The deliveries file was mostly consistent, so most of the work here is **verification**. The script asserts:
- No duplicate balls, and `total_runs = batsman_runs + extra_runs` on every row.
- `is_wicket` agrees exactly with `dismissal_kind` and `player_dismissed`.
- Every ball's batting and bowling team is one of the match's two teams.
- Innings-1 total + 1 equals the stated target in every match **except the 21 rain-affected (D/L) matches**.
- The batting-first team derived from the toss equals the innings-1 batting team in all matches.

Decisions made:

| Issue | Method chosen | Why / alternatives |
|---|---|---|
| `extras_type` is empty on normal balls | Fill with `"none"` | Empty means "no extra", not "missing". Pandas `groupby` silently **drops** empty keys, so leaving them would remove most balls from any grouping. |
| `dismissal_kind`, `player_dismissed`, `fielder` mostly empty | Leave as empty | They are genuinely not applicable on non-wicket balls. Filling them with text would blur "no wicket". |
| Super overs: 161 balls, 14 matches (innings 3–6) | Separate file plus `is_super_over` flag | Super-over balls have very high run rates and would contaminate batting and bowling stats. Dropping them loses information. A flag alone is easy to forget to filter. |
| Wides and no-balls are not legal deliveries | `is_legal_ball` (also excludes `penalty`, which are awarded runs, not deliveries) | Strike rate and overs bowled need legal balls. Using all rows overstates balls faced. |
| Byes and leg-byes are not the bowler's fault | `bowler_runs` | Using `total_runs` would overcharge bowlers by **6,513 runs** (about 1.9%) in economy rates. |
| Retired hurt is not a wicket for the team | `team_wicket` excludes it; `bowler_wicket` counts only the six bowler-credited dismissal types | Run outs are not bowler wickets. Counting them inflates bowler ratings. |
| Convenience state columns | `legal_balls_cum`, `runs_cum`, `wickets_cum` | Needed for the optional live win-probability model, and cheap to add. |

### A source-data error I found and did not "fix"

My validation showed **28 overs in 27 matches contain 7 legal deliveries**, which is impossible in cricket. It is a scoring error in the source. I cannot tell which row is wrong, and guessing would invent data. So the script flags those balls with `over_has_extra_legal_ball` (0.07% of overs) so you can exclude them or inspect them. This also explains why a few innings show 121 legal balls.

---

## 12. Output format

I chose **CSV** because it opens everywhere and needs no extra library. Parquet would be smaller and faster and would keep column types (switching is a one-line change), but it needs `pyarrow`. Date and nullable columns are re-read correctly by pandas.

---

## 13. What was intentionally *not* done

- **No outlier removal.** Very short innings (as low as 7 legal balls) come from rain-shortened or abandoned matches, not from data errors. Removing them would delete real outcomes. The no-result matches are already handled in section 7.
- **No class balancing.** The labels are already balanced (617 vs 617 after removing no-results).
- **No feature engineering.** Elo, form, venue averages, impact-player flags and player ratings come next, as a separate step.
- **No invented 2025–26 ball-by-ball data.** The deliveries stop at 2024. Add Cricsheet data if you want player stats for 2025–26.

## 14. Limits of this cleaning

- The venue and team mappings use my domain knowledge. They are easy to review, but please check the judgement calls in section 3.
- I could not verify the 2025–26 results against an outside source, so those rows are used as given.
- The playoff rule is validated only on 2019–2024. If the IPL changes its playoff format, the script's assertion will stop it rather than mislabel matches.
