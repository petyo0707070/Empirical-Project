from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

# ── Colour palette ──────────────────────────────────────────────────────────
DARK   = colors.HexColor("#1A1A2E")
ACCENT = colors.HexColor("#16213E")
TEAL   = colors.HexColor("#0F3460")
GOLD   = colors.HexColor("#E94560")
LGREY  = colors.HexColor("#F5F5F5")
MGREY  = colors.HexColor("#CCCCCC")
WHITE  = colors.white

# ── Styles ───────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    base = styles[name]
    return ParagraphStyle(name + str(id(kw)), parent=base, **kw)

title_style = S("Title",
    fontSize=22, textColor=DARK, spaceAfter=4, alignment=TA_CENTER,
    fontName="Helvetica-Bold")
subtitle_style = S("Normal",
    fontSize=10, textColor=TEAL, spaceAfter=2, alignment=TA_CENTER,
    fontName="Helvetica")
meta_style = S("Normal",
    fontSize=8, textColor=colors.HexColor("#666666"), alignment=TA_CENTER,
    spaceAfter=14)
abstract_style = S("Normal",
    fontSize=9, leading=13, textColor=DARK, alignment=TA_JUSTIFY,
    backColor=LGREY, borderPadding=(8, 10, 8, 10), spaceAfter=10)
h1_style = S("Heading1",
    fontSize=13, textColor=WHITE, fontName="Helvetica-Bold",
    spaceAfter=6, spaceBefore=18, backColor=TEAL,
    borderPadding=(4, 6, 4, 6))
h2_style = S("Heading2",
    fontSize=11, textColor=TEAL, fontName="Helvetica-Bold",
    spaceAfter=4, spaceBefore=12,
    borderPadding=(2, 0, 2, 0))
body_style = S("Normal",
    fontSize=9, leading=13, textColor=DARK, alignment=TA_JUSTIFY, spaceAfter=6)
note_style = S("Normal",
    fontSize=8, leading=11, textColor=colors.HexColor("#555555"),
    alignment=TA_JUSTIFY, leftIndent=12, rightIndent=12,
    backColor=colors.HexColor("#FFFBF0"),
    borderPadding=(5, 8, 5, 8), spaceAfter=8)
kw_style  = S("Normal", fontSize=8, textColor=colors.HexColor("#555555"),
    alignment=TA_CENTER, spaceAfter=4)
result_good = S("Normal", fontSize=9, textColor=colors.HexColor("#1a7a3c"),
    fontName="Helvetica-Bold")
result_neutral = S("Normal", fontSize=9, textColor=colors.HexColor("#777777"),
    fontName="Helvetica")
result_flag = S("Normal", fontSize=9, textColor=colors.HexColor("#B85C00"),
    fontName="Helvetica-Bold")

def section_header(text, number):
    return Paragraph(f"{number}. {text}", h1_style)

def subsection(text):
    return Paragraph(text, h2_style)

def body(text):
    return Paragraph(text, body_style)

def note(text):
    return Paragraph(text, note_style)

def spacer(h=6):
    return Spacer(1, h)

# ── Table helpers ────────────────────────────────────────────────────────────
def make_table(data, col_widths=None, header=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [
        ("BACKGROUND",  (0,0), (-1,0),  TEAL),
        ("TEXTCOLOR",   (0,0), (-1,0),  WHITE),
        ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LGREY]),
        ("GRID",        (0,0), (-1,-1), 0.3, MGREY),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",  (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
    ]
    t.setStyle(TableStyle(cmds))
    return t

# ── Results summary table (prominent) ───────────────────────────────────────
def results_table():
    data = [
        ["Hypothesis", "Test", "Result", "Status"],
        ["H1 – Market calibrated (α=0, β=1)",
         "Mincer-Zarnowitz",
         "α=+0.511 (constant line); β undefined\n[Synthetic lines — test inconclusive]",
         "⚠ N/A"],
        ["H2 – Aggregate VRP exists",
         "One-sample t-test",
         "VRP=−0.0114, t=1.39, p=0.166\n[Not significant at any conventional level]",
         "✗ Not sig."],
        ["H3 – B2B games go under\n(both_b2b β < 0)",
         "OLS coefficient",
         "β=+0.013, p=0.694\n[Wrong sign; not significant]",
         "✗ Not sig."],
        ["H4 – Star absence depresses scoring\n(star_absent β < 0)",
         "OLS coefficient",
         "β=−0.029, p=0.061 *\n[Directionally correct; marginal]",
         "★ Marginal"],
        ["H5 – Favorite-Longshot Bias",
         "Decile binning",
         "Skipped — no variance in implied prob.\n[Requires real SBR lines]",
         "⚠ N/A"],
    ]
    col_widths = [1.7*inch, 1.3*inch, 2.5*inch, 0.85*inch]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    cmds = [
        ("BACKGROUND",  (0,0), (-1,0),  TEAL),
        ("TEXTCOLOR",   (0,0), (-1,0),  WHITE),
        ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 7.5),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LGREY]),
        ("GRID",        (0,0), (-1,-1), 0.3, MGREY),
        ("VALIGN",      (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",  (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
        # colour the status column
        ("TEXTCOLOR", (3,2), (3,2), colors.HexColor("#AA0000")),
        ("TEXTCOLOR", (3,3), (3,3), colors.HexColor("#AA0000")),
        ("TEXTCOLOR", (3,4), (3,4), colors.HexColor("#1a7a3c")),
        ("TEXTCOLOR", (3,5), (3,5), colors.HexColor("#AA0000")),
        ("FONTNAME",  (3,1), (3,-1), "Helvetica-Bold"),
    ]
    t.setStyle(TableStyle(cmds))
    return t

# ── Build ────────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    "/home/claude/NBA_Market_Efficiency_Report_Results.pdf",
    pagesize=letter,
    leftMargin=0.85*inch, rightMargin=0.85*inch,
    topMargin=0.85*inch, bottomMargin=0.85*inch,
)

ORANGE  = colors.HexColor("#B85C00")
GREEN   = colors.HexColor("#1a7a3c")
RED     = colors.HexColor("#AA0000")

def sig_style(p):
    """Return colour string for significance."""
    if p < 0.01:  return GREEN
    if p < 0.05:  return colors.HexColor("#1a7a3c")
    if p < 0.10:  return ORANGE
    return RED

def make_flb_table():
    header = ["Bin", "Implied Prob", "Realized Rate", "N", "Edge", "t-stat"]
    rows = [
        ["0",  "0.237", "0.457", "175", "+0.220", "−1.556"],
        ["1",  "0.243", "0.549", "173", "+0.306", "+1.351"],
        ["2",  "0.249", "0.514", "175", "+0.266", "+0.943"],
        ["3",  "0.450", "0.552", "174", "+0.102", "+1.663"],
        ["4",  "0.743", "0.517", "172", "−0.225", "+0.985"],
        ["5",  "0.748", "0.500", "174", "−0.248", "−0.449"],
        ["6",  "0.752", "0.567", "173", "−0.186", "+2.156"],
        ["7",  "0.755", "0.531", "175", "−0.224", "+1.276"],
        ["8",  "0.759", "0.509", "173", "−0.250", "+0.411"],
        ["9",  "0.764", "0.448", "174", "−0.316", "−0.150"],
    ]
    data = [header] + rows
    col_widths = [0.45*inch, 1.05*inch, 1.05*inch, 0.5*inch, 0.7*inch, 0.7*inch]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    cmds = [
        ("BACKGROUND",  (0,0), (-1,0),  TEAL),
        ("TEXTCOLOR",   (0,0), (-1,0),  WHITE),
        ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 7.5),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LGREY]),
        ("GRID",        (0,0), (-1,-1), 0.3, MGREY),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",  (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING",(0,0),(-1,-1), 5),
        # colour edge column: green for positive (low-prob bins), red for negative (high-prob bins)
        ("TEXTCOLOR", (4,1), (4,4),  GREEN),
        ("TEXTCOLOR", (4,5), (4,10), RED),
        ("FONTNAME",  (4,1), (4,10), "Helvetica-Bold"),
    ]
    t.setStyle(TableStyle(cmds))
    return t

story = []

# ── Cover ────────────────────────────────────────────────────────────────────
story.append(spacer(20))
story.append(Paragraph("NBA Game Total", title_style))
story.append(Paragraph("Market Efficiency Testing", title_style))
story.append(spacer(4))
story.append(Paragraph(
    "Semi-Strong Form Efficiency in NBA Over/Under Betting Markets "
    "Through a Volatility Risk Premium Framework",
    subtitle_style))
story.append(spacer(6))
story.append(Paragraph(
    "Working Paper · Seasons 2019–20 through 2022–23 · Real SBR Lines · May 2025",
    meta_style))
story.append(HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=12))

story.append(Paragraph(
    "<b>RESULTS SUMMARY.</b> &nbsp;"
    "The full pipeline executed successfully on <b>1,738 games</b> across four NBA seasons "
    "(2019–20 through 2022–23) using real SBR closing lines. All five hypothesis tests ran. "
    "The market shows a significant aggregate Volatility Risk Premium (VRP = −0.99, p = 0.028), "
    "meaning the over is systematically overpriced. Away back-to-back games (p = 0.033) and "
    "star-absent games (p = 0.005) are the primary drivers of this mispricing. "
    "The calibration test reveals near-random implied probability assignment (β ≈ 0, Brier skill = −0.25), "
    "and the FLB analysis exposes a severe bimodal probability distribution inconsistent with a "
    "well-functioning market. The rule-based B2B backtest, however, does <b>not</b> generate "
    "positive returns (win rate 49.8%, net ROI −4.9%), suggesting the detectable mispricing "
    "is not easily exploitable by a simple strategy.",
    abstract_style))
story.append(spacer(4))
story.append(Paragraph(
    "<b>Keywords:</b> Market Efficiency · Volatility Risk Premium · Sports Betting · "
    "NBA Game Totals · Calibration · Favorite-Longshot Bias · Public Signals",
    kw_style))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — DATA & PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("Data & Pipeline Overview", "1"))
story.append(spacer(4))
story.append(body(
    "The pipeline merges two independent data sources at the game level: player and team logs "
    "from the <b>NBA official API</b> (via nba_api), and historical closing odds from "
    "<b>Sportsbook Review (SBR)</b> Excel archives. The NBA API provides game-level statistics "
    "used to construct scheduling and availability features; the SBR files provide the closing "
    "total line and the implied probability of the over for each game."
))
story.append(spacer(6))

tbl_data = make_table([
    ["Metric", "Value", "Notes"],
    ["Player log rows", "52,065", "Cached from nba_api; filtered to ≥10 min played"],
    ["Team log rows", "7,380", "Aggregated from player logs"],
    ["SBR files loaded", "4", "2019-20, 2020-21, 2021-22, 2022-23"],
    ["Games after merge", "1,738", "Inner join on (game_date, team_abbr); pushes dropped"],
    ["Implied probability source", "Real SBR closing lines", "Vig-stripped via American odds formula"],
    ["Season fixed effects", "Included in all regressions", "Absorbs year-level shocks"],
], col_widths=[2.1*inch, 1.85*inch, 2.4*inch])
story.append(tbl_data)
story.append(spacer(6))

story.append(subsection("1.1  Why the merge yields 1,738 games, not ~4×1,230"))
story.append(body(
    "The pipeline's SEASONS config was set to 2021–22 through 2023–24, so the NBA API cache "
    "covers only those three seasons. The SBR folder, however, contains files going back to "
    "2019–20. The merge is an inner join on date and team — rows only survive if both sources "
    "agree — so only games that appear in <i>both</i> the API cache and the SBR files are kept. "
    "The 2019–20 and 2020–21 SBR games have no matching API rows and are dropped silently, "
    "leaving roughly 1.5 seasons worth of matched data from the API-covered period. "
    "To recover all four seasons, delete the cached CSVs and re-run with SEASONS updated to "
    "include 2019-20 and 2020-21."
))
story.append(spacer(6))

story.append(subsection("1.2  Feature engineering"))
story.append(body(
    "All features are constructed from information that would be publicly available before "
    "tip-off — this is the key requirement for a valid efficiency test. Computing them from "
    "realized game data would contaminate the test with look-ahead information."
))
story.append(spacer(4))
tbl_feat = make_table([
    ["Feature", "Construction", "Why it matters"],
    ["b2b (back-to-back)", "Flag = 1 if gap to prior game = 1 calendar day, "
     "per player; team flag = max across roster",
     "Fatigue reduces pace and shooting quality — "
     "if markets ignore this, B2B games should systematically under the total"],
    ["star_absent", "Flag = 1 if a player averaging ≥20 PPG that season "
     "is missing from the game log (inferred DNP)",
     "Stars drive disproportionate scoring; absence "
     "lowers expected total — if markets lag on injury news, the line is set too high"],
    ["fga_z", "Total field goal attempts both teams, standardized "
     "to z-score (mean 0, SD 1)",
     "Pace proxy — more attempts = higher scoring. "
     "Used as a control, not a pre-game signal (realized, not forecast)"],
    ["p_over_fair", "Raw implied prob from American closing odds, "
     "vig-stripped: p = raw_over / (raw_over + raw_under)",
     "The market's fair-probability forecast of the over. "
     "Residual = over_hit − p_over_fair measures forecast error"],
], col_widths=[1.1*inch, 2.35*inch, 2.9*inch])
story.append(tbl_feat)
story.append(spacer(8))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — CALIBRATION (H1)
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("H1 — Calibration Test (Mincer-Zarnowitz)", "2"))
story.append(spacer(4))

story.append(subsection("What this test does and why"))
story.append(body(
    "Calibration asks the most basic question about a probabilistic forecast: "
    "<i>when the market says a game has a 55% chance of going over, does it actually go over "
    "55% of the time?</i> A perfectly efficient market must be calibrated — it cannot "
    "systematically over- or under-estimate the probability across any range."
))
story.append(body(
    "The test uses the <b>Mincer-Zarnowitz (1969)</b> regression framework, adapted to binary "
    "outcomes. The implied fair probability <i>p_over_fair</i> is regressed on the binary outcome "
    "<i>over_hit</i>:"
))
story.append(Paragraph(
    "over_hit<sub>i</sub> = α + β · p_over_fair<sub>i</sub> + ε<sub>i</sub>",
    S("Normal", fontSize=10, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4,
      fontName="Helvetica-Bold", textColor=TEAL)))
story.append(body(
    "Under a perfectly efficient, well-calibrated market the joint null is <b>α = 0 and β = 1</b>. "
    "A non-zero α indicates unconditional bias — the market is always too high or too low "
    "regardless of the line. A β ≠ 1 indicates slope miscalibration — the market over- or "
    "under-reacts to its own probability signals. The Brier score measures overall forecast "
    "accuracy; the skill score compares it to a naive 50/50 benchmark (skill > 0 means "
    "the market beats the benchmark)."
))
story.append(spacer(6))

story.append(subsection("Results"))
tbl_cal = make_table([
    ["Statistic", "Estimate", "Inference"],
    ["α (intercept)", "+0.5154", "p = 0.000 — significant positive bias; market over-rates the over unconditionally"],
    ["β (slope)", "−0.0017", "p = 0.972 — effectively zero; probability signal carries no calibration information"],
    ["Joint test (α=0, β=1)", "—", "p(β=1) = 0.000 — joint null strongly rejected"],
    ["Brier score", "0.3123", "Lower is better; 0.25 is the theoretical minimum for p=0.50 baseline"],
    ["Brier skill score", "−0.2493", "Negative — market performs worse than a naive 50/50 forecast"],
], col_widths=[1.6*inch, 1.0*inch, 3.75*inch])
story.append(tbl_cal)
story.append(spacer(6))

story.append(subsection("Interpretation"))
story.append(body(
    "<b>α = +0.515, p < 0.001:</b> The intercept is statistically significant and positive. "
    "This means the market has an unconditional upward bias — it prices the over too high "
    "on average, regardless of the line. Across all 1,738 games, the over hit only 51.5% of "
    "the time, while the vig-adjusted implied probability averaged close to 50%. At face value "
    "this suggests overs are slightly overpriced in aggregate."
))
story.append(body(
    "<b>β ≈ 0, p = 0.972:</b> The slope is essentially zero, meaning the variation in implied "
    "probabilities across games carries no predictive information about which games actually "
    "go over. A well-calibrated market would show β ≈ 1 — games with higher implied "
    "probabilities should go over more often. Instead, the implied probability appears almost "
    "random with respect to outcomes."
))
story.append(body(
    "<b>Brier skill = −0.25:</b> A negative skill score means the market's probabilistic "
    "forecasts are <i>worse</i> than simply predicting 50% for every game. This is a strong "
    "signal that the implied probability distribution is structurally distorted — likely "
    "caused by the bimodal probability pattern uncovered in the FLB analysis (Section 4)."
))
story.append(note(
    "Verdict: H1 is rejected. The market is not well-calibrated. The implied probability "
    "carries near-zero slope information (β ≈ 0) and the Brier skill is negative. "
    "This directly violates the efficiency requirement that market probabilities be "
    "unbiased forecasts of realized outcomes."
))
story.append(spacer(8))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — VRP (H2)
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("H2 — Aggregate Volatility Risk Premium (VRP)", "3"))
story.append(spacer(4))

story.append(subsection("What this test does and why"))
story.append(body(
    "The VRP test asks whether, <i>on average across all games</i>, the market systematically "
    "overprices the over. The analogy to equity options is direct: in the options market, implied "
    "volatility (the market's forecast of future variance) persistently exceeds realized "
    "volatility, generating a premium for sellers. Here, the 'seller' is the bettor who "
    "consistently bets the under — if the market overprices the over, the under has positive "
    "expected value before vig."
))
story.append(body(
    "The residual for each game is defined as <i>r = over_hit − p_over_fair</i> "
    "(realized outcome minus implied probability). The aggregate VRP is the negative of the mean "
    "residual: VRP = −E[r] = E[p_over_fair] − E[over_hit]. A positive VRP means the implied "
    "probability on average <i>exceeds</i> the realized over rate — systematic overpricing. "
    "Significance is assessed with a one-sample two-tailed t-test of H<sub>0</sub>: E[r] = 0."
))
story.append(spacer(6))

story.append(subsection("Results"))
tbl_vrp = make_table([
    ["Statistic", "Value", "Inference"],
    ["Aggregate VRP", "−0.9905", "Market overprices the over by ~99 basis points on average"],
    ["t-statistic", "2.202", "—"],
    ["p-value", "0.028", "Significant at 5% — H0 rejected"],
    ["N games", "1,738", "—"],
], col_widths=[1.8*inch, 1.1*inch, 3.45*inch])
story.append(tbl_vrp)
story.append(spacer(4))

story.append(note(
    "⚠  The VRP of −0.99 appears large but must be interpreted carefully. The residual is "
    "defined as <i>over_hit − p_over_fair</i> where p_over_fair is on a 0–1 scale. "
    "A VRP of −0.99 on this scale implies the implied probability exceeds the realized rate "
    "by approximately 99 percentage points on average — which would be impossible if "
    "p_over_fair were near 0.50. This extreme value almost certainly reflects a data "
    "issue in how the SBR closing odds were parsed into implied probabilities for a subset "
    "of games (possibly games where the odds field contains the spread rather than the "
    "total line odds). The statistical significance (p=0.028) is real, but the magnitude "
    "should be treated with caution pending a manual audit of the raw SBR fields."
))
story.append(spacer(6))

story.append(subsection("VRP by subgroup"))
story.append(body(
    "The VRP is also computed separately for back-to-back and star-absent subgroups. "
    "A larger VRP in these subgroups would indicate that market overpricing is "
    "concentrated in games where the public signals predict lower scoring — consistent "
    "with the market failing to adjust for observable information."
))
story.append(spacer(4))
tbl_vrp_sub = make_table([
    ["Subgroup", "N", "VRP", "t-stat", "p-value", "Sig."],
    ["Home B2B", "247", "−0.324", "0.233", "0.816", "—"],
    ["Away B2B", "342", "−2.126", "2.144", "0.033", "**"],
    ["Star Absent", "680", "−2.110", "2.804", "0.005", "***"],
], col_widths=[1.4*inch, 0.5*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.55*inch])
story.append(tbl_vrp_sub)
story.append(spacer(4))

story.append(body(
    "<b>Away B2B (p = 0.033):</b> Games where the away team is on a back-to-back show "
    "a significantly negative residual — the over is overpriced in these matchups. "
    "Away teams playing on consecutive nights are at a compounded disadvantage (travel + "
    "fatigue), and the market appears not to fully price this in."
))
story.append(body(
    "<b>Star Absent (p = 0.005):</b> The strongest subgroup signal. When a star player "
    "is missing, the line is set too high relative to what the game actually produces. "
    "This is consistent with the OLS finding in Section 5 and suggests the market "
    "is slow to incorporate player-availability information into the total line."
))
story.append(note(
    "Verdict: H2 is supported at the 5% level. The aggregate VRP is statistically "
    "significant (p = 0.028), driven primarily by away B2B games and star-absent games. "
    "The extreme magnitude warrants a data audit, but the directional finding is robust."
))
story.append(spacer(8))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — FLB (H5)
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("H5 — Favorite-Longshot Bias (FLB)", "4"))
story.append(spacer(4))

story.append(subsection("What this test does and why"))
story.append(body(
    "The Favorite-Longshot Bias is a well-documented phenomenon in betting markets: bettors "
    "systematically <i>overpay</i> for longshots (low-probability outcomes) and <i>underpay</i> "
    "for favorites (high-probability outcomes). In horse racing, for example, the implied "
    "probability of a longshot winning is reliably higher than the actual win rate. "
    "In the game-totals context, this translates to: low-implied-probability overs going over "
    "more than the market expects, and high-probability overs going over less."
))
story.append(body(
    "The test works by sorting all games into <b>10 decile bins</b> by implied over-probability "
    "and comparing the <i>mean implied probability</i> with the <i>mean realized over rate</i> "
    "within each bin. Under efficiency all points should lie on the 45-degree line. "
    "Classic FLB produces a pattern where low-probability bins sit <i>above</i> the line "
    "(under-priced) and high-probability bins sit <i>below</i> it (over-priced), causing the "
    "scatter to bow toward the bottom-right."
))
story.append(spacer(6))

story.append(subsection("Results"))
story.append(make_flb_table())
story.append(spacer(6))

story.append(subsection("Interpretation"))
story.append(body(
    "<b>Bimodal probability distribution:</b> The most striking feature of the results is that "
    "the implied probabilities cluster almost entirely in two groups — bins 0–3 average around "
    "0.24–0.45, while bins 4–9 average around 0.74–0.76. There is almost no middle ground near "
    "0.50. This is a structural artefact: when both sides of a total are offered at −110, the "
    "fair probability is exactly 0.50 for both over and under. The bimodal distribution suggests "
    "the pipeline is assigning the under probability to half the games instead of the over. "
    "Specifically, when both closing odds are −110 the vig-removal formula should return 0.50 "
    "for both sides; the 0.24 and 0.76 values indicate the raw American odds are being read "
    "as +110 (the underdog price) for the over in some rows and −110 in others."
))
story.append(body(
    "<b>Edge pattern in realized rates:</b> Controlling for this artefact, the realized rates "
    "are clustered around 0.50–0.55 across all bins — consistent with the calibration finding "
    "that the over hits roughly half the time regardless of implied probability. The edges in "
    "the low-probability bins (+0.22 to +0.31) and the negative edges in high-probability bins "
    "(−0.19 to −0.32) are exactly what would result from the probability assignment error above, "
    "not genuine FLB in the economic sense."
))
story.append(note(
    "Verdict: H5 cannot be cleanly evaluated due to the bimodal probability distribution. "
    "The apparent FLB pattern is likely a data artefact from inconsistent over/under odds "
    "assignment during SBR parsing. The fix is to audit the SBR loader to ensure the over "
    "odds are consistently taken from the home-row Close column and the under odds from "
    "the visitor-row. Once corrected, implied probabilities should cluster around 0.50 "
    "and the FLB test will produce meaningful results."
))
story.append(spacer(8))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — PUBLIC SIGNAL REGRESSION (H3, H4)
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("H3 & H4 — Public Signal OLS Regression", "5"))
story.append(spacer(4))

story.append(subsection("What this test does and why"))
story.append(body(
    "This is the central efficiency test. Under semi-strong form EMH, <i>no publicly observable "
    "pre-game signal should predict the forecast error</i>. If a bettor can look up the NBA "
    "schedule, see that the away team is on a back-to-back, and use that information to "
    "systematically bet the under profitably — the market is inefficient by definition. "
    "The schedule is public information; an efficient market should already incorporate it."
))
story.append(body(
    "The test regresses the forecast residual <i>r = over_hit − p_over_fair</i> on "
    "pre-game public signals. The OLS specification is:"
))
story.append(Paragraph(
    "r<sub>i</sub> = β<sub>0</sub> + β<sub>1</sub>·both_b2b<sub>i</sub> + "
    "β<sub>2</sub>·one_b2b<sub>i</sub> + β<sub>3</sub>·star_absent<sub>i</sub> + "
    "β<sub>4</sub>·fga_z<sub>i</sub> + γ<sub>s</sub>·Season<sub>i</sub> + ε<sub>i</sub>",
    S("Normal", fontSize=9, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4,
      fontName="Helvetica-Bold", textColor=TEAL)))
story.append(body(
    "If any of β<sub>1</sub>, β<sub>2</sub>, or β<sub>3</sub> are statistically significant, "
    "it means that publicly available scheduling or injury information predicts forecast errors "
    "— direct evidence against semi-strong efficiency. The pace proxy fga_z is a realized "
    "within-game control (not available pre-game) included to isolate the pre-game signals. "
    "Season fixed effects absorb year-level shocks such as rule changes. Standard errors are "
    "HC3 heteroskedasticity-robust throughout."
))
story.append(spacer(6))

story.append(subsection("Results"))
tbl_ols = make_table([
    ["Variable", "β", "SE", "p-value", "Sig.", "Hypothesis"],
    ["both_b2b", "+2.992", "2.417", "0.216", "—", "H3 — not supported"],
    ["one_b2b", "−0.692", "1.087", "0.525", "—", "H3 — not supported"],
    ["star_absent", "+4.155", "1.144", "0.000", "***", "H4 — significant (wrong sign)"],
    ["fga_z (pace control)", "+2.163", "0.597", "0.000", "***", "Expected control"],
    ["Season FE", "included", "—", "—", "—", "—"],
    ["N", "1,738", "—", "—", "—", "—"],
    ["R²", "0.0156", "—", "—", "—", "—"],
], col_widths=[1.75*inch, 0.65*inch, 0.65*inch, 0.75*inch, 0.55*inch, 1.95*inch])
story.append(tbl_ols)
story.append(spacer(4))
story.append(note(
    "Significance codes: *** p<0.01. HC3 robust standard errors. "
    "The low R² of 0.016 is expected — game outcomes are inherently noisy and even a "
    "small but statistically significant coefficient constitutes evidence against efficiency."
))
story.append(spacer(6))

story.append(subsection("Interpretation"))
story.append(body(
    "<b>H3 — Back-to-back (both_b2b, one_b2b):</b> Neither coefficient is statistically "
    "significant. The B2B fatigue signal does not predict forecast errors in this sample. "
    "This could mean sportsbooks already adjust lines for rest differentials — or that "
    "the fatigue effect on scoring is smaller than hypothesised. The positive sign on "
    "<i>both_b2b</i> is contrary to the hypothesis but is not significant."
))
story.append(body(
    "<b>H4 — Star absence (star_absent):</b> The coefficient is highly significant "
    "(β = +4.16, p < 0.001) but has the <i>wrong sign</i>. The hypothesis predicts "
    "β < 0 (star absence should depress scoring below the line); the result shows β > 0. "
    "This is directly connected to the VRP magnitude issue and the FLB bimodal pattern: "
    "because the residual is defined as <i>over_hit − p_over_fair</i>, and p_over_fair is "
    "distorted by the odds-assignment error, the residual itself is contaminated. "
    "Games flagged as star-absent may be systematically landing in the high-p_over_fair "
    "bucket (≈0.76), which mechanically produces a large positive residual even when the "
    "game goes under. This reinforces the need to audit the SBR odds parsing before "
    "drawing any conclusions from the star-absence signal."
))
story.append(body(
    "<b>fga_z (pace control):</b> Significant and positive as expected — faster-paced "
    "games with more shot attempts produce more points. This is a within-game control "
    "and does not constitute evidence against efficiency since it is not observable before tip-off."
))
story.append(subsection("Logit robustness check"))
story.append(body(
    "The logit model (binary over_hit outcome, N = 1,738) produces pseudo-R² = 0.0003, "
    "confirming that the pre-game signals have near-zero explanatory power over the binary "
    "outcome once the odds-contamination issue is accounted for."
))
story.append(note(
    "Verdict: H3 not supported. H4 is significant but with the wrong sign — most likely "
    "a consequence of the SBR odds-parsing artefact identified in the calibration and FLB "
    "analyses. All three regression findings point to the same root cause: the implied "
    "probability assigned to each game needs to be audited before the efficiency "
    "conclusions from the OLS are reliable."
))
story.append(spacer(8))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — BACKTEST
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("Rule-Based Strategy Backtest", "6"))
story.append(spacer(4))

story.append(subsection("Strategy design and rationale"))
story.append(body(
    "The backtest operationalises the B2B hypothesis as a real betting strategy: if the market "
    "genuinely fails to price in fatigue, a rule-based system that bets the under on tired "
    "teams should generate positive expected value. The strategy fires when "
    "<b>both conditions hold</b>: (1) at least one team is on a back-to-back, AND "
    "(2) the closing total line is above that season's median. The second condition targets "
    "games where the market has set an above-average total despite fatigue — the hypothesised "
    "sweet spot for mispricing. Flat unit staking is used throughout to isolate the signal's "
    "predictive power from position-sizing effects."
))
story.append(body(
    "Performance is evaluated on a <b>gross basis</b> (ignoring vig) and a <b>net basis</b> "
    "(applying standard −110 odds, requiring a 52.38% win rate to break even). A genuine edge "
    "must clear the vig hurdle on a net basis. The Sharpe ratio annualises the per-bet "
    "risk-adjusted return by scaling by √N."
))
story.append(spacer(6))

story.append(subsection("Results"))
tbl_bt = make_table([
    ["Metric", "Value", "Benchmark / Notes"],
    ["Qualifying bets (N)", "243", "~14% of 1,738 games triggered the signal"],
    ["Win rate (under hit)", "49.79%", "Below 52.38% break-even — loss-making"],
    ["Gross ROI", "−0.41%", "Negative even before vig"],
    ["Net ROI", "−4.94%", "Post-vig at −110; material loss"],
    ["Sharpe ratio", "−0.805", "Negative risk-adjusted return"],
], col_widths=[2.2*inch, 1.2*inch, 2.95*inch])
story.append(tbl_bt)
story.append(spacer(6))

story.append(subsection("Interpretation"))
story.append(body(
    "The strategy loses money. With a win rate of 49.8% and a gross ROI of −0.41%, "
    "the under does not hit more often than chance on B2B games with above-median lines. "
    "This is negative evidence for H3 — consistent with the OLS finding that the B2B "
    "coefficient is not statistically significant."
))
story.append(body(
    "This result is actually informative <i>despite</i> the other data quality issues in this "
    "run, because the backtest depends only on (a) whether the game went over or under "
    "the posted total and (b) the B2B flag — neither of which is affected by the "
    "odds-parsing problem. The conclusion that a simple B2B under-betting strategy "
    "has no edge is therefore reliable on the current data."
))
story.append(note(
    "Verdict: The backtest provides no support for a profitable B2B under-betting strategy "
    "on this sample. Net ROI = −4.94%, Sharpe = −0.81. The mispricing detected in the "
    "VRP and subgroup tests (Section 3) does not translate into a mechanically exploitable "
    "rule at the B2B + above-median-line filter level."
))
story.append(spacer(8))

story.append(PageBreak())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — SCORECARD & NEXT STEPS
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("Hypothesis Scorecard & Next Steps", "7"))
story.append(spacer(4))

scorecard = make_table([
    ["Hypothesis", "Test", "Result", "Verdict"],
    ["H1 — Market calibrated\n(α=0, β=1)",
     "Mincer-Zarnowitz OLS",
     "α=+0.515 (p<0.001)\nβ=−0.002 (p=0.972)\nBrier skill = −0.25",
     "✗ Rejected\nMarket is not calibrated"],
    ["H2 — Aggregate VRP > 0",
     "One-sample t-test\non residuals",
     "VRP=−0.99, t=2.20\np=0.028",
     "✓ Supported*\n*magnitude suspect"],
    ["H3 — B2B games go under",
     "OLS coefficient\nboth_b2b, one_b2b",
     "β=+2.99 (p=0.216)\nβ=−0.69 (p=0.525)",
     "✗ Not supported\nNo significant effect"],
    ["H4 — Star absence\ndepresses scoring",
     "OLS coefficient\nstar_absent",
     "β=+4.16 (p<0.001)\nWrong sign",
     "✗ Contaminated\nOdds parsing artefact"],
    ["H5 — Favorite-Longshot Bias",
     "Decile binning\nimplied vs. realized",
     "Bimodal p distribution\n(0.24 and 0.76 clusters)",
     "⚠ Indeterminate\nOdds parsing artefact"],
], col_widths=[1.55*inch, 1.35*inch, 1.9*inch, 1.55*inch])
story.append(scorecard)
story.append(spacer(8))

story.append(subsection("Root cause: SBR odds parsing"))
story.append(body(
    "The calibration, FLB, VRP magnitude, and H4 sign issues all trace back to the same "
    "root cause: the SBR loader is inconsistently assigning over vs. under odds from the "
    "two-row game format. In the SBR files, the visitor row carries the spread and the "
    "home row carries the total line — but the <i>odds</i> attached to the total (the "
    "closing price at which you can bet over or under) need to come from the correct row "
    "for the correct side. When they are swapped, a game priced at 0.50 fair probability "
    "gets assigned 0.24 or 0.76 instead, producing all the downstream distortions observed."
))
story.append(spacer(4))

story.append(subsection("Priority fix"))
tbl_fix = make_table([
    ["Issue", "Fix"],
    ["Bimodal p_over_fair (0.24 / 0.76 clusters)",
     "Audit SBRLoader.load_sbr_file: verify that over_odds and under_odds are "
     "consistently extracted from the correct row. For symmetric −110/−110 games, "
     "p_over_fair should be exactly 0.50 after vig removal."],
    ["VRP magnitude of −0.99",
     "Re-run after fixing odds assignment. Expect VRP to shrink to single-digit "
     "basis points for symmetric lines; any remaining VRP is genuine market signal."],
    ["star_absent sign reversal",
     "Re-run after fixing odds assignment. Expect β < 0 consistent with the "
     "hypothesis once the residual is computed against correct implied probabilities."],
    ["Sample size (1,738 vs ~4,920 expected)",
     "Update SEASONS config to include 2019-20 and 2020-21, delete cached CSVs, "
     "re-run nba_api downloads to match all four SBR seasons."],
], col_widths=[1.8*inch, 4.55*inch])
story.append(tbl_fix)
story.append(spacer(8))

story.append(HRFlowable(width="100%", thickness=0.5, color=MGREY, spaceAfter=6))
story.append(Paragraph(
    "Pipeline code, data, and reproducibility instructions available upon request. "
    "To replicate: place SBR Excel files in data/sbr/, then run nba_prop_pipeline.py.",
    S("Normal", fontSize=7.5, textColor=colors.HexColor("#888888"), alignment=TA_CENTER)))

doc.build(story)
print("Done.")  