"""Prepare GitHub Pages root entrypoint for the executive dashboard."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_RELATIVE_PATH = "outputs/dashboard/executive-pricing-discipline-command-center.html"
DASHBOARD_PATH = ROOT / DASHBOARD_RELATIVE_PATH
VENDOR_PATH = ROOT / "outputs" / "dashboard" / "vendor" / "chart.umd.min.js"
INDEX_PATH = ROOT / "index.html"
NOJEKYLL_PATH = ROOT / ".nojekyll"

INDEX_TEMPLATE = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Executive Pricing Discipline Command Center</title>
  <meta http-equiv=\"refresh\" content=\"0; url=./{DASHBOARD_RELATIVE_PATH}\" />
  <style>
    body {{
      margin: 0;
      font-family: \"IBM Plex Sans\", \"Avenir Next\", \"Segoe UI\", sans-serif;
      background: #edf2fa;
      color: #0f172a;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 16px;
    }}
    .card {{
      background: #fff;
      border: 1px solid #d3deee;
      border-radius: 14px;
      padding: 24px;
      max-width: 700px;
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
    }}
    a {{ color: #0f4c81; font-weight: 700; text-decoration: none; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1 style=\"margin-top:0\">Opening Executive Dashboard...</h1>
    <p>If redirection does not start automatically, open
      <a href=\"./{DASHBOARD_RELATIVE_PATH}\">Executive Pricing Discipline Command Center</a>.
    </p>
  </div>
</body>
</html>
"""


def publish() -> None:
    missing = [p for p in (DASHBOARD_PATH, VENDOR_PATH) if not p.exists()]
    if missing:
        missing_list = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(f"Missing required dashboard asset(s): {missing_list}")

    html_text = DASHBOARD_PATH.read_text(encoding="utf-8")
    if 'src="vendor/chart.umd.min.js"' not in html_text:
        raise RuntimeError("Dashboard source does not reference expected local vendor path.")

    INDEX_PATH.write_text(INDEX_TEMPLATE, encoding="utf-8")
    NOJEKYLL_PATH.write_text("", encoding="utf-8")

    print("GitHub Pages entrypoint prepared:")
    print(f"- {INDEX_PATH}")
    print(f"- {NOJEKYLL_PATH}")
    print(f"- Dashboard source: {DASHBOARD_PATH}")


if __name__ == "__main__":
    publish()
