"""Tableau-ready CSVs for the Messi workbook (long formats so each chart is a single sheet)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "tableau_data"
OUT.mkdir(exist_ok=True)
d = json.loads((HERE / "messi_data.json").read_text())
se = pd.read_csv(HERE / "messi_seasons.csv")
NOISY = 900

se["season_short"] = se.season.str[2:4] + "/" + se.season.str[7:9]
se["goals_minus_npxg"] = (se.np_goals - se.npxg).round(2)
se["finishing"] = np.where(se.np_goals >= se.npxg, "Beat xG", "Below xG")
se["goals_label"] = se.np_goals.astype(int).astype(str) + " (" + se.npxg.round(1).astype(str) + " xG)"
se["low_minutes"] = np.where(se.minutes < NOISY, "Under 900 min", "Full season")
se["season_idx"] = range(1, len(se) + 1)
se["summary"] = (se.season + " · age " + se.age.astype(int).astype(str) + " · " + se.matches.astype(str) + " matches · "
                 + se.goals.astype(int).astype(str) + " goals (" + se.pen_goals.astype(int).astype(str) + " pen) · npxG "
                 + se.npxg.round(1).astype(str) + " · " + se.assists.astype(int).astype(str) + " assists · xA "
                 + se.xa.round(1).astype(str) + " · " + se.main_position)
se.round(4).to_csv(OUT / "messi_seasons.csv", index=False)

GX, GY = d["grid"]
rows, ch = [], []
for s, g in d["heat"].items():
    g = np.array(g); tot = g.sum() or 1
    for gy in range(GY):
        for gx in range(GX):
            if g[gy, gx]:
                # cell centre; y flipped so the attacker's left is at the top in Tableau (y axis points up)
                rows.append(dict(season=s, x=gx * 5 + 2.5, y_plot=80 - (gy * 5 + 2.5), touches=int(g[gy, gx]),
                                 share=round(g[gy, gx] / tot, 5)))
    ch += [dict(season=s, channel="Right channel", share=round(g[11:, :].sum() / tot, 4)),
           dict(season=s, channel="Central channel", share=round(g[5:11, :].sum() / tot, 4)),
           dict(season=s, channel="Left channel", share=round(g[:5, :].sum() / tot, 4))]
pd.DataFrame(rows).to_csv(OUT / "messi_heat.csv", index=False)
pd.DataFrame(ch).to_csv(OUT / "messi_channels.csv", index=False)

sh = pd.read_csv(HERE / "messi_shots.csv")
sh["result"] = np.where(sh.goal == 1, "Goal", "No goal")
sh = sh[sh.pen == 0]
sh.to_csv(OUT / "messi_shots.csv", index=False)

kp = pd.read_csv(HERE / "messi_keypasses.csv").reset_index().rename(columns={"index": "pass_id"})
kp["kind"] = np.where(kp.assist == 1, "Assist", "Chance created")
lines = pd.concat([kp.assign(point=1, px=kp.x, py=kp.y), kp.assign(point=2, px=kp.ex, py=kp.ey)])
lines[["pass_id", "season", "date", "opponent", "kind", "xa", "scorer", "point", "px", "py"]].sort_values(["pass_id", "point"]).to_csv(
    OUT / "messi_keypass_lines.csv", index=False)

role = []
for _, r in se.iterrows():
    for col, label in [("dribbles_won_p90", "Dribbles won per 90"), ("prog_passes_p90", "Progressive passes per 90"),
                       ("key_passes_p90", "Key passes per 90"), ("shots_p90", "Shots per 90")]:
        role.append(dict(season=r.season, season_idx=r.season_idx, metric=label, value=round(r[col], 3), low_minutes=r.low_minutes))
pd.DataFrame(role).to_csv(OUT / "messi_role.csv", index=False)

ok = se[se.minutes >= NOISY]
age = pd.concat([pd.DataFrame(dict(season=ok.season, age=ok.age.astype(int), series="Actual: non-penalty goals + assists per 90",
                                   value=((ok.np_goals + ok.assists) / ok.minutes * 90).round(3))),
                 pd.DataFrame(dict(season=ok.season, age=ok.age.astype(int), series="Expected: npxG + xA per 90",
                                   value=((ok.npxg + ok.xa) / ok.minutes * 90).round(3)))])
age.to_csv(OUT / "messi_age.csv", index=False)
print("heat rows", len(rows), "| shots", len(sh), "| key-pass lines", len(lines), "| seasons", len(se))
