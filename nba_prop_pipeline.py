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
        nba_2021-22.xlsx
        nba_2022-23.xlsx
        nba_2023-24.xlsx
  The files are a known format in sports analytics — each row is one
  team-game, paired (away row then home row). Spread on away row,
  total on home row, inside the "Close" column.
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

warnings.filterwarnings("ignore")
pd.set_option("display.float_format", "{:.4f}".format)
pd.set_option("display.max_columns", None)

# ──────────────────────────────────────────────────────────────
#  CONFIG  — edit paths, nothing else should need changing
# ──────────────────────────────────────────────────────────────

DATA_DIR   = Path("data")
SBR_DIR    = Path("data/sbr")       # put your downloaded SBR Excel files here
OUT_DIR    = Path("data/outputs")
SEASONS    = ["2021-22", "2022-23", "2023-24"]
MIN_GAMES  = 20                     # min games per player-season
MIN_MIN    = 10                     # drop DNPs / garbage time

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
            # Force lowercase and remove any duplicate columns that might have been cached
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
                    
                    # Ensure we don't create duplicate ID/Name columns
                    # Only add them if the API didn't provide them
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
        
        # Standardize and deduplicate
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
    """
    
    # Map from image_fe2ebd.png Team names to image_fe2ec0.png team_abbr
    TEAM_MAP = {
        'Atlanta': 'ATL', 'Boston': 'BOS', 'Brooklyn': 'BKN', 
        'Charlotte': 'CHA', 'Chicago': 'CHI', 'Cleveland': 'CLE', 
        'Dallas': 'DAL', 'Denver': 'DEN', 'Detroit': 'DET', 
        'GoldenState': 'GSW', 'Houston': 'HOU', 'Indiana': 'IND', 
        'LAClippers': 'LAC', 'LALakers': 'LAL', 'Memphis': 'MEM', 
        'Miami': 'MIA', 'Milwaukee': 'MIL', 'Minnesota': 'MIN', 
        'NewOrleans': 'NOP', 'NYKnicks': 'NYK', 'OklahomaCity': 'OKC', 
        'Orlando': 'ORL', 'Philadelphia': 'PHI', 'Phoenix': 'PHX', 
        'Portland': 'POR', 'Sacramento': 'SAC', 'SanAntonio': 'SAS', 
        'Toronto': 'TOR', 'Utah': 'UTA', 'Washington': 'WAS'
    }

    def load_sbr_file(self, file_path: Path) -> pd.DataFrame:
        """Loads and cleans a single SBR Excel file."""
        # 1. Extract year from filename (e.g., nba_2022-23.xlsx -> 2022)
        try:
            season_start_year = int(file_path.stem.split('_')[1].split('-')[0])
        except Exception:
            season_start_year = 2022 # Fallback
            
        df = pd.read_excel(file_path)
        
        # 2. Fix the Date (Converts 1018 to 2022-10-18)
        def parse_date(row):
            date_str = str(int(row['Date'])).zfill(4)
            month = int(date_str[:2])
            day = int(date_str[2:])
            # If month is Oct-Dec, it's the start year. Jan-July is next year.
            year = season_start_year if month >= 10 else season_start_year + 1
            return pd.Timestamp(year=year, month=month, day=day)

        df['game_date'] = df.apply(parse_date, axis=1)
        
        # 3. Standardize Team Abbreviations
        df['team_abbr'] = df['Team'].map(self.TEAM_MAP)
        
        # 4. Clean Odds (Handle 'pk' or non-numeric strings)
        df['close_num'] = pd.to_numeric(df['Close'], errors='coerce').fillna(0)
        
        # 5. Pivot from 2 rows per game to 1 row per game
        # SBR format: Row 1 is Visitor (V), Row 2 is Home (H)
        games = []
        # Step through by 2s because every two rows is one game
        for i in range(0, len(df), 2):
            if i + 1 >= len(df): break
            
            row_v = df.iloc[i]   # Visitor
            row_h = df.iloc[i+1] # Home
            
            # Identify the Total Line: It's the higher of the two 'Close' numbers
            # (The lower number is the point spread)
            total_line = max(row_v['close_num'], row_h['close_num'])
            
            over_odds  = row_h['close_num']   # home row carries the total odds
            under_odds = row_v['close_num']   # visitor row carries the spread; use symmetry if missing
            games.append({
                'game_date':  row_v['game_date'],
                'away_team':  row_v['team_abbr'],
                'home_team':  row_h['team_abbr'],
                'away_pts':   row_v['Final'],
                'home_pts':   row_h['Final'],
                'game_total': row_v['Final'] + row_h['Final'],
                'total_line': total_line,
                'over_odds':  over_odds,
                'under_odds': under_odds,
            })
            
        return pd.DataFrame(games).dropna(subset=['away_team', 'home_team'])

    def load_all(self, sbr_dir_path: str) -> pd.DataFrame:
        """
        Loads all SBR files in the directory and combines them.
        Fixes the AttributeError by ensuring sbr_dir is a Path object.
        """
        # Convert the input (string or list) to a Path object pointing to your folder
        # If SEASONS was passed by mistake, we default to the DATA_DIR/sbr path
        from pathlib import Path
        
        # Ensure we are looking at the directory, not a list of seasons
        sbr_dir = Path("data/sbr") 
        
        if not sbr_dir.exists():
            print(f"  [error] Directory not found: {sbr_dir}")
            return pd.DataFrame()

        all_files = list(sbr_dir.glob("nba_*.xlsx"))
        if not all_files:
            print(f"  [missing] No SBR files found in {sbr_dir}")
            return pd.DataFrame()
            
        dfs = []
        for f in all_files:
            print(f"  [loading] {f.name}")
            # Use the logic from the previous step to parse the file
            dfs.append(self.load_sbr_file(f))
            
        if not dfs:
            return pd.DataFrame()
            
        return pd.concat(dfs, ignore_index=True)


# ══════════════════════════════════════════════════════════════
# 3.  DATA PROCESSOR  — feature engineering + merging
# ══════════════════════════════════════════════════════════════

class DataProcessor:
    def process_player_logs(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = df[df["minutes"] >= MIN_MIN].copy()
        df["home"] = df["matchup"].str.contains("vs\\.").astype(int)

        # Rest/Fatigue logic
        df = df.sort_values(["player_id", "game_date"])
        df["prev_game"] = df.groupby("player_id")["game_date"].shift(1)
        df["b2b"] = ((df["game_date"] - df["prev_game"]).dt.days == 1).astype(int)

        # Star classification (needed for Star DNP signal)
        smeans = df.groupby(["player_id", "season"])["pts"].mean().rename("season_ppg").reset_index()
        df = df.merge(smeans, on=["player_id", "season"], how="left")
        df["is_star"] = df["season_ppg"] >= 20.0
        return df

    def build_team_game_df(self, player_df: pd.DataFrame) -> pd.DataFrame:
        """
        This creates the 'Bridge' by aggregating player data into team rows 
        that match the structure of your Excel rows.
        """
        # Group by game_id to get team-level aggregates
        agg = (
            player_df.groupby(["game_id", "game_date", "season", "matchup"])
            .agg(
                team_pts = ("pts", "sum"),
                star_present = ("is_star", "max"), 
                team_b2b = ("b2b", "max"),
                team_fga = ("fga", "sum"),
            ).reset_index()
        )
        
        # Determine the team abbreviation from the matchup string (e.g., 'BOS' vs 'PHI')
        agg["team_abbr"] = agg["matchup"].str[:3] 
        agg["is_home"] = agg["matchup"].str.contains("vs\\.").astype(int)
        
        return agg

    def add_implied_prob(self, sbr_df: pd.DataFrame) -> pd.DataFrame:

        df = sbr_df.copy()

        def american_to_raw_prob(odds):
            """Convert American odds (scalar or Series) to raw implied probability."""
            odds = pd.to_numeric(odds, errors='coerce').fillna(-110)
            return np.where(
                odds < 0,
                np.abs(odds) / (np.abs(odds) + 100),   # favourite side: -110 → 0.5238
                100          / (odds + 100)             # underdog side:  +110 → 0.4762
            )

        # Fall back to symmetric -110 if odds columns weren't preserved by the loader
        if 'over_odds' not in df.columns:
            df['over_odds']  = -110
            df['under_odds'] = -110

        raw_over  = american_to_raw_prob(df['over_odds'])
        raw_under = american_to_raw_prob(df['under_odds'])

        df['p_over_raw']   = raw_over
        df['p_under_raw']  = raw_under
        df['vig']          = raw_over + raw_under - 1          # bookmaker margin
        df['p_over_fair']  = raw_over / (raw_over + raw_under) # vig-stripped probability
        df['logit_impl']   = np.clip(df['p_over_fair'], 1e-6, 1 - 1e-6).apply(logit)

        # Outcome columns needed downstream
        df['over_hit'] = (df['game_total'] > df['total_line']).astype(int)
        df['push']     = (df['game_total'] == df['total_line']).astype(int)
        df = df[df['push'] == 0].copy()
        df['residual'] = df['over_hit'] - df['p_over_fair']

        return df

    def merge_lines_and_teams(self, sbr_df: pd.DataFrame, team_agg: pd.DataFrame) -> pd.DataFrame:
        """
        The Crucial Step: Joining the 'game_id' from API onto your Excel rows
        using Date and Team as keys.
        """
        # Separate the API data into Home and Away sets
        home_api = team_agg[team_agg["is_home"] == 1].copy()
        away_api = team_agg[team_agg["is_home"] == 0].copy()

        # Merge Excel Home Team
        merged = sbr_df.merge(
            home_api[['game_date', 'team_abbr', 'game_id', 'star_present', 'team_b2b', 'team_fga']],
            left_on=['game_date', 'home_team'],
            right_on=['game_date', 'team_abbr'],
            how='inner'
        ).rename(columns={'game_id': 'game_id_home', 'star_present': 'home_star', 'team_b2b': 'home_b2b', 'team_fga': 'home_fga'})

        # Merge Excel Away Team
        merged = merged.merge(
            away_api[['game_date', 'team_abbr', 'game_id', 'star_present', 'team_b2b', 'team_fga']],
            left_on=['game_date', 'away_team', 'game_id_home'], # match game_id to ensure same game
            right_on=['game_date', 'team_abbr', 'game_id'],
            how='inner'
        ).rename(columns={'star_present': 'away_star', 'team_b2b': 'away_b2b', 'team_fga': 'away_fga'})

        # Feature Engineering for the Regression
        merged["star_absent"] = ((merged["home_star"] == 0) | (merged["away_star"] == 0)).astype(int)
        merged["any_b2b"] = ((merged["home_b2b"] == 1) | (merged["away_b2b"] == 1)).astype(int)
        merged["total_fga"] = merged["home_fga"] + merged["away_fga"]
        merged["residual"] = merged["game_total"] - merged["total_line"]

        merged["season"] = merged["game_date"].apply(lambda d: f"{d.year}-{str(d.year + 1)[-2:]}" if d.month >= 10 else f"{d.year - 1}-{str(d.year)[-2:]}")

        return merged


# ══════════════════════════════════════════════════════════════
# 4.  SYNTHETIC LINE FALLBACK
#     When no SBR data: construct a "consensus expected total"
#     from rolling team averages — tests the same efficiency H0
# ══════════════════════════════════════════════════════════════

class SyntheticLineBuilder:
    """
    Uses each team's rolling average as an implied line.
    Handles the column suffixing that occurs during the home/away merge.
    """

    def build(self, team_agg: pd.DataFrame) -> pd.DataFrame:
        print("[synthetic] Building implied lines from rolling team averages...")

        # 1. Pivot to game level
        home = team_agg[team_agg["is_home"] == 1].copy()
        away = team_agg[team_agg["is_home"] == 0].copy()

        # 2. Merge on game_id
        # Every column shared by home and away (except game_id) will get a suffix
        games = home.merge(
            away[["game_id", "team_abbr", "team_pts", "team_b2b", "star_present", "team_fga"]],
            on="game_id", 
            suffixes=("_home", "_away")
        )
        
        # FIX: Reference the suffixed columns
        games["game_total"] = games["team_pts_home"] + games["team_pts_away"]
        games = games.sort_values("game_date")

        # 3. Rolling 10-game average as proxy for "the line"
        games["total_line"] = (
            games["game_total"].shift(1).rolling(10, min_periods=5).mean()
        )
        games = games.dropna(subset=["total_line"])

        # 4. Market Probability Constants
        games["p_over_fair"] = 0.50
        games["p_under_raw"] = 0.5238
        games["p_over_raw"]  = 0.5238
        games["vig"]         = 0.0476
        games["logit_impl"]  = 0.0

        # 5. Calculate Residuals
        games["over_hit"]  = (games["game_total"] > games["total_line"]).astype(int)
        games["push"]      = games["game_total"] == games["total_line"]
        games = games[~games["push"]].copy()
        games["residual"]  = games["over_hit"] - games["p_over_fair"]

        # 6. Feature Engineering
        # Ensure we use the correct suffixed names for all features
        games["home_b2b"]    = games["team_b2b_home"].fillna(0).astype(int)
        games["away_b2b"]    = games["team_b2b_away"].fillna(0).astype(int)
        
        # Star absence check for either team
        games["star_absent"] = ((games["star_present_home"] == 0) | 
                                (games["star_present_away"] == 0)).astype(int)
        
        games["total_fga"]   = games["team_fga_home"] + games["team_fga_away"]

        print(f"  {len(games)} synthetic game-lines built.")
        return games


# ══════════════════════════════════════════════════════════════
# 5.  MARKET EFFICIENCY TESTS
# ══════════════════════════════════════════════════════════════

class MarketEfficiencyTests:
    def __init__(self, df: pd.DataFrame):
        # Clean the dataframe to ensure all required metrics exist for the tests
        required = ["p_over_fair", "over_hit", "residual"]
        self.df = df.dropna(subset=[c for c in required if c in df.columns]).copy()

    # ── 5a. Calibration ──────────────────────────────────────

    def calibration(self) -> dict:
        """
        OLS: over_hit = α + β·p_over_fair + ε
        Prevails over the 'unpacking' error by checking for constant data first.
        """
        if self.df.empty:
            print("  [warning] No data available for calibration.")
            return {}

        # If using synthetic lines, p_over_fair is likely constant 0.50
        if self.df["p_over_fair"].nunique() <= 1:
            print("\n── Calibration [CONSTANT LINE DETECTED] ────────────────")
            mean_hit = self.df["over_hit"].mean()
            # In a constant model, alpha is the mean hit rate and beta is undefined
            print(f"  All lines are {self.df['p_over_fair'].iloc[0]}.")
            print(f"  Mean Hit Rate (Alpha Proxy): {mean_hit:.4f}")
            return dict(alpha=mean_hit, beta=np.nan, n=len(self.df))

        try:
            X = sm.add_constant(self.df["p_over_fair"])
            ols = sm.OLS(self.df["over_hit"], X).fit(cov_type="HC3")
            
            # Robust unpacking check
            if len(ols.params) < 2:
                a, b = ols.params[0], np.nan
            else:
                a, b = ols.params[0], ols.params[1]
                
            pa = ols.pvalues[0]
            pb = ols.pvalues[1] if len(ols.pvalues) > 1 else np.nan
            
            t_b1 = (b - 1) / ols.bse.iloc[1] if not np.isnan(b) else np.nan
            p_b1 = 2 * stats.t.sf(abs(t_b1), df=ols.df_resid) if not np.isnan(t_b1) else np.nan

            brier = np.mean((self.df["over_hit"] - self.df["p_over_fair"])**2)
            brier_naive = np.mean((self.df["over_hit"] - 0.5)**2)

            print("\n── Calibration ─────────────────────────────────────────")
            print(f"  α = {a:.4f} (p={pa:.4f})  β = {b:.4f} (p={pb:.4f})")
            print(f"  Brier score = {brier:.4f}  |  Skill = {1 - brier/max(brier_naive, 1e-6):.4f}")

            return dict(alpha=a, beta=b, p_alpha=pa, p_beta=pb,
                        t_beta1=t_b1, p_beta1=p_b1,
                        brier=brier, n=len(self.df))
        except Exception as e:
            print(f"  [error] OLS Calibration failed: {e}")
            return {}

    # ── 5b. Aggregate VRP ─────────────────────────────────────

    def aggregate_vrp(self) -> dict:
        """Calculates the Volatility Risk Premium across all games."""
        if self.df.empty: return {}
        
        r = self.df["residual"]
        vrp = -r.mean()
        t, p = stats.ttest_1samp(r, 0)

        print("\n── Prop Volatility Risk Premium (VRP) ──────────────────")
        print(f"  VRP = {vrp:+.4f}  ({vrp*100:+.2f} pp overpricing per bet)")
        print(f"  t = {t:.3f}  |  p = {p:.4f}  (H0: VRP=0)")
        return dict(vrp=vrp, t=t, p=p, n=len(r))

    # ── 5c. Favorite-Longshot Bias ───────────────────────────

    def flb(self, n_bins: int = 10) -> pd.DataFrame:
        """Bins bets by implied probability to find bias in extremes."""
        if self.df.empty or self.df["p_over_fair"].nunique() <= 1:
            print("\n── FLB skipped: Insufficient variance in implied probabilities.")
            return pd.DataFrame()

        df = self.df.copy()
        df["bin"] = pd.qcut(df["p_over_fair"], q=n_bins, labels=False, duplicates="drop")
        out = (
            df.groupby("bin")
              .agg(implied=("p_over_fair","mean"), realized=("over_hit","mean"), n=("over_hit","count"))
              .reset_index()
        )
        
        out["edge"] = out["realized"] - out["implied"]
        # Use simple mean-based t-test for each bin
        out["t_stat"] = out.apply(
            lambda r: stats.ttest_1samp(df[df["bin"] == r["bin"]]["residual"], 0)[0], axis=1
        )
        
        print("\n── Favorite-Longshot Bias ──────────────────────────────")
        print(out.to_string(index=False))
        return out

    # ── 5d. VRP by subset ─────────────────────────────────────

    def vrp_slices(self) -> pd.DataFrame:
        """Slices VRP by situational flags (B2B, Stars)."""
        slices = []
        df = self.df.copy()

        # Safe column mapping
        groups = {
            "Home B2B": df.get("home_b2b", pd.Series(0, index=df.index)) == 1,
            "Away B2B": df.get("away_b2b", pd.Series(0, index=df.index)) == 1,
            "Star Absent": df.get("star_absent", pd.Series(0, index=df.index)) == 1,
        }

        for label, mask in groups.items():
            if mask.sum() < 10: continue
            sub = df[mask]["residual"]
            t, p = stats.ttest_1samp(sub, 0)
            slices.append(dict(
                group=label, n=len(sub), vrp=-sub.mean(), t=t, p=p,
                sig="***" if p<.01 else "**" if p<.05 else "*" if p<.1 else "",
            ))

        out = pd.DataFrame(slices)
        if not out.empty:
            print("\n── VRP by Subgroup ─────────────────────────────────────")
            print(out.to_string(index=False))
        return out


# ══════════════════════════════════════════════════════════════
# 6.  PUBLIC SIGNAL REGRESSION
#     H0: No public signal predicts the residual
#     Rejection = market leaves money on the table
# ══════════════════════════════════════════════════════════════

class PublicSignalRegression:

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def run(self):
        """
        OLS: residual = f(b2b flags, star absent, total_fga, season FE)
        """
        df = self.df.dropna(subset=["residual"]).copy()

        # Ensure columns exist with safe defaults
        for c, default in [("home_b2b", 0), ("away_b2b", 0), ("star_absent", 0),
                            ("total_fga", df.get("total_fga", pd.Series([80]*len(df))).mean())]:
            if c not in df.columns:
                df[c] = default

        df["both_b2b"] = ((df["home_b2b"] == 1) & (df["away_b2b"] == 1)).astype(int)
        df["one_b2b"]  = ((df["home_b2b"] == 1) ^ (df["away_b2b"] == 1)).astype(int)
        
        # Standardize FGA to Z-score
        fga_std = df["total_fga"].std()
        df["fga_z"] = (df["total_fga"] - df["total_fga"].mean()) / (fga_std if fga_std > 0 else 1)

        season_col = "C(season)" if "season" in df.columns and df["season"].nunique() > 1 else "1"

        formula = f"residual ~ both_b2b + one_b2b + star_absent + fga_z + {season_col}"
        ols = smf.ols(formula, data=df).fit(cov_type="HC3")

        print("\n── Public Signal Regression ────────────────────────────")
        print(f"  N = {int(ols.nobs):,}  |  R² = {ols.rsquared:.4f}")
        key = ["both_b2b", "one_b2b", "star_absent", "fga_z"]
        print(f"\n  {'Variable':<18} {'β':>8}  {'SE':>8}  {'p':>8}")
        for v in key:
            if v in ols.params.index:
                b, se, p = ols.params[v], ols.bse[v], ols.pvalues[v]
                sig = "***" if p<.01 else "**" if p<.05 else "*" if p<.1 else ""
                print(f"  {v:<18} {b:>+8.4f}  {se:>8.4f}  {p:>8.4f} {sig}")

        return ols

    def logit_robustness(self):
        """
        Logit version: over_hit = f(public signals).
        Safeguarded against Singular Matrix errors from constant logit_impl.
        """
        df = self.df.dropna(subset=["over_hit"]).copy()
        
        # Setup signals
        for c, default in [("home_b2b", 0), ("away_b2b", 0), ("star_absent", 0)]:
            if c not in df.columns:
                df[c] = default

        df["both_b2b"] = ((df["home_b2b"] == 1) & (df["away_b2b"] == 1)).astype(int)
        df["one_b2b"]  = ((df["home_b2b"] == 1) ^ (df["away_b2b"] == 1)).astype(int)

        # Build dynamic formula - drop constants to avoid Singular Matrix error
        base_features = ["both_b2b", "one_b2b", "star_absent"]
        active_features = []
        
        for feat in base_features:
            if df[feat].nunique() > 1:
                active_features.append(feat)
        
        # Only add logit_impl if it actually varies (it won't for synthetic lines)
        if "logit_impl" in df.columns and df["logit_impl"].nunique() > 1:
            active_features.append("logit_impl")

        if not active_features:
            print("\n── Logit Robustness Check: Skipped (No variable features) ──")
            return None

        formula = f"over_hit ~ {' + '.join(active_features)}"
        
        try:
            # fit(disp=0) silences the iteration output
            logit_model = smf.logit(formula, data=df).fit(disp=0)
            print("\n── Logit Robustness Check ──────────────────────────────")
            print(f"  Pseudo R² = {logit_model.prsquared:.4f}")
            print(f"  N = {int(logit_model.nobs):,}")
            return logit_model
        except np.linalg.LinAlgError:
            print("\n── Logit Robustness Check: Failed (Singular Matrix) ──")
            print("   Hint: This usually means one variable perfectly predicts the outcome.")
            return None
        except Exception as e:
            print(f"\n── Logit Robustness Check: Failed ({type(e).__name__}) ──")
            return None


# ══════════════════════════════════════════════════════════════
# 7.  BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════

class BacktestEngine:
    """
    Simulates betting the UNDER on games where public signals predict
    systematic over-pricing of the total.

    Strategy: bet under when:
      - At least one team is on a back-to-back, AND
      - The total line is in the upper quartile for that season
        (i.e., market expects a high-scoring game on a tired night)

    Reports gross ROI (pre-vig) and net ROI (after standard -110 vig).
    """

    def __init__(self, df: pd.DataFrame, stake: float = 1.0):
        self.df    = df.sort_values("game_date").copy()
        self.stake = stake

    def run(self) -> pd.DataFrame:
        df = self.df.copy()

        # Construct signal: b2b + line above seasonal median
        df["b2b_any"] = (
            df.get("home_b2b", pd.Series(0, index=df.index)).fillna(0).astype(int) |
            df.get("away_b2b", pd.Series(0, index=df.index)).fillna(0).astype(int)
        )
        median_line = df.groupby("season")["total_line"].transform("median")
        df["line_above_median"] = (df["total_line"] > median_line).astype(int)
        df["signal"]            = df["b2b_any"] & df["line_above_median"]

        bets = df[df["signal"] == 1].copy()
        bets["won"]       = (bets["over_hit"] == 0).astype(int)   # bet under → win if over didn't hit
        bets["gross_pnl"] = np.where(bets["won"], self.stake, -self.stake)
        # Net: winning leg pays stake * (100/110) after standard -110 juice
        bets["net_pnl"]   = np.where(bets["won"],
                                     self.stake * (100/110),
                                     -self.stake)

        bets["cum_gross"] = bets["gross_pnl"].cumsum()
        bets["cum_net"]   = bets["net_pnl"].cumsum()

        n        = len(bets)
        win_rate = bets["won"].mean()
        gross_roi = bets["gross_pnl"].sum() / (n * self.stake)
        net_roi   = bets["net_pnl"].sum()   / (n * self.stake)
        sharpe    = (bets["net_pnl"].mean() / bets["net_pnl"].std()) * np.sqrt(n) if n > 1 else 0

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
    """
    Generates the final analysis dashboard and summary CSV.
    Safeguarded against crashes caused by constant synthetic lines or empty subsets.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df
        # Set a clean style for the plots
        sns.set_theme(style="whitegrid")

    def plot_all(self, bets: pd.DataFrame, flb: pd.DataFrame):
        """Creates a 5-panel dashboard of market efficiency metrics."""
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(2, 3, hspace=0.40, wspace=0.35)

        # ── Panel 1: Calibration curve ────────────────────────
        ax1 = fig.add_subplot(gs[0, 0])
        # Only plot if we have variance in p_over_fair
        df_cal = self.df.dropna(subset=["p_over_fair", "over_hit"]).copy()
        
        if not df_cal.empty and df_cal["p_over_fair"].nunique() > 1:
            df_cal["bin"] = pd.qcut(df_cal["p_over_fair"], q=8, labels=False, duplicates="drop")
            cal_data = df_cal.groupby("bin").agg(impl=("p_over_fair","mean"), real=("over_hit","mean")).reset_index()
            ax1.plot([0.4, 0.6], [0.4, 0.6], "k--", lw=1.5, label="Perfect")
            ax1.scatter(cal_data["impl"], cal_data["real"], s=70, c="steelblue", zorder=5)
            ax1.set_xlabel("Implied Prob")
            ax1.set_ylabel("Realized Rate")
        else:
            ax1.text(0.5, 0.5, "Calibration N/A\n(Constant Lines)", ha="center", va="center", transform=ax1.transAxes)
            
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

        # ── Panel 3: VRP by b2b ───────────────────────────────
        ax3 = fig.add_subplot(gs[0, 2])
        b2b_labels, vrps, errs = [], [], []
        # Check for both original and suffixed column names
        for label, mask_col, val in [("Both B2B", "both_b2b", 1),
                                     ("One B2B",  "one_b2b",  1),
                                     ("No B2B",   "home_b2b", 0)]:
            
            # Robust column checking for merged dataframes
            col = mask_col if mask_col in self.df.columns else f"team_b2b_{mask_col.split('_')[0]}"
            
            if col in self.df.columns:
                sub = self.df[self.df[col] == val]["residual"].dropna()
                if len(sub) >= 5:
                    b2b_labels.append(label)
                    vrps.append(-sub.mean())
                    errs.append(sub.sem())

        if b2b_labels:
            colors = ["#d62728" if v > 0 else "#1f77b4" for v in vrps]
            ax3.bar(b2b_labels, vrps, yerr=errs, color=colors, capsize=5, edgecolor="black", linewidth=0.7)
            ax3.axhline(0, color="black", lw=0.8)
        else:
            ax3.text(0.5, 0.5, "Insufficient Data", ha="center", va="center", transform=ax3.transAxes)
        
        ax3.set_title("VRP by B2B Schedule", fontweight="bold")
        ax3.set_ylabel("VRP (implied − realized)")

        # ── Panel 4: Favorite-Longshot Bias (FLB) ─────────────
        ax4 = fig.add_subplot(gs[1, 0])
        # FIX: Check if flb dataframe has the expected 'implied' column
        if flb is not None and not flb.empty and "implied" in flb.columns:
            ax4.plot([0.35, 0.65], [0.35, 0.65], "k--", lw=1.5)
            sc = ax4.scatter(flb["implied"], flb["realized"],
                             c=flb["edge"], cmap="RdYlGn", s=80, edgecolors="k", lw=0.5)
            plt.colorbar(sc, ax=ax4, label="Edge")
            ax4.set_xlabel("Implied Prob")
            ax4.set_ylabel("Realized Rate")
        else:
            ax4.text(0.5, 0.5, "FLB Skipped\n(No variance in lines)", ha="center", va="center", transform=ax4.transAxes)
            
        ax4.set_title("Favorite-Longshot Bias", fontweight="bold")

        # ── Panel 5: Cumulative P&L ────────────────────────────
        ax5 = fig.add_subplot(gs[1, 1:])
        if bets is not None and not bets.empty and "cum_net" in bets.columns:
            ax5.plot(bets["game_date"], bets["cum_gross"], label="Gross (pre-vig)", lw=1.5, color="steelblue")
            ax5.plot(bets["game_date"], bets["cum_net"], label="Net (post-vig)", lw=1.5, linestyle="--", color="darkorange")
            ax5.axhline(0, color="black", lw=0.8)
            ax5.legend()
        else:
            ax5.text(0.5, 0.5, "No strategy signals generated", ha="center", va="center", transform=ax5.transAxes)
            
        ax5.set_title("Cumulative P&L Strategy Performance", fontweight="bold")
        ax5.set_xlabel("Date"); ax5.set_ylabel("Units")

        fig.suptitle("NBA Game Total Market Efficiency Analysis", fontsize=14, fontweight="bold", y=1.01)
        
        # Ensure the output directory exists
        output_path = Path("output/nba_efficiency_dashboard.png")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"\n[saved] {output_path}")

    def export_summary(self, cal: dict, vrp: dict, reg_ols) -> pd.DataFrame:
        """Exports key metrics to CSV, handling missing dictionary keys gracefully."""
        
        # Safe formatting helper
        fmt = lambda d, key, default: f"{d.get(key, default):+.4f}" if isinstance(d.get(key), (int, float)) else str(d.get(key, default))

        rows = [
            ("Calibration Alpha (Bias)", fmt(cal, 'alpha', 0.0), f"p={cal.get('p_alpha', 1.0):.3f}"),
            ("Calibration Beta (Slope)", fmt(cal, 'beta', 1.0), f"p(B=1)={cal.get('p_beta1', 1.0):.3f}"),
            ("Aggregate VRP",            fmt(vrp, 'vrp', 0.0),   f"p={vrp.get('p', 1.0):.3f}"),
            ("N Observations",           f"{vrp.get('n', 0):,}", ""),
            ("OLS R-Squared",            f"{reg_ols.rsquared:.4f}" if reg_ols else "N/A", "")
        ]
        
        df_summary = pd.DataFrame(rows, columns=["Metric", "Estimate", "Inference"])
        
        summary_path = Path("output/summary_metrics.csv")
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

    # ── Step 1: Load NBA data (auto-downloads) ────────────────
    print("\n[1/6] Loading NBA game logs via nba_api...")
    loader      = NBADataLoader()
    player_logs = loader.load_player_logs(SEASONS)
    team_logs   = loader.load_team_logs(SEASONS)

    # ── Step 2: Feature engineering ──────────────────────────
    print("\n[2/6] Processing features...")
    proc      = DataProcessor()
    players_e = proc.process_player_logs(player_logs)
    team_agg  = proc.build_team_game_df(players_e)

    # ── Step 3: Load or synthesize game lines ─────────────────
    print("\n[3/6] Loading game lines...")
    sbr_raw = SBRLoader().load_all(SEASONS)

    if sbr_raw.empty:
        print("  → No SBR files found — using synthetic lines.")
        print("  → To use real lines: download from sportsbookreviewsonline.com")
        print(f"    Save as: {SBR_DIR}/nba_2021-22.xlsx  (etc.)")
        game_df = SyntheticLineBuilder().build(team_agg)
    else:
        sbr_with_prob = proc.add_implied_prob(sbr_raw)
        game_df       = proc.merge_lines_and_teams(sbr_with_prob, team_agg)
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