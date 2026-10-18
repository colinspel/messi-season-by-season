"""
Every Lionel Messi La Liga match in StatsBomb open data (Barcelona, 2004/05 to 2020/21).

    python extract_messi.py /path/to/open-data/data  ->  messi_data.json (+ CSVs for inspection)

Coordinates: 120 x 80 yards, Barcelona attacking toward x = 120 in every event.
"""
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

MESSI = 5503
BORN = date(1987, 6, 24)
OUT = Path(__file__).parent
GOAL = (120.0, 40.0)
TOUCH_TYPES = {"Pass", "Carry", "Ball Receipt*", "Shot", "Dribble", "Miscontrol", "Dispossessed", "Foul Won"}
SET_PIECE_PASS = {"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"}
GX, GY = 24, 16  # heatmap grid: 5-yard cells


def clock(s):
    m, sec = s.split(":")
    return int(m) + int(sec) / 60


def d2g(x, y):
    return math.hypot(GOAL[0] - x, GOAL[1] - y)


def progressive(a, b, min_len=0.0):
    if a is None or b is None or a[0] < 48 or math.hypot(b[0] - a[0], b[1] - a[1]) < min_len:
        return False
    return d2g(*b) <= 0.75 * d2g(*a)


def in_box(p):
    return p[0] >= 102 and 18 <= p[1] <= 62


def main(data):
    data = Path(data)
    comps = json.load(open(data / "competitions.json"))
    seasons = sorted([c for c in comps if c["competition_name"] == "La Liga" and c["season_name"] >= "2004"],
                     key=lambda c: c["season_name"])
    per_match, shots, keypasses, heat = [], [], [], {}
    for c in seasons:
        sname = c["season_name"]
        heat[sname] = np.zeros((GY, GX), dtype=int)
        for m in json.load(open(data / "matches" / str(c["competition_id"]) / f"{c['season_id']}.json")):
            if "Barcelona" not in (m["home_team"]["home_team_name"], m["away_team"]["away_team_name"]):
                continue
            ef, lf = data / "events" / f"{m['match_id']}.json", data / "lineups" / f"{m['match_id']}.json"
            if not ef.exists() or not lf.exists():
                continue
            ev = json.load(open(ef))
            lu = json.load(open(lf))
            me = next((p for t in lu for p in t["lineup"] if p["player_id"] == MESSI), None)
            if not me or not me["positions"]:
                continue
            end_min = max(e["minute"] + e["second"] / 60 for e in ev if e["period"] <= 4)
            spells = [p for p in me["positions"] if not (p["from_period"] and p["from_period"] >= 5)]
            start = min(clock(p["from"]) for p in spells)
            offs = [clock(p["to"]) for p in spells if p["to"] and any(k in (p["end_reason"] or "") for k in ("Substitution - Off", "Sent Off", "Red Card"))]
            minutes = max(0.0, (min(offs) if offs else end_min) - start)
            pos_min = defaultdict(float)
            for p in spells:
                pos_min[p["position"]] += max(0.0, (clock(p["to"]) if p["to"] else end_min) - clock(p["from"]))
            main_pos = max(pos_min, key=pos_min.get)
            by_id = {e["id"]: e for e in ev}
            home = m["home_team"]["home_team_name"]
            opp = m["away_team"]["away_team_name"] if home == "Barcelona" else home
            bs, os_ = (m["home_score"], m["away_score"]) if home == "Barcelona" else (m["away_score"], m["home_score"])
            r = defaultdict(float)
            for e in ev:
                if e["period"] >= 5 or e.get("player", {}).get("id") != MESSI:
                    continue
                t, loc = e["type"]["name"], e.get("location")
                if t in TOUCH_TYPES and loc:
                    r["touches"] += 1
                    gx, gy = min(GX - 1, int(loc[0] // 5)), min(GY - 1, int(loc[1] // 5))
                    heat[sname][gy, gx] += 1
                    r["sum_x"] += loc[0]; r["sum_y"] += loc[1]
                    r["box_touches"] += in_box(loc)
                if t == "Shot":
                    s = e["shot"]
                    pen = s["type"]["name"] == "Penalty"
                    goal = s["outcome"]["name"] == "Goal"
                    r["shots"] += 1; r["goals"] += goal
                    if pen:
                        r["pen_goals"] += goal; r["pens"] += 1
                    else:
                        r["np_shots"] += 1; r["np_goals"] += goal; r["npxg"] += s["statsbomb_xg"]
                    shots.append(dict(season=sname, date=m["match_date"], opponent=opp, minute=e["minute"],
                                      x=round(loc[0], 1), y=round(loc[1], 1), xg=round(s["statsbomb_xg"], 3),
                                      goal=int(goal), pen=int(pen), body=s["body_part"]["name"],
                                      fk=int(s["type"]["name"] == "Free Kick"), outcome=s["outcome"]["name"]))
                if t == "Pass":
                    p = e["pass"]
                    done = "outcome" not in p
                    open_play = p.get("type", {}).get("name") not in SET_PIECE_PASS
                    r["passes"] += 1; r["passes_done"] += done
                    r["prog_passes"] += done and open_play and progressive(loc, p.get("end_location"))
                    if p.get("goal_assist"):
                        r["assists"] += 1
                    if p.get("shot_assist") or p.get("goal_assist"):
                        r["key_passes"] += 1
                        shot = next((x for x in ev if x["type"]["name"] == "Shot" and x["shot"].get("key_pass_id") == e["id"]), None)
                        sxg = shot["shot"]["statsbomb_xg"] if shot else 0.0
                        r["xa"] += sxg
                        keypasses.append(dict(season=sname, date=m["match_date"], opponent=opp,
                                              x=round(loc[0], 1), y=round(loc[1], 1),
                                              ex=round(p["end_location"][0], 1), ey=round(p["end_location"][1], 1),
                                              xa=round(sxg, 3), assist=int(bool(p.get("goal_assist"))),
                                              scorer=(shot["player"]["name"] if shot else None)))
                if t == "Carry":
                    r["prog_carries"] += progressive(loc, e["carry"]["end_location"], 5)
                if t == "Dribble":
                    r["dribbles"] += 1
                    r["dribbles_won"] += e["dribble"]["outcome"]["name"] == "Complete"
            per_match.append(dict(season=sname, match_id=m["match_id"], date=m["match_date"], opponent=opp,
                                  result=f"{bs}-{os_}", minutes=round(minutes, 1), main_position=main_pos,
                                  start=int(start == 0), **{k: v for k, v in r.items()}))
    pm = pd.DataFrame(per_match).fillna(0)
    pm.to_csv(OUT / "messi_matches.csv", index=False)
    pd.DataFrame(shots).to_csv(OUT / "messi_shots.csv", index=False)
    pd.DataFrame(keypasses).to_csv(OUT / "messi_keypasses.csv", index=False)

    g = pm.groupby("season")
    num = ["minutes", "goals", "np_goals", "pen_goals", "pens", "shots", "np_shots", "npxg", "assists", "xa",
           "key_passes", "passes", "passes_done", "prog_passes", "prog_carries", "dribbles", "dribbles_won",
           "touches", "box_touches", "sum_x", "sum_y"]
    se = g[num].sum()
    se["matches"] = g.size()
    se["starts"] = g.start.sum()
    se["main_position"] = g.apply(lambda d: d.groupby("main_position").minutes.sum().idxmax())
    se["avg_x"] = se.sum_x / se.touches
    se["avg_y"] = se.sum_y / se.touches
    se["age"] = [round((date(int(s[:4]), 8, 1) - BORN).days / 365.25, 1) for s in se.index]
    for c in ("np_goals", "npxg", "assists", "xa", "key_passes", "prog_passes", "prog_carries", "dribbles_won",
              "shots", "box_touches", "touches"):
        se[c + "_p90"] = se[c] / se.minutes * 90
    se = se.drop(columns=["sum_x", "sum_y"]).reset_index()
    se.to_csv(OUT / "messi_seasons.csv", index=False)

    out = dict(
        seasons=json.loads(se.round(4).to_json(orient="records")),
        shots=json.loads(pd.DataFrame(shots).to_json(orient="split", index=False)),
        keypasses=json.loads(pd.DataFrame(keypasses).to_json(orient="split", index=False)),
        heat={k: v.tolist() for k, v in heat.items()},
        grid=[GX, GY],
    )
    (OUT / "messi_data.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(se[["season", "matches", "minutes", "goals", "np_goals", "npxg", "assists", "main_position", "age"]].round(1).to_string())
    print("TOTAL goals", int(se.goals.sum()), "| assists", int(se.assists.sum()), "| matches", int(se.matches.sum()))


if __name__ == "__main__":
    main(sys.argv[1])
