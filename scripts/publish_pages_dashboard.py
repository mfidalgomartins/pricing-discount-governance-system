"""Prepare GitHub Pages entrypoints for the dashboard (main branch root)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_RELATIVE_PATH = "outputs/dashboard/pricing-discipline-command-center.html"
DASHBOARD_PATH = ROOT / DASHBOARD_RELATIVE_PATH
VENDOR_PATH = ROOT / "outputs" / "dashboard" / "vendor" / "chart.umd.min.js"

ROOT_INDEX = ROOT / "index.html"
ROOT_NOJEKYLL = ROOT / ".nojekyll"
OUTPUTS_INDEX = ROOT / "outputs" / "index.html"
DASHBOARD_INDEX = ROOT / "outputs" / "dashboard" / "index.html"

ROOT_INDEX_TEMPLATE = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Pricing Discipline Command Center</title>
  <meta http-equiv=\"refresh\" content=\"0; url=./{DASHBOARD_RELATIVE_PATH}\" />
</head>
<body>
  <p>Redirecting to dashboard...
    <a href=\"./{DASHBOARD_RELATIVE_PATH}\">Open dashboard</a>
  </p>
</body>
</html>
"""

OUTPUTS_INDEX_TEMPLATE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Outputs Redirect</title>
  <meta http-equiv=\"refresh\" content=\"0; url=./dashboard/\" />
</head>
<body>
  <p>Redirecting to dashboard folder...</p>
</body>
</html>
"""

DASHBOARD_INDEX_TEMPLATE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Dashboard Redirect</title>
  <meta http-equiv=\"refresh\" content=\"0; url=./pricing-discipline-command-center.html\" />
</head>
<body>
  <p>Redirecting to dashboard...</p>
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

    ROOT_INDEX.write_text(ROOT_INDEX_TEMPLATE, encoding="utf-8")
    ROOT_NOJEKYLL.write_text("", encoding="utf-8")
    OUTPUTS_INDEX.write_text(OUTPUTS_INDEX_TEMPLATE, encoding="utf-8")
    DASHBOARD_INDEX.write_text(DASHBOARD_INDEX_TEMPLATE, encoding="utf-8")

    print("GitHub Pages entrypoints prepared:")
    print(f"- {ROOT_INDEX}")
    print(f"- {OUTPUTS_INDEX}")
    print(f"- {DASHBOARD_INDEX}")


if __name__ == "__main__":
    publish()
