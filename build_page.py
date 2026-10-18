"""Inject messi_data.json into page_src.html -> messi_season_by_season.html."""
from pathlib import Path
here = Path(__file__).parent
src = (here / "page_src.html").read_text()
data = (here / "messi_data.json").read_text().replace("</", "<\\/")
out = here / "index.html"
out.write_text(src.replace("/*DATA*/null", data))
print(out, out.stat().st_size // 1024, "KB")
