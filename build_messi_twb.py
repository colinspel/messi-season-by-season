"""
Tableau Public workbook for "Messi, Season by Season".

    python build_messi_twb.py [--xsd path/to/twb_2026.1.0.xsd]  ->  messi_season_by_season.twbx
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from twb_lib import BLUE, GRAY, ORANGE, Workbook  # noqa: E402

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "tableau_data"
IMG = HERE / "images"
XSD = Path(sys.argv[sys.argv.index("--xsd") + 1]) if "--xsd" in sys.argv else None
SEASONS = pd.read_csv(DATA / "messi_seasons.csv").season.tolist()
SE = pd.read_csv(DATA / "messi_seasons.csv")

wb = Workbook("Messi Season by Season", DATA,
              "Data: StatsBomb Open Data, La Liga, FC Barcelona 2004/05-2020/21 (519 Messi matches). Built by Colin Spelman.")
pS = wb.param_list("Season", SEASONS, "2011/2012")

seasons = wb.source("seasons", "messi_seasons.csv", "Seasons", dims=["season_idx", "matches", "starts"])
seasons.calc("Calc_is_sel", "Is selected season", f"[season] = {pS.ref}", "boolean", "dimension", "nominal", deps=["season"], params=[pS])
seasons.palettes.append(("[none:finishing:nk]", [('"Beat xG"', BLUE), ('"Below xG"', ORANGE)]))
seasons.palettes.append(("[none:Calc_is_sel:nk]", [("true", ORANGE), ("false", BLUE)]))

heat = wb.source("heat", "messi_heat.csv", "Touch heatmap")
shots = wb.source("shots", "messi_shots.csv", "Shots", dims=["minute", "goal", "pen", "fk"])
kpl = wb.source("kpl", "messi_keypass_lines.csv", "Chances created", dims=["pass_id", "point"])
for s in (heat, shots, kpl):
    s.calc("Calc_season", "Is selected season", f"[season] = {pS.ref}", "boolean", "dimension", "nominal", deps=["season"], params=[pS])
heat.palettes.append(("[none:share:qk]", "Portfolio Sequential"))
heat.images.append(("Pitch", "Image/pitch_full.png", "x", "y_plot", 0, 120, 0, 80))
shots.palettes.append(("[none:result:nk]", [('"Goal"', BLUE), ('"No goal"', GRAY)]))
shots.images.append(("Pitch", "Image/pitch_half_vertical.png", "y", "x", 0, 80, 60, 120))
kpl.palettes.append(("[none:kind:nk]", [('"Assist"', ORANGE), ('"Chance created"', GRAY)]))
kpl.images.append(("Pitch", "Image/pitch_half_vertical.png", "py", "px", 0, 80, 60, 120))

channels = wb.source("channels", "messi_channels.csv", "Channel shares")
channels.palettes.append(("[none:channel:nk]", [('"Right channel"', ORANGE), ('"Central channel"', BLUE), ('"Left channel"', GRAY)]))
role = wb.source("role", "messi_role.csv", "Role metrics", dims=["season_idx"])
age = wb.source("age", "messi_age.csv", "Ageing curve", dims=["age"])
age.palettes.append(("[none:series:nk]", [('"Actual: non-penalty goals + assists per 90"', BLUE), ('"Expected: npxG + xA per 90"', GRAY)]))

# ---------------- season explorer ----------------
s = wb.sheet("Touch Heatmap", heat, "Square", "Where he touched the ball (Barcelona attack left to right)")
s.aggregate = False
hx, hy = s.use("x", "cont"), s.use("y_plot", "cont")
s.cols_shelf.append(hx); s.rows.append(hy)
s.encode("color", "share", "cont").encode("tooltip", "touches", "cont")
s.keep_true("Calc_season")
s.fix_axis(hx, "cols", 0, 120, show=False).fix_axis(hy, "rows", 0, 80, show=False)
s.mark_formats += [("mark-transparency", "220"), ("size", "2.6")]

s = wb.sheet("Season Shots", shots, "Circle", "Non-penalty shots (size = xG)")
s.aggregate = False
sy, sx = s.use("y", "cont"), s.use("x", "cont")
s.cols_shelf.append(sy); s.rows.append(sx)
s.encode("color", "result", "dim").encode("size", "xg", "cont")
for f in ("opponent", "date", "minute", "body"):
    s.encode("tooltip", f, "dim" if shots.field_type(f) == "string" else "cont")
s.keep_true("Calc_season")
s.fix_axis(sy, "cols", 0, 80, show=False).fix_axis(sx, "rows", 60, 120.5, show=False)

s = wb.sheet("Season Summary", seasons, "Text", "Selected season")
s.encode("text", "summary", "dim")
s.keep_true("Calc_is_sel")

s = wb.sheet("Channel Shares", channels, "Line", "Right wing or centre? Share of touches by channel")
s.col("season", "dim").row("share", "sum")
s.encode("color", "channel", "dim").encode("lod", "channel", "dim")
s.mark_formats += [("mark-markers-mode", "all")]

# ---------------- finishing ----------------
s = wb.sheet("Goals vs xG", seasons, "Bar", "Non-penalty goals by season (label: goals and npxG)")
s.col("season_short", "dim").row("np_goals", "sum")
s.encode("color", "finishing", "dim").encode("text", "goals_label", "dim").encode("tooltip", "npxg", "sum")
s.mark_formats += [("mark-labels-show", "true")]

s = wb.sheet("Goals Above xG", seasons, "Bar", "Goals above expected (non-penalty goals minus npxG)")
s.col("season_short", "dim").row("goals_minus_npxg", "sum")
s.encode("color", "finishing", "dim").encode("text", "goals_minus_npxg", "sum")
s.mark_formats += [("mark-labels-show", "true")]

# ---------------- role & age ----------------
ROLE = ["Dribbles won per 90", "Progressive passes per 90", "Key passes per 90", "Shots per 90"]
for metric in ROLE:
    s = wb.sheet(metric, role, "Line", metric)
    s.col("season", "dim").row("value", "sum")
    s.encode("tooltip", "low_minutes", "dim")
    s.keep_value("metric", metric)
    s.mark_formats += [("mark-markers-mode", "all"), ("mark-color", BLUE)]

s = wb.sheet("Ageing Curve", age, "Line", "Goal contributions per 90 by age (seasons with 900+ minutes)")
s.col("age", "ord").row("value", "sum")
s.encode("color", "series", "dim").encode("lod", "series", "dim").encode("tooltip", "season", "dim")
s.mark_formats += [("mark-markers-mode", "all")]

# ---------------- chances created ----------------
s = wb.sheet("Chances Created Map", kpl, "Line", "Passes that led to a shot (line ends where received)")
s.aggregate = False
cy, cx = s.use("py", "cont"), s.use("px", "cont")
s.cols_shelf.append(cy); s.rows.append(cx)
s.encode("lod", "pass_id", "dim").encode("path", "point", "ord").encode("color", "kind", "dim")
s.encode("tooltip", "opponent", "dim").encode("tooltip", "scorer", "dim").encode("tooltip", "xa", "cont")
s.keep_true("Calc_season")
s.fix_axis(cy, "cols", 0, 80, show=False).fix_axis(cx, "rows", 60, 120.5, show=False)

s = wb.sheet("Assists by Season", seasons, "Bar", "Assists by season (selected season highlighted)")
s.col("season_short", "dim").row("assists", "sum")
s.encode("color", "Calc_is_sel", "dim").encode("tooltip", "xa", "sum").encode("text", "assists", "sum")
s.mark_formats += [("mark-labels-show", "true")]

# ---------------- dashboards ----------------
np_tot, xg_tot = int(SE.np_goals.sum()), SE.npxg.sum()
beat = int((SE.np_goals > SE.npxg).sum())
wb.dashboard("1 Season Explorer", "Messi, Season by Season",
             "Pick a season. 519 La Liga matches for Barcelona, 2004/05 to 2020/21: where he played, where he shot, and how his role moved.",
             [pS], lambda pg: (wb.row_of(pg, 110, 520, [("Touch Heatmap", 760), ("Season Shots", 520)]),
                               wb.row_of(pg, 630, 270, [("Season Summary", 420), ("Channel Shares", 860)])))
wb.dashboard("2 Finishing", "Better Finisher Than the Model, Almost Every Year",
             f"{np_tot} non-penalty goals from {xg_tot:.0f} xG: +{np_tot - xg_tot:.0f} above expectation, beating xG in {beat} of 17 seasons.",
             [], lambda pg: (wb.row_of(pg, 110, 395, [("Goals vs xG", 1280)]), wb.row_of(pg, 505, 395, [("Goals Above xG", 1280)])))
wb.dashboard("3 Role and Age", "From Dribbler to Playmaker",
             "Per-90 output by season, and his ageing curve. Seasons under 900 minutes (his first two) are noisy.",
             [], lambda pg: (wb.row_of(pg, 110, 360, [(m, 320) for m in ROLE]), wb.row_of(pg, 470, 430, [("Ageing Curve", 1280)])))
wb.dashboard("4 Chances Created", "Chances Created",
             "Every pass that led to a shot in the selected season. Orange = assist.",
             [pS], lambda pg: wb.row_of(pg, 110, 790, [("Chances Created Map", 560), ("Assists by Season", 720)]))

wb.save(HERE / "messi_season_by_season.twbx", images=[IMG / "pitch_full.png", IMG / "pitch_half_vertical.png"], xsd=XSD)
