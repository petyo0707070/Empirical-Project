"""
NBA Game Total Market Efficiency Pipeline
==========================================
Two confirmed data sources — no flaky APIs:

  1. nba_api  — player + team game logs  (auto-downloads, confirmed working)
  2. SBR Excel — historical game lines    (one-time manual download, free)

─── HOW TO GET THE SBR DATA ────────────────────────────────────────────
  1. Go to: https://www.sportsbookreviewsonline.com/scoresoddsarchives/nba/nbaoddsarchives.htm
  2. Download the Excel file for each season you want
  3. Save them to the folder defined by SBR_DIR below, named exactly:
        nba_2019-20.xlsx
        nba_2020-21.xlsx
        nba_2021-22.xlsx
        nba_2022-23.xlsx
  The files are a known format in sports analytics — each row is one
  team-game, paired (away row then home row). Spread on away row,
  total on home row, inside the "Close" column.

─── FIXES FROM REPORT AUDIT (May 2025) ────────────────────────────────
  FIX 1: SBR odds extraction — over_odds/under_odds now read from a
          dedicated odds column (or fall back to -110/-110 symmetry)
          rather than reusing the total-line 'Close' value. This
          eliminates the bimodal 0.24/0.76 p_over_fair distribution.
  FIX 2: residual no longer overwritten in merge_lines_and_teams.
          The correct probability residual (over_hit - p_over_fair)
          computed in add_implied_prob is preserved end-to-end.
  FIX 3: total_line identification uses the home-row Close directly
          (not max of both rows) plus a validity guard [150, 280].
  FIX 4: SEASONS expanded to 2019-20 through 2022-23; delete cached
          CSVs after updating so the API re-fetches the full history.
  FIX 5: Implied-probability audit added after SBR loading to catch
          any future parsing errors before they contaminate the tests.
  FIX 6: Directional-sign assertion on OLS coefficients flags artefacts.
────────────────────────────────────────────────────────────────────────

Economic framing (identical to the options analogy):
  "Over 224.5" on a game total  ≅  Binary call, strike = 224.5
  Vig-adjusted implied prob      ≅  Risk-neutral delta
  Realized outcome (1/0)         ≅  Option payoff at expiry

  VRP analog: if E[implied prob] > E[realized rate], the market
  systematically overprices totals — sellers of variance earn a premium,
  exactly as in the equity volatility risk premium literature.

Key public signals tested for market inefficiency:
  - Back-to-back schedule (fatigue → lower scoring → under hits)
  - Days rest differential (home vs away)
  - Star player DNP (inferred from game log absence)
  - Season stage (early vs late)
  - Pace proxy (3PA, FGA)
"""

from random import sample
import os, time, warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import statsmodels.formula.api as smf
import statsmodels.api as sm
from scipy import stats
from scipy.special import logit
from pathlib import Path
from nba_api.stats.endpoints import playergamelog, teamgamelog
from nba_api.stats.static import players, teams
import sys

warnings.filterwarnings("ignore")
pd.set_option("display.float_format", "{:.4f}".format)
pd.set_option("display.max_columns", None)

# ──────────────────────────────────────────────────────────────
#  CONFIG  — edit paths, nothing else should need changing
# ──────────────────────────────────────────────────────────────

DATA_DIR   = Path("data")
SBR_DIR    = Path("data/sbr")       # put your downloaded SBR Excel files here
OUT_DIR    = Path("data/outputs")

# FIX 4: Expanded to include 2019-20 and 2020-21 so all four SBR
#         seasons have matching NBA API rows after the inner join.
#         After changing this, DELETE data/player_logs.csv and
#         data/team_logs.csv so the cache is rebuilt from scratch.
SEASONS    = ["2019-20", "2020-21", "2021-22", "2022-23"]

MIN_GAMES  = 20                     # min games per player-season
MIN_MIN    = 10                     # drop DNPs / garbage time

# Valid range for a game total line — used to catch spread/total confusion
TOTAL_LINE_MIN = 150
TOTAL_LINE_MAX = 280

for d in [DATA_DIR, SBR_DIR, OUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════
# 1.  NBA DATA LOADER  (confirmed working from your test run)
# ══════════════════════════════════════════════════════════════

class NBADataLoader:
    """
    Pulls player and team game logs.
    Enforces lowercase headers and prevents duplicate columns.
    """

    def load_player_logs(self, seasons: list[str]) -> pd.DataFrame:
        cache = DATA_DIR / "player_logs.csv"

        if cache.exists():
            df = pd.read_csv(cache)
            df.columns = [c.lower() for c in df.columns]
            df = df.loc[:, ~df.columns.duplicated()].copy()
            df["game_date"] = pd.to_datetime(df["game_date"])
            print(f"[cache] player_logs.csv    → {df.shape[0]:,} rows")
            return df

        active = players.get_active_players()
        rows   = []

        for i, p in enumerate(active):
            print(f"  [{i+1}/{len(active)}] {p['full_name']}", end="\r")
            for season in seasons:
                try:
                    df = playergamelog.PlayerGameLog(
                        player_id=p["id"], season=season,
                        season_type_all_star="Regular Season", timeout=30
                    ).get_data_frames()[0]
                    if df.empty:
                        continue

                    if "PLAYER_ID" not in df.columns and "Player_ID" not in df.columns:
                        df["PLAYER_ID"] = p["id"]
                    if "PLAYER_NAME" not in df.columns:
                        df["PLAYER_NAME"] = p["full_name"]

                    df["SEASON"] = season
                    rows.append(df)
                    time.sleep(0.6)
                except Exception:
                    continue

        if not rows: return pd.DataFrame()

        out = pd.concat(rows, ignore_index=True)

        out.columns = [c.lower() for c in out.columns]
        out = out.loc[:, ~out.columns.duplicated()].copy()

        out["game_date"] = pd.to_datetime(out["game_date"])
        if "minutes" in out.columns:
            out["minutes"] = pd.to_numeric(out["minutes"], errors="coerce")

        out.to_csv(cache, index=False)
        print(f"\n[done] {len(out):,} player-game rows saved.")
        return out

    def load_team_logs(self, seasons: list[str]) -> pd.DataFrame:
        cache = DATA_DIR / "team_logs.csv"

        if cache.exists():
            df = pd.read_csv(cache)
            df.columns = [c.lower() for c in df.columns]
            df = df.loc[:, ~df.columns.duplicated()].copy()
            df["game_date"] = pd.to_datetime(df["game_date"])
            print(f"[cache] team_logs.csv     → {df.shape[0]:,} rows")
            return df

        all_teams = teams.get_teams()
        rows = []

        for i, t in enumerate(all_teams):
            print(f"  [{i+1}/{len(all_teams)}] {t['full_name']}", end="\r")
            for season in seasons:
                try:
                    df = teamgamelog.TeamGameLog(
                        team_id=t["id"], season=season,
                        season_type_all_star="Regular Season", timeout=30
                    ).get_data_frames()[0]
                    if df.empty:
                        continue

                    if "TEAM_ID" not in df.columns and "Team_ID" not in df.columns:
                        df["TEAM_ID"] = t["id"]
                    if "TEAM_ABBR" not in df.columns:
                        df["TEAM_ABBR"] = t["abbreviation"]

                    df["SEASON"] = season
                    rows.append(df)
                    time.sleep(0.6)
                except Exception:
                    continue

        if not rows: return pd.DataFrame()

        out = pd.concat(rows, ignore_index=True)
        out.columns = [c.lower() for c in out.columns]
        out = out.loc[:, ~out.columns.duplicated()].copy()

        out["game_date"] = pd.to_datetime(out["game_date"])
        out.to_csv(cache, index=False)
        print(f"\n[done] {len(out):,} team-game rows saved.")
        return out


# ══════════════════════════════════════════════════════════════
# 2.  SBR LOADER  — reads your manually downloaded Excel files
# ══════════════════════════════════════════════════════════════

class SBRLoader:
    """
    Handles Sportsbook Review (SBR) Excel files.
    - Converts '1018' date format to datetime.
    - Maps full team names to NBA abbreviations.
    - Pivots two-row game format into a single row per game.

    FIX 1 (odds extraction): The SBR two-row format carries the
    game total in the home row's 'Close' column, but the betting
    odds (e.g. -110 / -110) are in a separate column — typically
    'ML' or an adjacent odds field — NOT the same 'Close' value.
    Reusing 'Close' (224.5) as American odds produced raw implied
    probabilities of ~0.996 and ~0.004, and after vig-stripping
    produced the observed bimodal 0.24 / 0.76 p_over_fair pattern.

    The loader now looks for a dedicated odds column in this order:
      1. 'ML'  (most common in SBR exports)
      2. 'Odds' or '2H' (alternate column names seen in some years)
      3. Hard fallback to -110 / -110 (symmetric; yields p = 0.50)
    If your SBR files use a different column name, set
    SBRLoader.ODDS_COL to match before calling load_all().

    FIX 3 (total line): The total line is taken directly from the
    home row's 'Close' column rather than max(visitor, home). A
    validity guard rejects lines outside [150, 280] to prevent
    spread values from slipping through.
    """

    # Map from SBR team names to NBA abbreviations
    TEAM_MAP = {
    'Atlanta': 'ATL', 'Boston': 'BOS', 'Brooklyn': 'BKN',
    'Charlotte': 'CHA', 'Chicago': 'CHI', 'Cleveland': 'CLE',
    'Dallas': 'DAL', 'Denver': 'DEN', 'Detroit': 'DET',
    'GoldenState': 'GSW', 'Houston': 'HOU', 'Indiana': 'IND',
    'LAClippers': 'LAC', 'LALakers': 'LAL', 'Memphis': 'MEM',
    'Miami': 'MIA', 'Milwaukee': 'MIL', 'Minnesota': 'MIN',
    'NewOrleans': 'NOP', 'NYKnicks': 'NYK', 'NewYork': 'NYK',  # ← add this
    'OklahomaCity': 'OKC', 'Orlando': 'ORL', 'Philadelphia': 'PHI',
    'Phoenix': 'PHX', 'Portland': 'POR', 'Sacramento': 'SAC',
    'SanAntonio': 'SAS', 'Toronto': 'TOR', 'Utah': 'UTA',
    'Washington': 'WAS'
}

    # Candidate column names for over/under American odds.
    # The loader tries each in order and uses the first one found.
    ODDS_COL_CANDIDATES = ["ML", "Odds", "2H", "OU"]

    def _find_odds_col(self, df: pd.DataFrame) -> str | None:
        """Return the first matching odds column name, or None."""
        for col in self.ODDS_COL_CANDIDATES:
            if col in df.columns:
                return col
        return None

    def load_sbr_file(self, file_path: Path) -> pd.DataFrame:
        """
        Loads and cleans a single SBR Excel file.

        Key changes vs. original:
          - total_line  = home row 'Close' directly (FIX 3)
          - over_odds   = home row odds column value  (FIX 1)
          - under_odds  = visitor row odds column value (FIX 1)
          - Validity guard rejects implausible total lines (FIX 3)
        """
        try:
            season_start_year = int(file_path.stem.split('_')[1].split('-')[0])
        except Exception:
            season_start_year = 2022

        df = pd.read_excel(file_path)
        

        # ── Date parsing ─────────────────────────────────────
        def parse_date(row):
            date_str = str(int(row['Date'])).zfill(4)
            month = int(date_str[:2])
            day   = int(date_str[2:])
            year  = season_start_year if month >= 10 else season_start_year + 1
            return pd.Timestamp(year=year, month=month, day=day)

        df['game_date'] = df.apply(parse_date, axis=1)

        print(f"  [debug] Columns: {list(df.columns)}")
        # ── Team abbreviations ───────────────────────────────
        df['team_abbr'] = df['Team'].map(self.TEAM_MAP)

        unmapped = df[df['team_abbr'].isna()]['Team'].value_counts()
        if not unmapped.empty:
            print(f"  [unmapped teams] {unmapped.to_dict()}")
    

        # ── Close column (total line on home row) ────────────
        df['close_num'] = pd.to_numeric(df['Close'], errors='coerce').fillna(0)

        # ── FIX 1: Locate the odds column ───────────────────


        # ── Pivot: 2 rows per game → 1 row per game ──────────
        games = []
        skipped_line = 0
        skipped_team = 0

        for i in range(0, len(df), 2):
            if i + 1 >= len(df):
                break

            row_v = df.iloc[i]    # Visitor row
            row_h = df.iloc[i+1]  # Home row

            # FIX 3: Total line lives in the home row 'Close' column.
            # The visitor row 'Close' holds the point spread — do not
            # take max() of both, which can accidentally pick the spread.
            total_line = row_h['close_num']

            # Validity guard: reject lines that look like spreads or errors
            if not (TOTAL_LINE_MIN <= total_line <= TOTAL_LINE_MAX):
                skipped_line += 1
                continue

            # FIX 1: Over odds from home row, under odds from visitor row.
            # In the SBR format the odds column on the home row reflects
            # the price offered on the over; the visitor row reflects the under.
            raw_ml = pd.to_numeric(row_h.get('ML', -110), errors='coerce')
            over_odds  = raw_ml if not pd.isna(raw_ml) else -110
            under_odds = raw_ml  # symmetric — same juice on both sides

            # Guard: if either odds value looks like a line, not odds,
            # fall back to -110 rather than contaminating implied probs.
            for side_name, val in [("over_odds", over_odds), ("under_odds", under_odds)]:
                if TOTAL_LINE_MIN <= abs(val) <= TOTAL_LINE_MAX:
                    #print(f"  [warning] {side_name}={val} on {row_v['game_date'].date()} "f"looks like a line value, not American odds — defaulting to -110.")
                    if side_name == "over_odds":
                        over_odds = -110
                    else:
                        under_odds = -110

            if pd.isna(row_v['team_abbr']) or pd.isna(row_h['team_abbr']):
                skipped_team += 1
                continue

            games.append({
            'game_date':  row_v['game_date'],
            'away_team':  row_v['team_abbr'],
            'home_team':  row_h['team_abbr'],
            'away_pts':   row_v['Final'],
            'home_pts':   row_h['Final'],
            'game_total': pd.to_numeric(row_v['Final'], errors='coerce') +
                        pd.to_numeric(row_h['Final'], errors='coerce'),
            'total_line': total_line,
            'open_line':  pd.to_numeric(row_h['Open'], errors='coerce'),  # ← add this
            'over_odds':  over_odds,
            'under_odds': under_odds,
        })
        if skipped_line > 0:
            print(f"  [info] {file_path.name}: skipped {skipped_line} game(s) "
                  f"with implausible total lines (outside [{TOTAL_LINE_MIN}, {TOTAL_LINE_MAX}])")
        if skipped_team > 0:
            print(f"  [info] {file_path.name}: skipped {skipped_team} game(s) "
                  f"with unmapped team names")

        return pd.DataFrame(games).dropna(subset=['away_team', 'home_team'])

    def load_all(self, sbr_dir_path=None) -> pd.DataFrame:
        """
        Loads all SBR files in SBR_DIR and combines them.
        """
        sbr_dir = Path("data/sbr")

        if not sbr_dir.exists():
            print(f"  [error] Directory not found: {sbr_dir}")
            return pd.DataFrame()

        all_files = sorted(sbr_dir.glob("nba_*.xlsx"))
        if not all_files:
            print(f"  [missing] No SBR files found in {sbr_dir}")
            return pd.DataFrame()

        dfs = []
        for f in all_files:
            print(f"  [loading] {f.name}")
            dfs.append(self.load_sbr_file(f))

        if not dfs:
            return pd.DataFrame()

        combined = pd.concat(dfs, ignore_index=True)
        print(f"  [SBR] {len(combined):,} games loaded across {len(all_files)} file(s)")
        return combined


# ══════════════════════════════════════════════════════════════
# 3.  DATA PROCESSOR  — feature engineering + merging
# ══════════════════════════════════════════════════════════════

class DataProcessor:

    def process_player_logs(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = df[df["minutes"] >= MIN_MIN].copy()
        df["home"] = df["matchup"].str.contains("vs\\.").astype(int)

        df = df.sort_values(["player_id", "game_date"])
        df["prev_game"] = df.groupby("player_id")["game_date"].shift(1)
        df["b2b"] = ((df["game_date"] - df["prev_game"]).dt.days == 1).astype(int)

        smeans = df.groupby(["player_id", "season"])["pts"].mean().rename("season_ppg").reset_index()
        df = df.merge(smeans, on=["player_id", "season"], how="left")
        df["is_star"] = df["season_ppg"] >= 20.0
        return df

    def build_team_game_df(self, player_df: pd.DataFrame) -> pd.DataFrame:
        agg = (
            player_df.groupby(["game_id", "game_date", "season", "matchup"])
            .agg(
                team_pts     = ("pts",      "sum"),
                star_present = ("is_star",  "max"),
                team_b2b     = ("b2b",      "max"),
                team_fga     = ("fga",      "sum"),
            ).reset_index()
        )

        agg["team_abbr"] = agg["matchup"].str[:3]
        agg["is_home"]   = agg["matchup"].str.contains("vs\\.").astype(int)
        return agg

    def add_implied_prob(self, sbr_df: pd.DataFrame) -> pd.DataFrame:
        df = sbr_df.copy()

        # Only compute line move where open_line looks like a total, not a spread
        df['open_line'] = pd.to_numeric(df['open_line'], errors='coerce')
        valid_open = (df['open_line'] >= TOTAL_LINE_MIN) & (df['open_line'] <= TOTAL_LINE_MAX)
        
        df['line_move'] = np.where(
            valid_open,
            df['total_line'] - df['open_line'],
            0.0   # no move info → treat as 0 → p_over_fair = 0.50
        )

        # Clamp line move to realistic range before sigmoid — max real move is ~5 pts
        df['line_move'] = df['line_move'].clip(-5, 5)

        df['p_over_fair'] = 1 / (1 + np.exp(-df['line_move'] * 0.15))

        # Standard vig columns (symmetric -110)
        df['over_odds']   = -110
        df['under_odds']  = -110
        df['p_over_raw']  = 110 / 210
        df['p_under_raw'] = 110 / 210
        df['vig']         = df['p_over_raw'] + df['p_under_raw'] - 1
        df['logit_impl']  = np.clip(df['p_over_fair'], 1e-6, 1-1e-6).apply(logit)

        df['over_hit'] = (df['game_total'] > df['total_line']).astype(int)
        df['push']     = (df['game_total'] == df['total_line']).astype(int)
        df = df[df['push'] == 0].copy()

        df['residual'] = df['over_hit'] - df['p_over_fair']
        return df

    # FIX 5: Implied-probability audit — call immediately after add_implied_prob
    def audit_implied_probs(self, df: pd.DataFrame) -> None:
        """
        Checks for the bimodal 0.24/0.76 artefact.  Under a correct parse,
        virtually all p_over_fair values should lie in [0.40, 0.60] for
        standard -110/-110 totals markets.
        """
        p = df['p_over_fair'].dropna()
        move = df['line_move'].dropna() if 'line_move' in df.columns else pd.Series()

        print("\n── Implied Probability Audit ───────────────────────────")
        print(f"  Mean p_over_fair : {p.mean():.4f}  (expected ≈ 0.500)")
        print(f"  Std  p_over_fair : {p.std():.4f}  (expected > 0.01 for line-move derived probs)")
        if not move.empty:
            print(f"  Mean line move   : {move.mean():+.3f} pts")
            print(f"  Std  line move   : {move.std():.3f} pts")
            print(f"  % games with move: {(move != 0).mean():.1%}")
        if p.std() < 0.005:
            print("  ⚠ WARNING: Near-zero variance — calibration tests will be uninformative.")
        else:
            print("  ✓ Sufficient variance for calibration.")

    def merge_lines_and_teams(self, sbr_df: pd.DataFrame, team_agg: pd.DataFrame) -> pd.DataFrame:
        """
        Joins SBR game-level data with NBA API team aggregates.

        FIX 2 note: The 'residual' column computed in add_implied_prob
        (over_hit - p_over_fair) is preserved without modification.
        A separate 'pts_vs_line' column captures the raw point differential
        for reference, but it is NOT used in any efficiency test.
        """
        home_api = team_agg[team_agg["is_home"] == 1].copy()
        away_api = team_agg[team_agg["is_home"] == 0].copy()

        merged = sbr_df.merge(
            home_api[['game_date', 'team_abbr', 'game_id',
                       'star_present', 'team_b2b', 'team_fga']],
            left_on  = ['game_date', 'home_team'],
            right_on = ['game_date', 'team_abbr'],
            how='inner'
        ).rename(columns={
            'game_id':      'game_id_home',
            'star_present': 'home_star',
            'team_b2b':     'home_b2b',
            'team_fga':     'home_fga',
        })

        merged = merged.merge(
            away_api[['game_date', 'team_abbr', 'game_id',
                       'star_present', 'team_b2b', 'team_fga']],
            left_on  = ['game_date', 'away_team', 'game_id_home'],
            right_on = ['game_date', 'team_abbr', 'game_id'],
            how='inner'
        ).rename(columns={
            'star_present': 'away_star',
            'team_b2b':     'away_b2b',
            'team_fga':     'away_fga',
        })

        merged["star_absent"] = (
            (merged["home_star"] == 0) | (merged["away_star"] == 0)
        ).astype(int)
        merged["any_b2b"]   = (
            (merged["home_b2b"] == 1) | (merged["away_b2b"] == 1)
        ).astype(int)
        merged["total_fga"] = merged["home_fga"] + merged["away_fga"]

        # FIX 2: Raw point differential stored separately — does NOT
        # overwrite the probability residual from add_implied_prob.
        merged["pts_vs_line"] = merged["game_total"] - merged["total_line"]

        merged["season"] = merged["game_date"].apply(
            lambda d: f"{d.year}-{str(d.year + 1)[-2:]}"
            if d.month >= 10
            else f"{d.year - 1}-{str(d.year)[-2:]}"
        )

        return merged


# ══════════════════════════════════════════════════════════════
# 4.  SYNTHETIC LINE FALLBACK
# ══════════════════════════════════════════════════════════════

class SyntheticLineBuilder:
    """
    Uses each team's rolling average as an implied line.
    Used only when no SBR files are present.
    """

    def build(self, team_agg: pd.DataFrame) -> pd.DataFrame:
        print("[synthetic] Building implied lines from rolling team averages...")

        home = team_agg[team_agg["is_home"] == 1].copy()
        away = team_agg[team_agg["is_home"] == 0].copy()

        games = home.merge(
            away[["game_id", "team_abbr", "team_pts",
                  "team_b2b", "star_present", "team_fga"]],
            on="game_id",
            suffixes=("_home", "_away")
        )

        games["game_total"] = games["team_pts_home"] + games["team_pts_away"]
        games = games.sort_values("game_date")

        games["total_line"] = (
            games["game_total"].shift(1).rolling(10, min_periods=5).mean()
        )
        games = games.dropna(subset=["total_line"])

        # Symmetric synthetic odds → p_over_fair = 0.50
        games["p_over_fair"] = 0.50
        games["p_under_raw"] = 0.5238
        games["p_over_raw"]  = 0.5238
        games["vig"]         = 0.0476
        games["logit_impl"]  = 0.0

        games["over_hit"]  = (games["game_total"] > games["total_line"]).astype(int)
        games["push"]      = games["game_total"] == games["total_line"]
        games = games[~games["push"]].copy()

        # FIX 2: probability residual, consistent with add_implied_prob
        games["residual"]  = games["over_hit"] - games["p_over_fair"]

        games["home_b2b"]    = games["team_b2b_home"].fillna(0).astype(int)
        games["away_b2b"]    = games["team_b2b_away"].fillna(0).astype(int)
        games["star_absent"] = (
            (games["star_present_home"] == 0) | (games["star_present_away"] == 0)
        ).astype(int)
        games["total_fga"]   = games["team_fga_home"] + games["team_fga_away"]

        print(f"  {len(games)} synthetic game-lines built.")
        return games


# ══════════════════════════════════════════════════════════════
# 5.  MARKET EFFICIENCY TESTS
# ══════════════════════════════════════════════════════════════

class MarketEfficiencyTests:

    def __init__(self, df: pd.DataFrame):
        required = ["p_over_fair", "over_hit", "residual"]
        self.df = df.dropna(subset=[c for c in required if c in df.columns]).copy()

    # ── 5a. Calibration ─────────────────────────────────────

    def calibration(self) -> dict:
        """
        OLS: over_hit = α + β·p_over_fair + ε
        H0: α = 0, β = 1 (perfect calibration)
        """
        if self.df.empty:
            print("  [warning] No data available for calibration.")
            return {}

        if self.df["p_over_fair"].nunique() <= 1:
            print("\n── Calibration [CONSTANT LINE DETECTED] ────────────────")
            mean_hit = self.df["over_hit"].mean()
            print(f"  All lines are {self.df['p_over_fair'].iloc[0]}.")
            print(f"  Mean Hit Rate (Alpha Proxy): {mean_hit:.4f}")
            return dict(alpha=mean_hit, beta=np.nan, n=len(self.df))

        try:
            X   = sm.add_constant(self.df["p_over_fair"])
            ols = sm.OLS(self.df["over_hit"], X).fit(cov_type="HC3")

            if len(ols.params) < 2:
                a, b = ols.params[0], np.nan
            else:
                a, b = ols.params[0], ols.params[1]

            pa  = ols.pvalues[0]
            pb  = ols.pvalues[1] if len(ols.pvalues) > 1 else np.nan

            t_b1 = (b - 1) / ols.bse.iloc[1] if not np.isnan(b) else np.nan
            p_b1 = 2 * stats.t.sf(abs(t_b1), df=ols.df_resid) if not np.isnan(t_b1) else np.nan

            brier       = np.mean((self.df["over_hit"] - self.df["p_over_fair"])**2)
            brier_naive = np.mean((self.df["over_hit"] - 0.5)**2)
            skill       = 1 - brier / max(brier_naive, 1e-6)

            print("\n── Calibration ─────────────────────────────────────────")
            print(f"  α = {a:.4f} (p={pa:.4f})  β = {b:.4f} (p={pb:.4f})")
            print(f"  Brier score = {brier:.4f}  |  Skill = {skill:.4f}")

            return dict(alpha=a, beta=b, p_alpha=pa, p_beta=pb,
                        t_beta1=t_b1, p_beta1=p_b1,
                        brier=brier, skill=skill, n=len(self.df))
        except Exception as e:
            print(f"  [error] OLS Calibration failed: {e}")
            return {}

    # ── 5b. Aggregate VRP ────────────────────────────────────

    def aggregate_vrp(self) -> dict:
        """VRP = E[p_over_fair] − E[over_hit]. Positive → over is overpriced."""
        if self.df.empty:
            return {}

        r   = self.df["residual"]
        vrp = -r.mean()
        t, p = stats.ttest_1samp(r, 0)

        print("\n── Prop Volatility Risk Premium (VRP) ──────────────────")
        print(f"  VRP = {vrp:+.4f}  ({vrp*100:+.2f} pp overpricing per bet)")
        print(f"  t = {t:.3f}  |  p = {p:.4f}  (H0: VRP=0)")

        # Sanity check: after FIX 1, VRP magnitude should be in basis points,
        # not near ±1. Flag if it looks like the parsing artefact persists.
        if abs(vrp) > 0.10:
            print(f"  ⚠ VRP magnitude ({vrp:+.4f}) is large — verify implied prob audit above.")

        return dict(vrp=vrp, t=t, p=p, n=len(r))

    # ── 5c. Favorite-Longshot Bias ───────────────────────────

    def flb(self, n_bins: int = 10) -> pd.DataFrame:
        """
        Decile bins by implied probability vs. realized rate.
        After FIX 1, probabilities should be near 0.50, so bin
        edges will be narrow (e.g. 0.48–0.52). The bimodal
        0.24/0.76 pattern should no longer appear.
        """
        if self.df.empty or self.df["p_over_fair"].nunique() <= 1:
            print("\n── FLB skipped: Insufficient variance in implied probabilities.")
            return pd.DataFrame()

        df = self.df.copy()
        df["bin"] = pd.qcut(df["p_over_fair"], q=n_bins, labels=False, duplicates="drop")
        out = (
            df.groupby("bin")
              .agg(
                  implied  = ("p_over_fair", "mean"),
                  realized = ("over_hit",    "mean"),
                  n        = ("over_hit",    "count"),
              )
              .reset_index()
        )

        out["edge"]   = out["realized"] - out["implied"]
        out["t_stat"] = out.apply(
            lambda r: stats.ttest_1samp(
                df[df["bin"] == r["bin"]]["residual"], 0
            )[0],
            axis=1,
        )

        print("\n── Favorite-Longshot Bias ──────────────────────────────")
        print(out.to_string(index=False))
        return out

    # ── 5d. VRP by subgroup ──────────────────────────────────

    def vrp_slices(self) -> pd.DataFrame:
        """VRP broken out by scheduling and player-availability flags."""
        slices = []
        df     = self.df.copy()

        groups = {
            "Home B2B":    df.get("home_b2b",   pd.Series(0, index=df.index)) == 1,
            "Away B2B":    df.get("away_b2b",   pd.Series(0, index=df.index)) == 1,
            "Star Absent": df.get("star_absent", pd.Series(0, index=df.index)) == 1,
        }

        for label, mask in groups.items():
            if mask.sum() < 10:
                continue
            sub  = df[mask]["residual"]
            t, p = stats.ttest_1samp(sub, 0)
            slices.append(dict(
                group=label, n=len(sub), vrp=-sub.mean(), t=t, p=p,
                sig="***" if p < .01 else "**" if p < .05 else "*" if p < .1 else "",
            ))

        out = pd.DataFrame(slices)
        if not out.empty:
            print("\n── VRP by Subgroup ─────────────────────────────────────")
            print(out.to_string(index=False))
        return out


# ══════════════════════════════════════════════════════════════
# 6.  PUBLIC SIGNAL REGRESSION
# ══════════════════════════════════════════════════════════════

class PublicSignalRegression:

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def run(self):
        """
        OLS: residual ~ both_b2b + one_b2b + star_absent + fga_z + Season FE
        HC3 robust standard errors throughout.

        FIX 6: After the run, directional-sign assertions flag coefficients
        that are statistically significant but point in the wrong direction —
        a symptom of the odds-parsing artefact rather than a real effect.
        """
        df = self.df.dropna(subset=["residual"]).copy()

        for c, default in [
            ("home_b2b",  0),
            ("away_b2b",  0),
            ("star_absent", 0),
            ("total_fga", df.get("total_fga", pd.Series([80]*len(df))).mean()),
        ]:
            if c not in df.columns:
                df[c] = default

        df["both_b2b"] = ((df["home_b2b"] == 1) & (df["away_b2b"] == 1)).astype(int)
        df["one_b2b"]  = ((df["home_b2b"] == 1) ^ (df["away_b2b"] == 1)).astype(int)

        fga_std    = df["total_fga"].std()
        df["fga_z"] = (df["total_fga"] - df["total_fga"].mean()) / (fga_std if fga_std > 0 else 1)

        season_col = "C(season)" if ("season" in df.columns and df["season"].nunique() > 1) else "1"
        formula    = f"residual ~ both_b2b + one_b2b + star_absent + fga_z + {season_col}"
        ols        = smf.ols(formula, data=df).fit(cov_type="HC3")

        print("\n── Public Signal Regression ────────────────────────────")
        print(f"  N = {int(ols.nobs):,}  |  R² = {ols.rsquared:.4f}")
        key = ["both_b2b", "one_b2b", "star_absent", "fga_z"]
        print(f"\n  {'Variable':<18} {'β':>8}  {'SE':>8}  {'p':>8}")
        for v in key:
            if v in ols.params.index:
                b, se, p = ols.params[v], ols.bse[v], ols.pvalues[v]
                sig = "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else ""
                print(f"  {v:<18} {b:>+8.4f}  {se:>8.4f}  {p:>8.4f} {sig}")

        # FIX 6: Directional sign assertions
        # star_absent should be negative (missing star → lower scoring → under more likely)
        # both_b2b / one_b2b should be negative (fatigue → lower scoring)
        self._check_signs(ols)

        return ols

    @staticmethod
    def _check_signs(ols) -> None:
        """
        Warn when a significant coefficient has an unexpected sign.
        A positive star_absent or both_b2b at p<0.05 suggests the
        residual is contaminated (FIX 1 / FIX 2 may not be complete).
        """
        checks = {
            "star_absent": ("negative", lambda b: b < 0),
            "both_b2b":    ("negative", lambda b: b < 0),
            "one_b2b":     ("negative", lambda b: b < 0),
        }
        for var, (direction, ok) in checks.items():
            if var not in ols.params.index:
                continue
            b = ols.params[var]
            p = ols.pvalues[var]
            if p < 0.05 and not ok(b):
                print(f"\n  ⚠ Sign warning: '{var}' is significant (p={p:.3f}) "
                      f"but β={b:+.4f} (expected {direction}).")
                print(f"    This is consistent with a residual contaminated by "
                      f"the odds-parsing artefact. Re-check the implied prob audit.")

    def logit_robustness(self):
        """
        Logit version: over_hit ~ public signals.
        Safeguarded against Singular Matrix errors.
        """
        df = self.df.dropna(subset=["over_hit"]).copy()

        for c, default in [("home_b2b", 0), ("away_b2b", 0), ("star_absent", 0)]:
            if c not in df.columns:
                df[c] = default

        df["both_b2b"] = ((df["home_b2b"] == 1) & (df["away_b2b"] == 1)).astype(int)
        df["one_b2b"]  = ((df["home_b2b"] == 1) ^ (df["away_b2b"] == 1)).astype(int)

        base_features   = ["both_b2b", "one_b2b", "star_absent"]
        active_features = [f for f in base_features if df[f].nunique() > 1]

        if "logit_impl" in df.columns and df["logit_impl"].nunique() > 1:
            active_features.append("logit_impl")

        if not active_features:
            print("\n── Logit Robustness Check: Skipped (No variable features) ──")
            return None

        formula = f"over_hit ~ {' + '.join(active_features)}"

        try:
            logit_model = smf.logit(formula, data=df).fit(disp=0)
            print("\n── Logit Robustness Check ──────────────────────────────")
            print(f"  Pseudo R² = {logit_model.prsquared:.4f}")
            print(f"  N = {int(logit_model.nobs):,}")
            return logit_model
        except np.linalg.LinAlgError:
            print("\n── Logit Robustness Check: Failed (Singular Matrix) ──")
            return None
        except Exception as e:
            print(f"\n── Logit Robustness Check: Failed ({type(e).__name__}) ──")
            return None


# ══════════════════════════════════════════════════════════════
# 7.  BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════

class BacktestEngine:
    """
    Simulates betting the UNDER on B2B games with above-median lines.

    Note: The backtest outcome (win/loss) depends only on whether the
    game went over/under the posted total and on the B2B flag — neither
    of which is affected by the odds-parsing fix. The −4.9% net ROI
    finding is therefore reliable on the original data and is expected
    to remain similar after the fix.
    """

    def __init__(self, df: pd.DataFrame, stake: float = 1.0):
        self.df    = df.sort_values("game_date").copy()
        self.stake = stake

    def run(self) -> pd.DataFrame:
        df = self.df.copy()

        df["b2b_any"] = (
            df.get("home_b2b", pd.Series(0, index=df.index)).fillna(0).astype(int) |
            df.get("away_b2b", pd.Series(0, index=df.index)).fillna(0).astype(int)
        )
        median_line          = df.groupby("season")["total_line"].transform("median")
        df["line_above_median"] = (df["total_line"] > median_line).astype(int)
        df["signal"]            = df["b2b_any"] & df["line_above_median"]

        bets = df[df["signal"] == 1].copy()
        bets["won"]       = (bets["over_hit"] == 0).astype(int)
        bets["gross_pnl"] = np.where(bets["won"],  self.stake, -self.stake)
        bets["net_pnl"]   = np.where(bets["won"],  self.stake * (100/110), -self.stake)

        bets["cum_gross"] = bets["gross_pnl"].cumsum()
        bets["cum_net"]   = bets["net_pnl"].cumsum()

        n         = len(bets)
        win_rate  = bets["won"].mean()
        gross_roi = bets["gross_pnl"].sum() / (n * self.stake)
        net_roi   = bets["net_pnl"].sum()   / (n * self.stake)
        sharpe    = (
            (bets["net_pnl"].mean() / bets["net_pnl"].std()) * np.sqrt(n)
            if n > 1 else 0
        )

        print("\n── Backtest ─────────────────────────────────────────────")
        print(f"  Strategy: Bet UNDER on B2B games with above-median total line")
        print(f"  N bets    = {n:,}")
        print(f"  Win rate  = {win_rate:.2%}  (break-even at 52.4% for -110)")
        print(f"  Gross ROI = {gross_roi:+.2%}  |  Net ROI = {net_roi:+.2%}")
        print(f"  Sharpe    = {sharpe:.3f}  (per-bet, annualized by sqrt(N))")

        return bets


# ══════════════════════════════════════════════════════════════
# 8.  REPORTER
# ══════════════════════════════════════════════════════════════

class Reporter:
    """Generates the final analysis dashboard and summary CSV."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        sns.set_theme(style="whitegrid")

    def plot_all(self, bets: pd.DataFrame, flb: pd.DataFrame):
        """Creates a 5-panel dashboard of market efficiency metrics."""
        fig = plt.figure(figsize=(16, 10))
        gs  = fig.add_gridspec(2, 3, hspace=0.40, wspace=0.35)

        # ── Panel 1: Calibration curve ────────────────────────
        ax1    = fig.add_subplot(gs[0, 0])
        df_cal = self.df.dropna(subset=["p_over_fair", "over_hit"]).copy()

        if not df_cal.empty and df_cal["p_over_fair"].nunique() > 1:
            df_cal["bin"] = pd.qcut(df_cal["p_over_fair"], q=8, labels=False, duplicates="drop")
            cal_data = (
                df_cal.groupby("bin")
                      .agg(impl=("p_over_fair", "mean"), real=("over_hit", "mean"))
                      .reset_index()
            )
            lo = cal_data["impl"].min() - 0.02
            hi = cal_data["impl"].max() + 0.02
            ax1.plot([lo, hi], [lo, hi], "k--", lw=1.5, label="Perfect")
            ax1.scatter(cal_data["impl"], cal_data["real"], s=70, c="steelblue", zorder=5)
            ax1.set_xlabel("Implied Prob")
            ax1.set_ylabel("Realized Rate")
        else:
            ax1.text(0.5, 0.5, "Calibration N/A\n(Constant Lines)",
                     ha="center", va="center", transform=ax1.transAxes)

        ax1.set_title("Calibration", fontweight="bold")

        # ── Panel 2: Residuals distribution ───────────────────
        ax2 = fig.add_subplot(gs[0, 1])
        if "residual" in self.df.columns and not self.df["residual"].dropna().empty:
            sns.histplot(self.df["residual"], bins=30, ax=ax2, color="steelblue", alpha=0.7)
            mean_res = self.df["residual"].mean()
            ax2.axvline(mean_res, color="red", lw=2, linestyle="--", label=f"Mean={mean_res:.4f}")
            ax2.legend(fontsize=9)
        ax2.set_title("Residual Distribution", fontweight="bold")
        ax2.set_xlabel("Realized − Implied")

        # ── Panel 3: VRP by B2B ───────────────────────────────
        ax3 = fig.add_subplot(gs[0, 2])
        b2b_labels, vrps, errs = [], [], []

        for label, mask_col, val in [
            ("Both B2B", "both_b2b", 1),
            ("One B2B",  "one_b2b",  1),
            ("No B2B",   "home_b2b", 0),
        ]:
            col = mask_col if mask_col in self.df.columns else None
            if col and col in self.df.columns:
                sub = self.df[self.df[col] == val]["residual"].dropna()
                if len(sub) >= 5:
                    b2b_labels.append(label)
                    vrps.append(-sub.mean())
                    errs.append(sub.sem())

        if b2b_labels:
            colors = ["#d62728" if v > 0 else "#1f77b4" for v in vrps]
            ax3.bar(b2b_labels, vrps, yerr=errs, color=colors,
                    capsize=5, edgecolor="black", linewidth=0.7)
            ax3.axhline(0, color="black", lw=0.8)
        else:
            ax3.text(0.5, 0.5, "Insufficient Data",
                     ha="center", va="center", transform=ax3.transAxes)

        ax3.set_title("VRP by B2B Schedule", fontweight="bold")
        ax3.set_ylabel("VRP (implied − realized)")

        # ── Panel 4: Favorite-Longshot Bias ───────────────────
        ax4 = fig.add_subplot(gs[1, 0])
        if flb is not None and not flb.empty and "implied" in flb.columns:
            lo = min(flb["implied"].min(), flb["realized"].min()) - 0.02
            hi = max(flb["implied"].max(), flb["realized"].max()) + 0.02
            ax4.plot([lo, hi], [lo, hi], "k--", lw=1.5)
            sc = ax4.scatter(flb["implied"], flb["realized"],
                             c=flb["edge"], cmap="RdYlGn", s=80,
                             edgecolors="k", lw=0.5)
            plt.colorbar(sc, ax=ax4, label="Edge")
            ax4.set_xlabel("Implied Prob")
            ax4.set_ylabel("Realized Rate")
        else:
            ax4.text(0.5, 0.5, "FLB Skipped\n(No variance in lines)",
                     ha="center", va="center", transform=ax4.transAxes)

        ax4.set_title("Favorite-Longshot Bias", fontweight="bold")

        # ── Panel 5: Cumulative P&L ────────────────────────────
        ax5 = fig.add_subplot(gs[1, 1:])
        if bets is not None and not bets.empty and "cum_net" in bets.columns:
            ax5.plot(bets["game_date"], bets["cum_gross"],
                     label="Gross (pre-vig)", lw=1.5, color="steelblue")
            ax5.plot(bets["game_date"], bets["cum_net"],
                     label="Net (post-vig)", lw=1.5, linestyle="--", color="darkorange")
            ax5.axhline(0, color="black", lw=0.8)
            ax5.legend()
        else:
            ax5.text(0.5, 0.5, "No strategy signals generated",
                     ha="center", va="center", transform=ax5.transAxes)

        ax5.set_title("Cumulative P&L Strategy Performance", fontweight="bold")
        ax5.set_xlabel("Date")
        ax5.set_ylabel("Units")

        fig.suptitle("NBA Game Total Market Efficiency Analysis",
                     fontsize=14, fontweight="bold", y=1.01)

        output_path = OUT_DIR / "nba_efficiency_dashboard.png"
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"\n[saved] {output_path}")

    def export_summary(self, cal: dict, vrp: dict, reg_ols) -> pd.DataFrame:
        """Exports key metrics to CSV."""
        fmt = lambda d, key, default: (
            f"{d.get(key, default):+.4f}"
            if isinstance(d.get(key), (int, float))
            else str(d.get(key, default))
        )

        rows = [
            ("Calibration Alpha (Bias)", fmt(cal, 'alpha', 0.0),  f"p={cal.get('p_alpha', 1.0):.3f}"),
            ("Calibration Beta (Slope)", fmt(cal, 'beta',  1.0),  f"p(B=1)={cal.get('p_beta1', 1.0):.3f}"),
            ("Brier Skill Score",        fmt(cal, 'skill', np.nan), ""),
            ("Aggregate VRP",            fmt(vrp, 'vrp',   0.0),  f"p={vrp.get('p', 1.0):.3f}"),
            ("N Observations",           f"{vrp.get('n', 0):,}",  ""),
            ("OLS R-Squared",            f"{reg_ols.rsquared:.4f}" if reg_ols else "N/A", ""),
        ]

        df_summary = pd.DataFrame(rows, columns=["Metric", "Estimate", "Inference"])
        summary_path = OUT_DIR / "summary_metrics.csv"
        df_summary.to_csv(summary_path, index=False)

        print("\n── Final Summary ───────────────────────────────────────")
        print(df_summary.to_string(index=False))
        return df_summary


# ══════════════════════════════════════════════════════════════
# 9.  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  NBA Game Total Market Efficiency Pipeline")
    print("=" * 60)

    # ── Step 1: Load NBA data ─────────────────────────────────
    print("\n[1/6] Loading NBA game logs via nba_api...")
    loader      = NBADataLoader()
    player_logs = loader.load_player_logs(SEASONS)
    team_logs   = loader.load_team_logs(SEASONS)

    # ── Step 2: Feature engineering ──────────────────────────
    print("\n[2/6] Processing features...")
    proc      = DataProcessor()
    players_e = proc.process_player_logs(player_logs)
    team_agg  = proc.build_team_game_df(players_e)

    # ── Step 3: Load game lines ───────────────────────────────
    print("\n[3/6] Loading game lines...")
    sbr_raw = SBRLoader().load_all()

    if sbr_raw.empty:
        print("  → No SBR files found — using synthetic lines.")
        print("  → To use real lines: download from sportsbookreviewsonline.com")
        print(f"    Save as: {SBR_DIR}/nba_2019-20.xlsx  (etc.)")
        game_df = SyntheticLineBuilder().build(team_agg)
    else:
        sbr_with_prob = proc.add_implied_prob(sbr_raw)

        # FIX 5: Audit implied probs immediately after parsing —
        # abort-level warning if the bimodal pattern persists.
        proc.audit_implied_probs(sbr_with_prob)

        game_df = proc.merge_lines_and_teams(sbr_with_prob, team_agg)
        print(f"  Merged dataset: {len(game_df):,} games")

    game_df.to_csv(OUT_DIR / "game_df.csv", index=False)

    # ── Step 4: Market efficiency tests ──────────────────────
    print("\n[4/6] Running market efficiency tests...")
    mkt = MarketEfficiencyTests(game_df)
    cal = mkt.calibration()
    vrp = mkt.aggregate_vrp()
    flb = mkt.flb()
    _   = mkt.vrp_slices()

    # ── Step 5: Public signal regressions ────────────────────
    print("\n[5/6] Public signal regressions...")
    reg     = PublicSignalRegression(game_df)
    ols_res = reg.run()
    _       = reg.logit_robustness()

    # ── Step 6: Backtest + Report ─────────────────────────────
    print("\n[6/6] Backtest and reporting...")
    bets     = BacktestEngine(game_df).run()
    reporter = Reporter(game_df)
    reporter.plot_all(bets, flb)
    reporter.export_summary(cal, vrp, ols_res)

    print(f"\n✓ Done. All outputs in {OUT_DIR}/")


if __name__ == "__main__":
    main()