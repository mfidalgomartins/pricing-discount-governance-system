"""Publish the executive dashboard to GitHub Pages docs/ folder.

Publishes a professionally named dashboard file and keeps docs/index.html as the
stable GitHub Pages entrypoint.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_FILENAME = "pricing-discipline-command-center.html"

SOURCE_HTML = ROOT / "outputs" / "dashboard" / DASHBOARD_FILENAME
SOURCE_VENDOR = ROOT / "outputs" / "dashboard" / "vendor" / "chart.umd.min.js"

TARGET_DOCS = ROOT / "docs"
TARGET_NAMED_HTML = TARGET_DOCS / DASHBOARD_FILENAME
TARGET_INDEX = TARGET_DOCS / "index.html"
TARGET_VENDOR_DIR = TARGET_DOCS / "vendor"
TARGET_VENDOR = TARGET_VENDOR_DIR / "chart.umd.min.js"
TARGET_NOJEKYLL = TARGET_DOCS / ".nojekyll"

INDEX_TEMPLATE = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Executive Pricing Discipline Command Center</title>
  <meta http-equiv=\"refresh\" content=\"0; url=./{DASHBOARD_FILENAME}\" />
  <style>
    body {{
      margin: 0;
      font-family: \"IBM Plex Sans\", \"Avenir Next\", \"Segoe UI\", sans-serif;
      background: #edf2fa;
      color: #0f172a;
      min-height: 100vh;
      display: grid;
      place-items: center;
    }}
    .card {{
      background: #fff;
      border: 1px solid #d3deee;
      border-radius: 14px;
      padding: 24px;
      max-width: 640px;
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
    }}
    a {{ color: #0f4c81; font-weight: 700; text-decoration: none; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1 style=\"margin-top:0\">Opening Executive Dashboard...</h1>
    <p>If redirection does not start automatically, open
      <a href=\"./{DASHBOARD_FILENAME}\">Executive Pricing Discipline Command Center</a>.
    </p>
  </div>
</body>
</html>
"""


def ensure_source_files() -> None:
    missing = [p for p in (SOURCE_HTML, SOURCE_VENDOR) if not p.exists()]
    if missing:
        missing_list = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(f"Missing source file(s): {missing_list}")


def publish() -> None:
    ensure_source_files()

    TARGET_DOCS.mkdir(parents=True, exist_ok=True)
    TARGET_VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SOURCE_HTML, TARGET_NAMED_HTML)
    shutil.copy2(SOURCE_VENDOR, TARGET_VENDOR)
    TARGET_INDEX.write_text(INDEX_TEMPLATE, encoding="utf-8")
    TARGET_NOJEKYLL.touch(exist_ok=True)

    html_text = TARGET_NAMED_HTML.read_text(encoding="utf-8")
    if 'src="vendor/chart.umd.min.js"' not in html_text:
        raise RuntimeError("Dashboard file is not using expected local vendor path.")

    print("GitHub Pages dashboard published:")
    print(f"- {TARGET_INDEX}")
    print(f"- {TARGET_NAMED_HTML}")
    print(f"- {TARGET_VENDOR}")


if __name__ == "__main__":
    publish()
