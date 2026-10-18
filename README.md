# Messi, Season by Season

**Live page:** https://colinspel.github.io/messi-season-by-season/

Every La Liga match Lionel Messi played for Barcelona in StatsBomb open data, 2004/05 to 2020/21 (519 matches), as an interactive page: season slider with touch heatmap, shot map, chances created, finishing against xG, role shift and ageing curve.

## Findings
- 472 goals and 412 non-penalty goals from 266 non-penalty xG: +146 above expectation, beating xG in 16 of 17 seasons.
- Through 2007/08, 56-62% of his touches came in the right channel. From 2009/10 the central channel took over (peaking at 63% in 2012/13).
- Dribbles won per 90 fell from about 7-9 to about 4; progressive passes per 90 rose from 1-3 to about 8.

## Reproduce
```
python extract_messi.py open-data/data   # messi_data.json + CSVs
python build_page.py                     # messi_season_by_season.html
```

## Caveats
2007/08 is missing one of his 28 matches in the open data (8 of 10 goals), so the career total reads 472 against the official 474. Seasons under 900 minutes are treated as noisy. StatsBomb's position label often says "Right Wing" in false-9 seasons; the touch data is the better guide.

Data: [StatsBomb Open Data](https://github.com/statsbomb/open-data).

## Tableau Public version
`messi_season_by_season.twbx` (built by `build_messi_twb.py`, validated against Tableau's official workbook schema). Dashboards: Season Explorer (season selector, touch heatmap, shot map, channel shares), Finishing, Role and Age, Chances Created.

## Files
- `index.html`: the interactive page (single file, works offline)
- `messi_season_by_season.twbx`: Tableau Public workbook (4 dashboards)
- `extract_messi.py` -> `messi_*.csv`, `messi_data.json`; `build_page.py` -> `index.html`
- `make_tableau_data.py` -> `tableau_data/`; `build_messi_twb.py` (uses `twb_lib.py`, `images/`) -> the `.twbx`
- `linkedin/`: slider screen recording and preview image used in the LinkedIn post
