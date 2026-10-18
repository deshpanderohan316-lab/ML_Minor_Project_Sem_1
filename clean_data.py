#!/usr/bin/env python3
"""
IPL data cleaning pipeline
==========================

Reads the three raw files

    matches.csv                   (1,095 matches, 2008-2024, match summary)
    Match_dataset.csv             (1,243 matches, 2008-2026, adds playing XIs)
    deliveries_ball_by_ball.csv   (260,920 balls, same 1,095 matches as matches.csv)

and writes analysis-ready files to the output directory:

    matches_clean.csv         every match, with flags, post-match columns prefixed `post_`
    matches_model.csv         usable matches only (no-results removed), no `post_` columns.
                              Label = `team1_won`. `winner_final`, `is_tie`, `outcome_type`
                              are outcome columns (for filtering/labels), NEVER features.
    deliveries_clean.csv      innings 1-2 only, with helper columns for batting/bowling stats
    deliveries_super_over.csv super-over balls (innings 3+), kept separate
    player_name_review.csv    possible duplicate player names for MANUAL review
    cleaning_report.json      counts of everything that was changed or flagged

Usage
-----
    python clean_data.py --input-dir /path/to/raw --output-dir data/processed

Every important assumption is enforced with an assertion, so the script fails
loudly instead of silently producing wrong data. See the accompanying markdown
(data_cleaning_explained.md) for the reasoning behind each step.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("ipl_clean")

# --------------------------------------------------------------------------- #
# 1. Lookup tables (explicit, reviewable, and version-controllable)
# --------------------------------------------------------------------------- #

# Same franchise under different names. Deccan Chargers and Sunrisers Hyderabad,
# and Gujarat Lions and Gujarat Titans, are DIFFERENT franchises: not merged.
TEAM_ALIASES = {
    "Delhi Daredevils": "Delhi Capitals",
    "Kings XI Punjab": "Punjab Kings",
    "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
    "Rising Pune Supergiants": "Rising Pune Supergiant",
}

# canonical ground name -> (city, every raw spelling found in the files)
VENUES: dict[str, tuple[str, list[str]]] = {
    "Arun Jaitley Stadium": ("Delhi", ["Feroz Shah Kotla", "Arun Jaitley Stadium", "Arun Jaitley Stadium, Delhi"]),
    "Barabati Stadium": ("Cuttack", ["Barabati Stadium"]),
    "Barsapara Cricket Stadium": ("Guwahati", ["Barsapara Cricket Stadium, Guwahati"]),
    "Brabourne Stadium": ("Mumbai", ["Brabourne Stadium", "Brabourne Stadium, Mumbai"]),
    "Buffalo Park": ("East London", ["Buffalo Park"]),
    "De Beers Diamond Oval": ("Kimberley", ["De Beers Diamond Oval"]),
    "Dr DY Patil Sports Academy": ("Navi Mumbai", ["Dr DY Patil Sports Academy", "Dr DY Patil Sports Academy, Mumbai"]),
    "Dr. Y.S. Rajasekhara Reddy ACA-VDCA Cricket Stadium": (
        "Visakhapatnam",
        ["Dr. Y.S. Rajasekhara Reddy ACA-VDCA Cricket Stadium",
         "Dr. Y.S. Rajasekhara Reddy ACA-VDCA Cricket Stadium, Visakhapatnam"]),
    "Dubai International Cricket Stadium": ("Dubai", ["Dubai International Cricket Stadium"]),
    "Eden Gardens": ("Kolkata", ["Eden Gardens", "Eden Gardens, Kolkata"]),
    "Ekana Cricket Stadium": (
        "Lucknow", ["Bharat Ratna Shri Atal Bihari Vajpayee Ekana Cricket Stadium, Lucknow"]),
    "Green Park": ("Kanpur", ["Green Park"]),
    "Himachal Pradesh Cricket Association Stadium": (
        "Dharamsala",
        ["Himachal Pradesh Cricket Association Stadium",
         "Himachal Pradesh Cricket Association Stadium, Dharamsala"]),
    "Holkar Cricket Stadium": ("Indore", ["Holkar Cricket Stadium"]),
    "JSCA International Stadium Complex": ("Ranchi", ["JSCA International Stadium Complex"]),
    "Kingsmead": ("Durban", ["Kingsmead"]),
    "M Chinnaswamy Stadium": (
        "Bengaluru",
        ["M Chinnaswamy Stadium", "M.Chinnaswamy Stadium", "M Chinnaswamy Stadium, Bengaluru"]),
    "MA Chidambaram Stadium": (
        "Chennai",
        ["MA Chidambaram Stadium", "MA Chidambaram Stadium, Chepauk",
         "MA Chidambaram Stadium, Chepauk, Chennai"]),
    "Maharaja Yadavindra Singh International Cricket Stadium": (
        "New Chandigarh",
        ["Maharaja Yadavindra Singh International Cricket Stadium, Mullanpur",
         "Maharaja Yadavindra Singh International Cricket Stadium, New Chandigarh"]),
    "Maharashtra Cricket Association Stadium": (
        "Pune",
        ["Maharashtra Cricket Association Stadium", "Maharashtra Cricket Association Stadium, Pune",
         "Subrata Roy Sahara Stadium"]),  # same Gahunje ground under a sponsor name
    "Narendra Modi Stadium": (
        "Ahmedabad", ["Narendra Modi Stadium, Ahmedabad", "Sardar Patel Stadium, Motera"]),  # renamed 2021
    "Nehru Stadium": ("Kochi", ["Nehru Stadium"]),
    "New Wanderers Stadium": ("Johannesburg", ["New Wanderers Stadium"]),
    "Newlands": ("Cape Town", ["Newlands"]),
    "OUTsurance Oval": ("Bloemfontein", ["OUTsurance Oval"]),
    "Punjab Cricket Association IS Bindra Stadium": (
        "Mohali",
        ["Punjab Cricket Association Stadium, Mohali",
         "Punjab Cricket Association IS Bindra Stadium",
         "Punjab Cricket Association IS Bindra Stadium, Mohali",
         "Punjab Cricket Association IS Bindra Stadium, Mohali, Chandigarh"]),
    "Rajiv Gandhi International Stadium": (
        "Hyderabad",
        ["Rajiv Gandhi International Stadium", "Rajiv Gandhi International Stadium, Uppal",
         "Rajiv Gandhi International Stadium, Uppal, Hyderabad"]),
    "Saurashtra Cricket Association Stadium": ("Rajkot", ["Saurashtra Cricket Association Stadium"]),
    "Sawai Mansingh Stadium": ("Jaipur", ["Sawai Mansingh Stadium", "Sawai Mansingh Stadium, Jaipur"]),
    "Shaheed Veer Narayan Singh International Stadium": (
        "Raipur",
        ["Shaheed Veer Narayan Singh International Stadium",
         "Shaheed Veer Narayan Singh International Stadium, Raipur"]),
    "Sharjah Cricket Stadium": ("Sharjah", ["Sharjah Cricket Stadium"]),
    "St George's Park": ("Port Elizabeth", ["St George's Park"]),
    "SuperSport Park": ("Centurion", ["SuperSport Park"]),
    "Vidarbha Cricket Association Stadium": ("Nagpur", ["Vidarbha Cricket Association Stadium, Jamtha"]),
    "Wankhede Stadium": ("Mumbai", ["Wankhede Stadium", "Wankhede Stadium, Mumbai"]),
    "Zayed Cricket Stadium": ("Abu Dhabi", ["Sheikh Zayed Stadium", "Zayed Cricket Stadium, Abu Dhabi"]),
}


def _build_venue_lookup() -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for canonical, (city, aliases) in VENUES.items():
        for alias in aliases:
            if alias in lookup:
                raise ValueError(f"Venue alias listed twice: {alias!r}")
            lookup[alias] = (canonical, city)
    return lookup


VENUE_LOOKUP = _build_venue_lookup()

# Playoff structure of the 4-match format (used from 2019 onward)
PLAYOFF_ORDER = ["Qualifier 1", "Eliminator", "Qualifier 2", "Final"]
RULE_VALIDATION_YEARS = range(2019, 2025)   # years where match_type is known

# Dismissals credited to the bowler (run out, retired etc. are not)
BOWLER_WICKETS = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}


# --------------------------------------------------------------------------- #
# 2. Small helpers
# --------------------------------------------------------------------------- #

def standardize_teams(df: pd.DataFrame, cols: list[str], report: dict, key: str) -> pd.DataFrame:
    changed = 0
    for c in cols:
        before = df[c]
        df[c] = before.replace(TEAM_ALIASES)
        changed += int((before != df[c]).sum() - (before.isna() & df[c].isna()).sum())
    report[key] = changed
    return df


def standardize_venues(df: pd.DataFrame, strict: bool, report: dict, key: str) -> pd.DataFrame:
    raw = df["venue"].str.strip()
    unknown = sorted(set(raw) - set(VENUE_LOOKUP))
    if unknown:
        msg = f"{len(unknown)} venue name(s) not in VENUES table: {unknown}"
        if strict:
            raise ValueError(msg + "  -> add them to VENUES (or run with --no-strict).")
        log.warning(msg)
    canon = raw.map(lambda v: VENUE_LOOKUP.get(v, (v, None))[0])
    city = raw.map(lambda v: VENUE_LOOKUP.get(v, (None, None))[1])
    old_city = df["city"].copy()
    df["venue"] = canon
    df["city"] = city.fillna(old_city)
    report[key] = {
        "raw_venue_names": int(raw.nunique()),
        "canonical_venues": int(canon.nunique()),
        "city_values_changed_or_filled": int((old_city.fillna("<NA>") != df["city"]).sum()),
    }
    return df


def split_lineup(s: str) -> list[str]:
    return [p.strip() for p in str(s).split(",") if p.strip()]


# --------------------------------------------------------------------------- #
# 3. Match-level cleaning
# --------------------------------------------------------------------------- #

def build_matches(m: pd.DataFrame, md: pd.DataFrame, strict: bool, report: dict) -> pd.DataFrame:
    m, md = m.copy(), md.copy()
    md = md.rename(columns={"match_number": "match_id", "match_date": "date",
                            "eliminator": "super_over_winner"})
    m = m.rename(columns={"id": "match_id"})
    for df in (m, md):
        df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="raise")

    # --- standardize names so both files can be compared / merged ----------
    team_cols_md = ["team1", "team2", "toss_winner", "winner", "super_over_winner"]
    md = standardize_teams(md, team_cols_md, report, "team_name_cells_changed_match_dataset")
    m = standardize_teams(m, ["team1", "team2", "toss_winner", "winner"], report,
                          "team_name_cells_changed_matches_csv")
    md = standardize_venues(md, strict, report, "venues_match_dataset")
    m = standardize_venues(m, strict, report, "venues_matches_csv")

    # --- the two files must agree on every shared fact ---------------------
    chk = m.merge(md, on="match_id", suffixes=("_m", "_md"), validate="one_to_one")
    assert len(chk) == len(m), "matches.csv contains ids missing from Match_dataset.csv"
    for col in ["team1", "team2", "toss_winner", "toss_decision", "date", "venue", "city"]:
        bad = (chk[f"{col}_m"] != chk[f"{col}_md"]).sum()
        assert bad == 0, f"'{col}' disagrees between files on {bad} matches"
    report["shared_matches_cross_checked"] = int(len(chk))

    # --- bring the extra columns from matches.csv onto the spine ------------
    extra = m[["match_id", "season", "match_type", "result", "result_margin",
               "target_runs", "target_overs", "super_over", "method"]].rename(columns={
        "season": "season_label_raw", "result": "post_result_detail",
        "result_margin": "post_result_margin", "target_runs": "post_target_runs",
        "target_overs": "post_target_overs"})
    extra["post_dl_applied"] = extra.pop("method").eq("D/L")
    extra = extra.drop(columns="super_over")        # redundant with is_tie, see report
    df = md.merge(extra, on="match_id", how="left", validate="one_to_one")
    df["has_ball_by_ball"] = df["match_id"].isin(m["match_id"])
    df["post_dl_applied"] = df["post_dl_applied"].astype("boolean")
    df.loc[~df["has_ball_by_ball"], "post_dl_applied"] = pd.NA

    # --- chronological order + calendar season ------------------------------
    df = df.sort_values(["date", "match_id"]).reset_index(drop=True)
    df["season"] = df["date"].dt.year
    df["match_idx"] = np.arange(len(df))
    df["match_no_in_season"] = df.groupby("season").cumcount() + 1

    df = infer_match_type(df, report)
    df = resolve_outcomes(df, m, report)
    df = clean_lineups(df, report)

    df["post_player_of_match"] = df.pop("player_of_match")
    return df


def infer_match_type(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Match_dataset has no match_type. Rule: last 4 matches of a season =
    Qualifier 1, Eliminator, Qualifier 2, Final. Validated on known years first."""
    pos_from_end = df.groupby("season").cumcount(ascending=False)   # 0 = last match of the season
    rule = pos_from_end.map(lambda p: PLAYOFF_ORDER[3 - p] if p < 4 else "League")
    known = df["match_type"].notna() & df["season"].isin(RULE_VALIDATION_YEARS)
    acc = float((rule[known] == df.loc[known, "match_type"]).mean())
    assert acc == 1.0, f"Playoff rule only {acc:.1%} accurate on known seasons; refusing to apply it"
    df["match_type_source"] = np.where(df["match_type"].notna(), "matches.csv", "inferred_by_rule")
    df["match_type"] = df["match_type"].fillna(rule)
    df["is_playoff"] = df["match_type"].ne("League")
    report["match_type_rule_validation"] = {"years": [min(RULE_VALIDATION_YEARS), max(RULE_VALIDATION_YEARS)],
                                            "accuracy": acc, "matches_checked": int(known.sum())}
    report["match_type_inferred_rows"] = int((df["match_type_source"] == "inferred_by_rule").sum())
    return df


def resolve_outcomes(df: pd.DataFrame, m_std: pd.DataFrame, report: dict) -> pd.DataFrame:
    df["outcome_type"] = df["result"].map({"Win": "normal", "tie": "tie", "no result": "no_result"})
    assert df["outcome_type"].notna().all(), "Unexpected value in Match_dataset 'result'"
    df["is_tie"] = df["outcome_type"].eq("tie")

    # A tie is decided by a super over; Match_dataset stores that winner in `eliminator`.
    tie_no_winner = df["is_tie"] & df["super_over_winner"].isna()
    assert not tie_no_winner.any(), f"{tie_no_winner.sum()} ties without a super-over winner"
    df["winner_final"] = df["winner"].where(df["outcome_type"].eq("normal"), df["super_over_winner"])
    df.loc[df["outcome_type"].eq("no_result"), "winner_final"] = pd.NA

    # Cross-check against matches.csv, which already stored the super-over winner in `winner`
    ref = m_std.set_index("match_id")["winner"]
    shared = df[df["has_ball_by_ball"]].set_index("match_id")["winner_final"]
    disagree = (shared.fillna("NA") != ref.reindex(shared.index).fillna("NA")).sum()
    assert disagree == 0, f"winner disagrees with matches.csv on {disagree} matches"

    decided = df["winner_final"].notna()
    ok = df.loc[decided, "winner_final"].eq(df.loc[decided, "team1"]) | \
         df.loc[decided, "winner_final"].eq(df.loc[decided, "team2"])
    assert ok.all(), "winner is neither team1 nor team2 for some match"

    df["team1_won"] = pd.array(np.where(decided, df["winner_final"].eq(df["team1"]), np.nan), dtype="Int8")
    df["is_usable"] = df["outcome_type"].ne("no_result")
    df["batting_first"] = np.where(df["toss_decision"].eq("bat"), df["toss_winner"],
                                   np.where(df["toss_winner"].eq(df["team1"]), df["team2"], df["team1"]))
    report["outcomes"] = df["outcome_type"].value_counts().to_dict()
    # The super-over winner is only known after the match -> `post_` prefix.
    return df.drop(columns=["result", "winner"]).rename(
        columns={"super_over_winner": "post_super_over_winner"})


def clean_lineups(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    sizes = {}
    for side in ("team1", "team2"):
        lists = df[f"{side}_players"].map(split_lineup)
        assert lists.map(lambda x: len(x) == len(set(x))).all(), f"duplicate player inside a {side} lineup"
        df[f"{side}_lineup_size"] = lists.map(len)
        df[f"{side}_players"] = lists.map("|".join)          # '|' never appears in a name
        sizes[side] = df[f"{side}_lineup_size"]
    allsizes = pd.concat(sizes.values())
    assert allsizes.between(11, 13).all(), "Lineup size outside 11-13"
    report["lineup_size_counts"] = {int(k): int(v) for k, v in allsizes.value_counts().sort_index().items()}
    return df


# --------------------------------------------------------------------------- #
# 4. Ball-by-ball cleaning
# --------------------------------------------------------------------------- #

def clean_deliveries(d: pd.DataFrame, matches: pd.DataFrame, report: dict):
    d = d.copy()
    d = standardize_teams(d, ["batting_team", "bowling_team"], report, "team_name_cells_changed_deliveries")

    # --- referential integrity ---------------------------------------------
    assert d["match_id"].isin(matches["match_id"]).all(), "deliveries has match_ids not in matches"
    with_bbb = matches.loc[matches["has_ball_by_ball"], "match_id"]
    assert with_bbb.isin(d["match_id"]).all(), "a match flagged has_ball_by_ball has no deliveries"
    key = ["match_id", "inning", "over", "ball"]
    assert not d.duplicated(key).any(), "duplicate ball records"

    # --- the two teams on every ball must be the two teams of the match -----
    mt = matches.set_index("match_id")[["team1", "team2"]]
    j = d.join(mt, on="match_id")
    in_match = (j["batting_team"].eq(j["team1"]) | j["batting_team"].eq(j["team2"])) & \
               (j["bowling_team"].eq(j["team1"]) | j["bowling_team"].eq(j["team2"])) & \
               j["batting_team"].ne(j["bowling_team"])
    assert in_match.all(), f"{(~in_match).sum()} balls whose teams don't match the match record"

    # --- internal arithmetic / flag consistency ------------------------------
    assert (d["total_runs"] == d["batsman_runs"] + d["extra_runs"]).all(), "total_runs != bat + extras"
    assert ((d["is_wicket"] == 1) == d["dismissal_kind"].notna()).all(), "is_wicket vs dismissal_kind"
    assert ((d["is_wicket"] == 1) == d["player_dismissed"].notna()).all(), "is_wicket vs player_dismissed"

    # --- derived helper columns ---------------------------------------------
    d["extras_type"] = d["extras_type"].fillna("none")        # NaN meant "no extra", not "missing"
    d["is_super_over"] = d["inning"] > 2
    # Wides and no-balls are re-bowled; 'penalty' rows are awarded runs, not deliveries.
    d["is_legal_ball"] = ~d["extras_type"].isin(["wides", "noballs", "penalty"])
    # Byes/leg-byes/penalty runs are not charged to the bowler; wides and no-balls are.
    d["bowler_runs"] = np.where(d["extras_type"].isin(["byes", "legbyes", "penalty"]),
                                d["batsman_runs"], d["total_runs"])
    d["team_wicket"] = (d["is_wicket"] == 1) & (d["dismissal_kind"] != "retired hurt")
    d["bowler_wicket"] = d["dismissal_kind"].isin(BOWLER_WICKETS)
    # Source anomaly: a few overs contain 7 legal deliveries, which is impossible in cricket.
    # We cannot tell which row is wrong, so we FLAG (not "fix") them.
    d["over_has_extra_legal_ball"] = d.groupby(["match_id", "inning", "over"])["is_legal_ball"].transform("sum") > 6
    bad_overs = d[d["over_has_extra_legal_ball"]]
    report["overs_with_more_than_6_legal_balls"] = {
        "overs": int(bad_overs.groupby(["match_id", "inning", "over"]).ngroups),
        "matches": int(bad_overs["match_id"].nunique())}
    d = d.join(matches.set_index("match_id")[["date", "season"]], on="match_id")
    d = d.sort_values(["date", "match_id", "inning", "over", "ball"]).reset_index(drop=True)

    grp = d.groupby(["match_id", "inning"])
    d["legal_balls_cum"] = grp["is_legal_ball"].cumsum()
    d["runs_cum"] = grp["total_runs"].cumsum()
    d["wickets_cum"] = grp["team_wicket"].cumsum()

    # --- innings-1 total must explain the chase target (except D/L games) ---
    inn1 = d[d["inning"] == 1].groupby("match_id")["total_runs"].sum().rename("inn1_runs")
    chk = matches.set_index("match_id").join(inn1, how="inner")
    chk = chk[chk["post_target_runs"].notna()]
    mismatch = chk[chk["post_target_runs"] != chk["inn1_runs"] + 1]
    unexplained = mismatch[~mismatch["post_dl_applied"].fillna(False).astype(bool)]
    assert unexplained.empty, f"target_runs mismatch not explained by D/L: {unexplained.index.tolist()}"
    report["target_runs_mismatches_explained_by_DL"] = int(len(mismatch))

    # --- batting-first team from the toss must equal innings-1 batting team --
    first = d[d["inning"] == 1].groupby("match_id")["batting_team"].first()
    bf = matches.set_index("match_id")["batting_first"].reindex(first.index)
    assert (first == bf).all(), "toss-derived batting-first team disagrees with deliveries"

    so = d[d["is_super_over"]].copy()
    regular = d[~d["is_super_over"]].copy()
    report["deliveries"] = {"raw_rows": int(len(d)), "regular_rows": int(len(regular)),
                            "super_over_rows": int(len(so)),
                            "super_over_matches": int(so["match_id"].nunique())}
    return regular, so


# --------------------------------------------------------------------------- #
# 5. Player-name review (report only: never auto-merged)
# --------------------------------------------------------------------------- #

def player_name_review(matches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for side in ("team1", "team2"):
        part = matches[["match_id", "season", f"{side}_players"]].rename(columns={f"{side}_players": "p"})
        part["p"] = part["p"].str.split("|")
        rows.append(part.explode("p"))
    long = pd.concat(rows).rename(columns={"p": "player"})

    def key(name: str) -> str:
        toks = name.split()
        return f"{toks[-1].lower()}|{toks[0][0].lower()}"

    long["group_key"] = long["player"].map(key)
    stats = long.groupby(["group_key", "player"]).agg(
        n_matches=("match_id", "nunique"), first_season=("season", "min"),
        last_season=("season", "max")).reset_index()
    multi = stats.groupby("group_key")["player"].transform("nunique") > 1
    stats = stats[multi]
    clash = (long[long["group_key"].isin(stats["group_key"])]
             .groupby(["group_key", "match_id"])["player"].nunique().gt(1)
             .groupby("group_key").any().rename("two_names_in_same_match"))
    return stats.join(clash, on="group_key").sort_values(["group_key", "first_season"])


# --------------------------------------------------------------------------- #
# 6. Orchestration
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input-dir", type=Path, default=Path("."))
    ap.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    ap.add_argument("--no-strict", action="store_true",
                    help="warn (instead of fail) on venue names missing from the VENUES table")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    m = pd.read_csv(args.input_dir / "matches.csv")
    md = pd.read_csv(args.input_dir / "Match_dataset.csv")
    d = pd.read_csv(args.input_dir / "deliveries_ball_by_ball.csv", low_memory=False)
    report["raw_shapes"] = {"matches": list(m.shape), "Match_dataset": list(md.shape),
                            "deliveries": list(d.shape)}
    log.info("Loaded %s matches, %s Match_dataset rows, %s deliveries", len(m), len(md), len(d))

    matches = build_matches(m, md, strict=not args.no_strict, report=report)
    regular, super_over = clean_deliveries(d, matches, report)

    # players in recent lineups with no ball-by-ball history (cold-start problem)
    seen = set(d["batter"]) | set(d["bowler"]) | set(d["non_striker"])
    recent = matches.loc[~matches["has_ball_by_ball"]]
    recent_players = {p for col in ("team1_players", "team2_players") for s in recent[col] for p in s.split("|")}
    old_players = {p for col in ("team1_players", "team2_players")
                   for s in matches.loc[matches["has_ball_by_ball"], col] for p in s.split("|")}
    report["players"] = {"in_2008_24_lineups_not_in_deliveries": len(old_players - seen),
                         "in_2025_26_lineups": len(recent_players),
                         "in_2025_26_lineups_without_history": len(recent_players - seen)}

    review = player_name_review(matches)
    report["player_name_review_groups"] = int(review["group_key"].nunique())

    model_cols = [c for c in matches.columns if not c.startswith("post_")]
    matches.to_csv(args.output_dir / "matches_clean.csv", index=False)
    matches.loc[matches["is_usable"], model_cols].to_csv(args.output_dir / "matches_model.csv", index=False)
    regular.to_csv(args.output_dir / "deliveries_clean.csv", index=False)
    super_over.to_csv(args.output_dir / "deliveries_super_over.csv", index=False)
    review.to_csv(args.output_dir / "player_name_review.csv", index=False)
    report["outputs"] = {"matches_clean": int(len(matches)),
                         "matches_model": int(matches["is_usable"].sum()),
                         "deliveries_clean": int(len(regular))}
    (args.output_dir / "cleaning_report.json").write_text(json.dumps(report, indent=2, default=str))

    log.info("Done. Files written to %s", args.output_dir.resolve())
    log.info("Report:\n%s", json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
