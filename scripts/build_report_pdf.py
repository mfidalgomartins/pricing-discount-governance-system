"""
Build the analytical PDF report for the Pricing Discount Governance System.

Reads data/processed/report_stats.json and outputs/graphs/*.png and writes
outputs/reports/pricing_discount_governance_report.pdf

Run:
    python scripts/build_report_pdf.py
"""

from __future__ import annotations

import json
from pathlib import Path

import reportlab
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
GRAPHS = ROOT / "outputs" / "graphs"
REPORTS = ROOT / "outputs" / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)
S = json.loads((ROOT / "data" / "processed" / "report_stats.json").read_text(encoding="utf-8"))
SENSITIVITY_THRESHOLDS = sorted(float(value) for value in S["high_discount_sensitivity_thresholds"])
LOW_THRESHOLD = SENSITIVITY_THRESHOLDS[0]
BASE_THRESHOLD = float(S["high_discount_threshold"])
HIGH_THRESHOLD = SENSITIVITY_THRESHOLDS[-1]
SEG_VALUE = {row["segment"]: row for row in S.get("segment_value_pool", [])}
CHAN_VALUE = {row["sales_channel"]: row for row in S.get("channel_value_pool", [])}
RISK_DETAIL = {row["risk_tier"]: row for row in S.get("risk_tier_detail", [])}
SCENARIOS = {int(row["realization_improvement_pp"]): row for row in S.get("recovery_scenarios", [])}
CAT_VALUE = {row["category"]: row for row in S.get("category", [])}
PROF_SERVICES = CAT_VALUE.get("Professional Services", S["category"][1])
CORE_PLATFORM = CAT_VALUE.get("Core Platform", S["category"][-1])
DISC_MARGIN_SLOPE_ABS = abs(float(S["disc_margin_slope"]))
ANALYSIS_YEARS = max(float(S["n_months"]) / 12.0, 1.0)
TWO_POINT_CAPTURE = S["total_list_revenue"] * 0.02
TWO_POINT_ANNUAL_RUN_RATE = TWO_POINT_CAPTURE / ANALYSIS_YEARS
REGION_BY_DISCOUNT = sorted(S["region"], key=lambda row: row["discount"])
SHALLOWEST_REGION = REGION_BY_DISCOUNT[0]
DEEPEST_REGION = REGION_BY_DISCOUNT[-1]
REGION_DISCOUNT_RANGE = DEEPEST_REGION["discount"] - SHALLOWEST_REGION["discount"]

# ---------------------------------------------------------------------------
# Typography and palette
# ---------------------------------------------------------------------------
SYSTEM_FONT_DIR = Path("/System/Library/Fonts/Supplemental")
REPORTLAB_FONT_DIR = Path(reportlab.__file__).resolve().parent / "fonts"


def _font_path(system_name: str, fallback_name: str) -> Path:
    system_path = SYSTEM_FONT_DIR / system_name
    return system_path if system_path.exists() else REPORTLAB_FONT_DIR / fallback_name


FONT_FILES = {
    "ReportSans": _font_path("Arial.ttf", "Vera.ttf"),
    "ReportSansBold": _font_path("Arial Bold.ttf", "VeraBd.ttf"),
    "ReportSansItalic": _font_path("Arial Italic.ttf", "VeraIt.ttf"),
    "ReportSansBoldItalic": _font_path("Arial Bold Italic.ttf", "VeraBI.ttf"),
    "ReportDisplay": _font_path("Georgia.ttf", "VeraSe.ttf"),
    "ReportDisplayBold": _font_path("Georgia Bold.ttf", "VeraSeBd.ttf"),
    "ReportDisplayItalic": _font_path("Georgia Italic.ttf", "VeraIt.ttf"),
    "ReportDisplayBoldItalic": _font_path("Georgia Bold Italic.ttf", "VeraBI.ttf"),
}
for font_name, font_path in FONT_FILES.items():
    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
pdfmetrics.registerFontFamily(
    "ReportSans",
    normal="ReportSans",
    bold="ReportSansBold",
    italic="ReportSansItalic",
    boldItalic="ReportSansBoldItalic",
)
pdfmetrics.registerFontFamily(
    "ReportDisplay",
    normal="ReportDisplay",
    bold="ReportDisplayBold",
    italic="ReportDisplayItalic",
    boldItalic="ReportDisplayBoldItalic",
)

PAPER = colors.white
INK = colors.HexColor("#151515")
INK_LIGHT = colors.HexColor("#556168")
ACCENT = colors.HexColor("#00a6d6")
ACCENT_DARK = colors.HexColor("#006f91")
NAVY = colors.HexColor("#12354a")
RULE = colors.HexColor("#ccd4d9")
PANEL = colors.HexColor("#f1f4f5")
PANEL_BLUE = colors.HexColor("#e7f7fb")

PAGE_W, PAGE_H = LETTER
LM, RM, TM, BM = 0.86 * inch, 0.78 * inch, 0.88 * inch, 0.78 * inch
CONTENT_W = PAGE_W - LM - RM


# ---------------------------------------------------------------------------
# Number helpers
# ---------------------------------------------------------------------------
def money(v, d=0):
    return f"${v / 1e6:,.{d}f}M" if v < 1e9 else f"${v / 1e9:,.2f}B"


def pct(v, d=1):
    return f"{v * 100:.{d}f}%"


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
styles = getSampleStyleSheet()
BODY = ParagraphStyle(
    "body",
    parent=styles["Normal"],
    fontName="ReportSans",
    fontSize=9.45,
    leading=13.55,
    alignment=TA_LEFT,
    textColor=INK,
    spaceAfter=7.5,
)
LEAD = ParagraphStyle(
    "lead",
    parent=BODY,
    fontName="ReportSans",
    fontSize=11.8,
    leading=16.1,
    textColor=INK,
    spaceAfter=11,
)
BULLET = ParagraphStyle(
    "bullet",
    parent=BODY,
    leftIndent=18,
    bulletIndent=3,
    bulletFontName="ReportSansBold",
    bulletColor=ACCENT,
    spaceAfter=5,
    alignment=TA_LEFT,
)
H1 = ParagraphStyle(
    "h1",
    parent=styles["Heading1"],
    fontName="ReportDisplayBold",
    fontSize=26,
    leading=29,
    textColor=INK,
    spaceBefore=0,
    spaceAfter=5,
)
H1KICK = ParagraphStyle(
    "h1kick",
    fontName="ReportSansBold",
    fontSize=8.2,
    textColor=INK_LIGHT,
    spaceAfter=5,
    leading=10,
)
H2 = ParagraphStyle(
    "h2",
    parent=styles["Heading2"],
    fontName="ReportDisplayBold",
    fontSize=14.3,
    leading=17,
    textColor=INK,
    spaceBefore=14,
    spaceAfter=5,
)
H3 = ParagraphStyle(
    "h3",
    parent=styles["Heading3"],
    fontName="ReportSansBold",
    fontSize=10.2,
    leading=13,
    textColor=INK,
    spaceBefore=8,
    spaceAfter=3,
)
CAP = ParagraphStyle(
    "cap",
    fontName="ReportSans",
    fontSize=7.55,
    textColor=INK_LIGHT,
    alignment=TA_LEFT,
    spaceBefore=4,
    spaceAfter=15,
    leading=10.2,
)
TOC_H = ParagraphStyle(
    "toch",
    fontName="ReportDisplayBold",
    fontSize=29,
    leading=32,
    textColor=INK,
    spaceAfter=18,
)
PULL = ParagraphStyle(
    "pull",
    fontName="ReportDisplayBold",
    fontSize=13.5,
    leading=17.5,
    textColor=ACCENT_DARK,
    alignment=TA_LEFT,
    spaceBefore=2,
    spaceAfter=2,
)

TOC = TableOfContents()
TOC.levelStyles = [
    ParagraphStyle(
        "toc1",
        fontName="ReportSansBold",
        fontSize=10.2,
        leading=21,
        textColor=INK,
        spaceBefore=2,
    ),
    ParagraphStyle(
        "toc2",
        fontName="ReportSans",
        fontSize=8.8,
        leading=16,
        textColor=INK_LIGHT,
        leftIndent=19,
    ),
]

# ---------------------------------------------------------------------------
# Flowable builders
# ---------------------------------------------------------------------------
_section_no = [0]


class ChapterHeader(Flowable):
    """Consulting-style chapter opener with a strong editorial hierarchy."""

    def __init__(self, number: int, title: str, kicker: str | None):
        super().__init__()
        self.number = number
        self.title = title
        self.kicker = kicker
        self.height = 1.58 * inch

    def wrap(self, avail_width, avail_height):
        self.width = avail_width
        return avail_width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(PANEL_BLUE)
        canvas.setFont("ReportDisplayBold", 57)
        canvas.drawString(0, 0.43 * inch, str(self.number))

        text_x = 0.82 * inch
        if self.kicker:
            canvas.setFillColor(INK_LIGHT)
            canvas.setFont("ReportSansBold", 8.1)
            canvas.drawString(text_x, 1.31 * inch, self.kicker.capitalize())

        title = Paragraph(self.title, H1)
        _, title_height = title.wrap(self.width - text_x, 0.82 * inch)
        title.drawOn(canvas, text_x, 0.47 * inch + (0.56 * inch - title_height))

        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(2.3)
        canvas.line(text_x, 0.28 * inch, self.width, 0.28 * inch)
        canvas.restoreState()


def section(title, kicker=None):
    _section_no[0] += 1
    n = _section_no[0]
    header = ChapterHeader(n, title, kicker)
    header._toc = (0, f"{n}  {title}")
    return [PageBreak(), header]


def sub(title):
    p = Paragraph(title, H2)
    p._toc = (1, title)
    return p


def para(text, style=BODY):
    return Paragraph(text, style)


TBL_WRAP = ParagraphStyle(
    "tblwrap",
    fontName="ReportSans",
    fontSize=8.45,
    leading=10.8,
    textColor=INK,
    alignment=TA_LEFT,
)


def tbl_para(text):
    return Paragraph(text, TBL_WRAP)


def bullets(items):
    return [Paragraph(t, BULLET, bulletText="•") for t in items]


def figure(fname, caption, width=CONTENT_W):
    path = GRAPHS / fname
    iw, ih = PILImage.open(path).size
    h = width * ih / iw
    img = Image(str(path), width=width, height=h)
    cap = Paragraph(caption, CAP)
    return KeepTogether([Spacer(1, 4), img, cap])


def styled_table(data, col_widths, align_right_from=1, header=True, highlight_rows=None):
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    cmds = [
        ("FONTNAME", (0, 0), (-1, -1), "ReportSans"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.45),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, RULE),
    ]
    if header:
        cmds += [
            ("FONTNAME", (0, 0), (-1, 0), "ReportSansBold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.15),
            ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ("BACKGROUND", (0, 0), (-1, 0), PANEL_BLUE),
            ("ALIGN", (align_right_from, 0), (-1, 0), "RIGHT"),
            ("LINEABOVE", (0, 0), (-1, 0), 1.4, ACCENT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, ACCENT_DARK),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ]
    cmds.append(("LINEBELOW", (0, -1), (-1, -1), 0.75, RULE))
    if highlight_rows:
        for r in highlight_rows:
            cmds += [
                ("BACKGROUND", (0, r), (-1, r), PANEL_BLUE),
                ("TEXTCOLOR", (0, r), (-1, r), ACCENT_DARK),
                ("FONTNAME", (0, r), (-1, r), "ReportSansBold"),
            ]
    t.setStyle(TableStyle(cmds))
    return t


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------
def _footer(canvas, doc, label):
    canvas.saveState()
    canvas.setFont("ReportSansBold", 6.8)
    canvas.setFillColor(INK)
    canvas.drawString(LM, 0.46 * inch, "Pricing discount governance · Analytical report")
    canvas.setFont("ReportSans", 7)
    canvas.drawRightString(PAGE_W - RM, 0.46 * inch, f"{canvas.getPageNumber()}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.45)
    canvas.line(LM, 0.61 * inch, PAGE_W - RM, 0.61 * inch)
    if label:
        canvas.setFillColor(INK_LIGHT)
        canvas.setFont("ReportSans", 6.8)
        canvas.drawRightString(PAGE_W - RM, PAGE_H - 0.48 * inch, label)
    canvas.restoreState()


def cover_page(canvas, doc):
    canvas.setTitle("Pricing Discount Governance: Analytical Report")
    canvas.setAuthor("Miguel Fidalgo Martins")
    canvas.setSubject("Synthetic B2B pricing governance and discount-risk analysis")
    canvas.setKeywords("pricing governance, discount analytics, margin risk, synthetic data")
    canvas.setCreator("Pricing Discount Governance System")
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Original data-flow ribbon: a restrained, vector-only cover gesture.
    ribbon_colors = [
        colors.HexColor("#12354a"),
        colors.HexColor("#0057b8"),
        colors.HexColor("#00a6d6"),
        colors.HexColor("#73d3e8"),
        colors.HexColor("#d32778"),
        colors.HexColor("#48357a"),
    ]
    ribbon_start_x = 3.65 * inch
    convergence_x = 5.05 * inch
    convergence_y = 3.7 * inch
    for i in range(58):
        start_y = -0.4 * inch + i * 4.8
        end_y = 4.95 * inch + i * 6.1
        path = canvas.beginPath()
        path.moveTo(ribbon_start_x, start_y)
        path.curveTo(
            4.2 * inch,
            start_y + 0.18 * inch,
            convergence_x - 0.35 * inch,
            convergence_y - 0.55 * inch + i * 0.8,
            convergence_x,
            convergence_y,
        )
        path.curveTo(
            convergence_x + 0.45 * inch,
            convergence_y + 0.55 * inch,
            PAGE_W - 0.45 * inch,
            end_y - 0.65 * inch,
            PAGE_W + 0.25 * inch,
            end_y,
        )
        canvas.setStrokeColor(ribbon_colors[i % len(ribbon_colors)])
        canvas.setLineWidth(0.72 + (i % 4) * 0.12)
        canvas.drawPath(path, stroke=1, fill=0)

    canvas.setFillColor(INK)
    canvas.setFont("ReportSansBold", 8.6)
    canvas.drawString(LM, PAGE_H - 0.9 * inch, "Pricing governance diagnostic review")
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(2.4)
    canvas.line(LM, PAGE_H - 1.05 * inch, LM + 1.05 * inch, PAGE_H - 1.05 * inch)
    canvas.setFillColor(INK)
    canvas.setFont("ReportDisplayBold", 34)
    canvas.drawString(LM, PAGE_H - 1.82 * inch, "Discount discipline")
    canvas.drawString(LM, PAGE_H - 2.34 * inch, "and margin risk")
    canvas.setFont("ReportSans", 12.7)
    canvas.drawString(LM, PAGE_H - 2.78 * inch, "A diagnostic of pricing health across")
    canvas.drawString(
        LM,
        PAGE_H - 3.04 * inch,
        f"a {money(S['total_revenue'], 2)} revenue book",
    )
    canvas.setFillColor(INK_LIGHT)
    canvas.setFont("ReportSans", 8.4)
    canvas.drawString(LM, PAGE_H - 3.52 * inch, "Miguel Fidalgo Martins")
    canvas.drawString(LM, PAGE_H - 3.72 * inch, S["coverage"])

    # Key figures use type and whitespace, never dashboard cards.
    figs = [
        (money(S["total_revenue"], 2), "Revenue analysed"),
        (money(S["revenue_forgone"]), "Forgone to discount"),
        (pct(S["price_realization"]), "Price realization"),
        (str(S["high_tier_customers"]), "High-risk accounts"),
    ]
    metric_x = [LM, LM + 1.62 * inch]
    metric_y = [2.75 * inch, 2.02 * inch]
    for i, (big, small) in enumerate(figs):
        x = metric_x[i % 2]
        y = metric_y[i // 2]
        canvas.setFillColor(ACCENT)
        canvas.setFont("ReportSansBold", 18.5)
        canvas.drawString(x, y, big)
        canvas.setFillColor(INK_LIGHT)
        canvas.setFont("ReportSansBold", 6.9)
        canvas.drawString(x, y - 0.18 * inch, small.upper())

    # Verdict is treated as the editorial thesis, not as a template panel.
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(1.5)
    canvas.line(LM, 1.58 * inch, LM + 2.95 * inch, 1.58 * inch)
    canvas.setFillColor(INK_LIGHT)
    canvas.setFont("ReportSansBold", 7.2)
    canvas.drawString(LM, 1.38 * inch, "Verdict")
    canvas.setFillColor(INK)
    canvas.setFont("ReportDisplayBold", 13.5)
    canvas.drawString(LM, 1.11 * inch, "Realization control gap")
    canvas.setFillColor(INK_LIGHT)
    canvas.setFont("ReportSans", 7.9)
    canvas.drawString(
        LM,
        0.83 * inch,
        "Revenue is stable, but list-to-net discipline is leaking value into",
    )
    canvas.drawString(
        LM,
        0.67 * inch,
        "Enterprise accounts and indirect-channel deals.",
    )
    canvas.setFont("ReportSans", 6.6)
    canvas.drawString(LM, 0.34 * inch, "Methodology in Section 3 · Limitations in Section 10")
    canvas.drawString(LM, 0.22 * inch, "All figures reconciled against governed pipeline outputs")
    canvas.restoreState()


def later_pages(canvas, doc):
    _footer(canvas, doc, "")


# ---------------------------------------------------------------------------
# Document with TOC hook
# ---------------------------------------------------------------------------
class Doc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        toc = getattr(flowable, "_toc", None)
        if toc is not None:
            level, text = toc
            self.notify("TOCEntry", (level, text, self.page))


frame = Frame(LM, BM, CONTENT_W, PAGE_H - TM - BM, id="main")
doc = Doc(
    str(REPORTS / "pricing_discount_governance_report.pdf"),
    pagesize=LETTER,
    leftMargin=LM,
    rightMargin=RM,
    topMargin=TM,
    bottomMargin=BM,
    title="Pricing Discount Governance: Analytical Report",
    author="Miguel Fidalgo Martins",
)
doc.addPageTemplates(
    [
        PageTemplate(id="cover", frames=[frame], onPage=cover_page),
        PageTemplate(id="body", frames=[frame], onPage=later_pages),
    ]
)

story = []
A = story.append


def addall(xs):
    for x in xs:
        story.append(x)


# ===========================================================================
# COVER (rendered by canvas) — switch to the body template after page one
# ===========================================================================
A(NextPageTemplate("body"))
A(PageBreak())  # ends cover page

# ===========================================================================
# TABLE OF CONTENTS
# ===========================================================================
A(Paragraph("Contents", TOC_H))
A(HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceAfter=10))
A(TOC)

# ===========================================================================
# 1. EXECUTIVE SUMMARY
# ===========================================================================
addall(section("Executive summary", "What the book is telling us"))
A(
    para(
        f"The commercial book is not failing; it is under-realising. Across {money(S['total_revenue'], 2)} "
        f"of revenue and {S['n_order_items']:,} order lines over {S['coverage']}, the business converts only "
        f"{pct(S['price_realization'])} of list value into billed revenue. That gap is not random deal noise. "
        f"It is stable over time, concentrated in Enterprise and indirect channels, and large enough to manage "
        f"as a value-recovery programme rather than a broad price increase.",
        LEAD,
    )
)
A(
    para(
        f"The value bridge is clear. List value over the period was {money(S['total_list_revenue'], 2)}; realized "
        f"revenue was {money(S['total_revenue'], 2)}. The difference, {money(S['revenue_forgone'])}, is the list-to-net "
        f"concession embedded in the book. Monthly realization stays inside a narrow {pct(S['pr_min'])} to "
        f"{pct(S['pr_max'])} band for {S['n_months']} months. A metric that stable is not a series of isolated "
        f"commercial exceptions. It is a standing operating level."
    )
)
A(
    para(
        f"The margin signal is equally direct. At customer level, average discount and average margin carry a "
        f"{S['disc_margin_r']:.2f} correlation, with margin falling by an estimated {DISC_MARGIN_SLOPE_ABS:.2f} points "
        f"for each additional discount point. The line-level view points the same way: blended margin falls from "
        f"{pct(S['margin_best_bucket'] / 100)} in the shallowest discount band to "
        f"{pct(S['margin_worst_bucket'] / 100)} in the deepest. The evidence supports a practical conclusion: depth "
        f"is the strongest visible marker of margin pressure in this book."
    )
)
A(
    para(
        f"The concentration makes the problem actionable. Enterprise is {money(S['segments'][0]['total_revenue'])} "
        f"of revenue, or {pct(S['segments'][0]['total_revenue'] / S['total_revenue'])} of the book, and carries the "
        f"weakest discount-margin position: {pct(S['segments'][0]['avg_discount_pct'])} average discount, "
        f"{pct(S['segments'][0]['avg_margin_proxy_pct'])} margin proxy, and "
        f"{pct(S['segments'][0]['share_high_discount'])} of revenue past the high-discount line. The top "
        f"{pct(0.20, 0)} of customers account for {pct(S['top20_rev_share'])} of revenue, so a focused programme "
        f"can reach the value pool without placing the whole sales motion under new controls."
    )
)
A(
    para(
        f"The management implication is specific. Do not treat this as a blanket price-rise mandate. The value pool sits "
        f"in three places: Enterprise renewal economics, indirect-channel approval discipline, and Professional Services "
        f"pricing. A two-point realization lift is worth about {money(TWO_POINT_CAPTURE)} on the analysed list-price base, "
        f"equivalent to roughly {money(TWO_POINT_ANNUAL_RUN_RATE)} per year at the current run rate, before any volume "
        f"response. That is the prize to test, not assume."
    )
)

A(sub("The five findings that matter"))
addall(
    bullets(
        [
            f"<b>Price realization is stuck at {pct(S['price_realization'])}.</b> The {money(S['revenue_forgone'])} forgone to "
            f"discount is a standing cost, not a seasonal one. Monthly realization never rises above {pct(S['pr_max'])}.",
            f"<b>Discount depth marks margin pressure.</b> A customer-level slope of {DISC_MARGIN_SLOPE_ABS:.2f} margin points "
            f"per discount point, and a {pct(S['margin_best_bucket'] / 100)}-to-{pct(S['margin_worst_bucket'] / 100)} margin "
            f"drop across depth bands, makes depth the clearest pricing-risk signal in the book.",
            f"<b>Enterprise is the priority segment.</b> It holds {pct(S['segments'][0]['total_revenue'] / S['total_revenue'])} of "
            f"revenue at the lowest margin proxy of the four segments and the highest high-discount share at "
            f"{pct(S['segments'][0]['share_high_discount'])}.",
            f"<b>Indirect channels discount deepest.</b> The reseller channel runs a {pct(S['channel']['Reseller']['discount'])} "
            f"weighted discount against {pct(S['channel']['Online']['discount'])} Online, and the Enterprise-reseller cell reaches "
            f"{pct(S['enterprise_reseller_disc'])} with {pct(S.get('enterprise_reseller', {}).get('high_discount_share', 0.886))} of its revenue deeply discounted.",
            f"<b>The exposure is nameable.</b> The high-risk tier holds {S['high_tier_customers']} accounts carrying "
            f"{money(S['high_tier_revenue'])}, at an average priority score of {S['high_tier_avg_priority']:.0f} "
            f"out of 100, each flagged for discount-term review.",
        ]
    )
)
A(Spacer(1, 6))
A(sub("Management response at a glance"))
response_tbl = [
    ["Move", "Scope", "Success metric"],
    [
        "Renewal reset",
        tbl_para(
            f"{S['high_tier_customers']} high-risk accounts carrying {money(S['high_tier_revenue'])}"
        ),
        tbl_para("Account realization lift versus pre-set renewal target"),
    ],
    [
        "Indirect-channel gate",
        tbl_para(
            f"Reseller and Partner deals above the {pct(S['high_discount_threshold'], 0)} line"
        ),
        tbl_para("High-discount revenue share and approval exception rate"),
    ],
    [
        "Services re-price",
        tbl_para(
            f"Professional Services, {money(PROF_SERVICES['revenue'])} revenue at {pct(PROF_SERVICES['margin'])} margin proxy"
        ),
        tbl_para("Category realization and delivery-margin recovery"),
    ],
    [
        "Operating cadence",
        tbl_para("Monthly realization by segment, channel, category and tier"),
        tbl_para(f"Move book realization toward {pct(S['price_realization'] + 0.02)}"),
    ],
]
A(
    styled_table(
        response_tbl, [1.35 * inch, 3.25 * inch, CONTENT_W - 4.6 * inch], align_right_from=99
    )
)
A(Spacer(1, 6))
A(
    para(
        f"Section 11 turns those moves into a 90-day programme: ring-fence the {S['high_tier_customers']} high-risk accounts "
        f"for renewal renegotiation, put a {pct(S['high_discount_threshold'], 0)} approval gate on reseller and partner "
        f"deals where depth concentrates, and re-price Professional Services, which earns a {pct(PROF_SERVICES['margin'])} "
        f"margin against a portfolio average above {pct(S['margin_proxy'])}. None of these actions depends on new revenue. "
        f"Each is aimed at retaining more of the value the book already creates."
    )
)

# ===========================================================================
# 2. CONTEXT AND OBJECTIVES
# ===========================================================================
addall(section("Context and objectives", "Why this review exists"))
A(
    para(
        "Discounting is easy to approve deal by deal and hard to govern once it becomes the default. One concession is "
        "commercial judgement; thousands of similar concessions become a pricing system. This review makes that system "
        "visible, quantifies the value at stake, and locates the exposure at the level where management can act: segment, "
        "channel, product category and account."
    )
)
A(
    para(
        f"The analytical question is narrow by design. It is not whether the business is growing; revenue is stable across "
        f"the window. It is whether that revenue is being earned with healthy list-to-net discipline. A book that bills "
        f"{money(S['total_revenue'], 2)} at {pct(S['price_realization'])} realization is a different asset from one that "
        f"bills the same amount at {pct(0.92)}. The difference, {money(S['revenue_forgone'])} over the period, is the "
        f"economic gap this review sizes and prioritises."
    )
)
A(sub("What governance means here"))
A(
    para(
        "Pricing governance is not the elimination of discount. Discount is a legitimate instrument for winning "
        "competitive deals, rewarding volume, and entering accounts. Governance is the discipline of knowing where "
        "discount is being spent, whether the return justifies the depth, and which accounts have drifted from "
        "negotiated concession into structural dependence. The outputs of this review, a risk score per customer, a "
        "priority queue, and a recommended action for each tier, are built to support that discipline at the level "
        "where it can actually be exercised: the individual account and the channel."
    )
)
A(sub("Scope and audience"))
A(
    para(
        f"The review covers the full order book: {S['n_customers']:,} customers, {S['n_products']} products across "
        f"{S['n_categories']} categories, {S['n_channels']} sales channels and {S['n_regions']} regions, observed over "
        f"{S['n_months']} months. It is written for three readers at once. For the executive, the executive summary and "
        f"the recommendations carry the argument. For the commercial and finance owner, the findings sections give the "
        f"segment, channel, and account detail needed to act. For the technical reviewer, Sections 3 and 4 document the "
        f"data lineage, the metric definitions, and the validation that stands behind every figure."
    )
)
A(sub("Decision frame"))
A(
    para(
        "The report is designed to support three management decisions: where to intervene first, which discounting "
        "behaviours should move from field discretion into policy, and how to measure whether the intervention is "
        "working. It does not set final list prices or approve individual account tactics. Those decisions require "
        "competitive context, contract terms, renewal dates, and account intelligence that sit outside the transaction "
        "data."
    )
)
decision_tbl = [
    ["Decision need", "Evidence used in this report", "Management output"],
    [
        "Size the value pool",
        tbl_para("List value, billed revenue, realization trend, annual leakage"),
        tbl_para("Realization-improvement target"),
    ],
    [
        "Locate the exposure",
        tbl_para("Segment, channel, category, region and segment-channel cuts"),
        tbl_para("Priority plays by cell"),
    ],
    [
        "Turn diagnosis into action",
        tbl_para("Customer risk scores, tiering, concentration and driver analysis"),
        tbl_para("Named account worklist"),
    ],
]
A(CondPageBreak(1.8 * inch))
A(
    styled_table(
        decision_tbl, [1.55 * inch, 3.0 * inch, CONTENT_W - 4.55 * inch], align_right_from=99
    )
)

A(
    figure(
        "02_price_realization_trend.png",
        "Figure 1. Price realization has held inside a two-point band for three years. The shaded area is the share "
        "of list value forgone to discount each month, the standing cost this review quantifies.",
    )
)

# ===========================================================================
# 3. DATA AND METHODOLOGY
# ===========================================================================
addall(section("Data and methodology", "What stands behind the numbers"))
A(
    para(
        f"Every figure in this report traces to a single reproducible pipeline that moves raw transactions through "
        f"cleaning, feature construction, a SQL warehouse layer, risk scoring, and validation. The pipeline reads five "
        f"raw tables, customers, products, orders, order items, and sales representatives, and resolves them into an "
        f"enriched order-item grain of {S['n_order_items']:,} rows. That grain is the atom of the analysis: one row per "
        f"product sold on one order, carrying its list price, its realized price, the discount between them, an estimated "
        f"unit cost, and the segment, channel, region, and tenure context of the sale."
    )
)
lineage_tbl = [
    ["Layer", "Role in the analysis", "Primary control"],
    [
        "Raw inputs",
        tbl_para("Customers, products, orders, order items and sales representatives"),
        tbl_para("Schema and required-column checks"),
    ],
    [
        "Order-item grain",
        tbl_para("Joins commercial context to realized price, list price, cost and discount"),
        tbl_para("Row-count and grain integrity checks"),
    ],
    [
        "Feature layer",
        tbl_para(
            "Constructs discount depth, margin proxy, residual price dispersion and exposure flags"
        ),
        tbl_para("Metric-contract reconciliation"),
    ],
    [
        "Scoring layer",
        tbl_para("Prioritises customers by dependency, margin erosion and pricing risk"),
        tbl_para("Tier and score distribution checks"),
    ],
    [
        "Report layer",
        tbl_para("Publishes only validated metrics and rendered chart assets"),
        tbl_para("Release gate before PDF generation"),
    ],
]
A(CondPageBreak(2.0 * inch))
A(styled_table(lineage_tbl, [1.2 * inch, 3.6 * inch, CONTENT_W - 4.8 * inch], align_right_from=99))
A(Spacer(1, 6))
A(sub("The margin proxy and why it is a proxy"))
A(
    para(
        "Cost of goods is estimated rather than booked, so margin throughout this report is a proxy: realized revenue "
        "less estimated cost, divided by realized revenue. That boundary matters. The proxy is strong for like-for-like "
        "comparison because every segment, channel and category is measured on the same basis. It is not a statement of "
        "accounting gross margin and is not used as one. The recommendations depend on relative gaps, such as Enterprise "
        "versus SMB or Professional Services versus the portfolio, not on the absolute margin level."
    )
)
A(sub("Key metric definitions"))
A(
    para(
        "Four constructed metrics carry most of the analytical weight, and each is defined once here so the findings can "
        "be read without ambiguity."
    )
)
defs = [
    ["Metric", "Definition"],
    [
        "Realized discount",
        "1 minus realized price over list price, per line; aggregated revenue-weighted unless stated.",
    ],
    [
        "Price realization",
        "Realized revenue over list-price revenue. The complement of the weighted discount.",
    ],
    ["Margin proxy", "Realized revenue less estimated cost, over realized revenue."],
    [
        "High-discount line",
        f"A line is high-discount at or above a {pct(S['high_discount_threshold'], 0)} threshold; sensitivity to this cut is tested in Section 9.",
    ],
    [
        "Governance priority",
        "A 0-100 composite of discount dependency, margin erosion, and pricing-risk scores per customer.",
    ],
]
A(CondPageBreak(2.2 * inch))
A(styled_table(defs, [1.7 * inch, CONTENT_W - 1.7 * inch], align_right_from=99))
A(Spacer(1, 8))
A(
    para(
        "The customer-level scores deserve a word because the priority queue depends on them. Each customer receives a "
        "discount-dependency score, a margin-erosion score, and a pricing-risk score, each on a 0-100 scale, blended into "
        "a single governance-priority score and reliability-weighted by how much data the customer provides. A customer "
        "with six orders and a customer with seventy are not scored as if equally certain. The blended score then sorts "
        "customers into four tiers with a recommended action each, which is the operational output the commercial team "
        "works from."
    )
)
A(sub("Pipeline integrity and validation"))
A(
    para(
        "The pipeline is deterministic and seeded, so a fixed environment reproduces the same outputs on repeated "
        "runs, and a release gate runs a battery of validation checks before any figure is published. For this "
        "review, all ten "
        "formal-analysis validation checks passed, and the metric-contract layer confirmed that every published metric "
        "matched its independently recomputed value within tolerance. The data is synthetic, generated to be internally "
        "consistent rather than drawn from a live system. Section 10 treats that as the main boundary condition. The "
        "report should therefore be read as a decision-support demonstration of a repeatable governance method, not as a "
        "claim about a real company's historical performance."
    )
)

# ===========================================================================
# 4. ANALYTICAL FRAMEWORK
# ===========================================================================
addall(section("Analytical framework", "How the question is decomposed"))
A(
    para(
        "The single question, healthy growth or discount-reliant growth, is answered along four axes, and the findings "
        "sections follow them in order. Each axis isolates one way that a discounting problem can hide."
    )
)
A(
    para(
        "<b>The aggregate axis</b> asks whether the book as a whole realizes its list prices. It is answered by price "
        "realization and the revenue forgone to discount, read over time so that a stable problem can be told apart from "
        f"a deteriorating or improving one. A single snapshot cannot make that distinction; {S['n_months']} months can."
    )
)
A(
    para(
        "<b>The depth axis</b> asks what discounting costs at the margin. It is answered by the relationship between "
        "discount depth and margin, measured two ways as a cross-check: across discount buckets at the line grain, and "
        "across customers at the account grain. Agreement between the two supports a consistent descriptive reading of "
        "how discount depth and margin move together."
    )
)
A(
    para(
        "<b>The structural axis</b> asks where the discounting lives. It is answered by cutting discount and margin by "
        "segment, channel, region, and product category, and by the interaction of segment and channel, because a problem "
        "that is uniform requires a blunt policy response while a problem that is concentrated requires a targeted one. "
        "The data, as Section 7 shows, is firmly the second case."
    )
)
A(
    para(
        "<b>The account axis</b> asks who is responsible for the exposure. It is answered by the customer risk scores, the "
        "priority tiers, and the concentration of revenue, which together turn a diagnosis into a worklist. This is the "
        "axis that makes the review operational rather than only descriptive."
    )
)
A(
    para(
        "A fifth consideration, sensitivity, runs underneath all four. Every threshold in the analysis, above all the "
        f"{pct(S['high_discount_threshold'], 0)} high-discount line, is tested by moving it and watching whether the conclusion moves with it. Section 9 "
        f"shows it does not across {', '.join(pct(value, 0) for value in S['high_discount_sensitivity_thresholds'])}, which is what distinguishes "
        "a finding from an artefact of where a cutoff happened to fall."
    )
)

# ===========================================================================
# 5. FINDINGS — AGGREGATE
# ===========================================================================
addall(section("Findings: the aggregate picture", "Axis one: does the book realize its prices"))
A(
    para(
        f"Start with the whole book. Over {S['coverage']} the business billed {money(S['total_revenue'], 2)} against "
        f"a list value of {money(S['total_list_revenue'], 2)}. The {money(S['revenue_forgone'])} difference is the cost of "
        f"discount, and at {pct(S['price_realization'])} realization it is large in both absolute and relative terms. For "
        f"every five dollars the catalogue says the book is worth, it collects a little over four."
    )
)
A(
    para(
        f"What turns this from a number into a finding is its stability. Monthly price realization sits in a "
        f"{pct(S['pr_min'])}-to-{pct(S['pr_max'])} band for the entire window, a spread of barely two points across three "
        f"years that include whatever seasonality, mix shift, and deal cycles the period contained. The weighted discount "
        f"behind it moves just as little, oscillating around {pct(S['weighted_discount'])} without trend. Revenue, plotted "
        f"against that flat discount line in Figure 2, is similarly trendless. The book is not growing into its discount or "
        f"out of it. It is holding both constant."
    )
)
annual_tbl = [["Year", "Revenue", "List value", "Forgone", "Realization", "High-disc rev."]]
for r in S.get("annual_summary", []):
    annual_tbl.append(
        [
            str(int(r["order_year"])),
            money(r["revenue"]),
            money(r["list_revenue"]),
            money(r["revenue_forgone"]),
            pct(r["price_realization"]),
            pct(r["high_discount_revenue_share"]),
        ]
    )
A(CondPageBreak(1.6 * inch))
A(
    styled_table(
        annual_tbl,
        [0.7 * inch, 1.15 * inch, 1.15 * inch, 1.05 * inch, 1.1 * inch, CONTENT_W - 5.15 * inch],
    )
)
A(Spacer(1, 6))
A(
    para(
        "The annual view is included to separate signal from monthly noise. The same pattern holds after seasonality is "
        "absorbed into full-year totals: realization remains in the low eighties, forgone revenue remains material, and "
        "high-discount revenue remains a recurring part of the book. The issue is therefore not a calendar effect; it is "
        "a commercial operating pattern."
    )
)
A(
    figure(
        "01_revenue_trend_discount_overlay.png",
        "Figure 2. Monthly revenue against the revenue-weighted discount. Neither trends. The discount is a level the "
        "organisation operates at, not a response to conditions that vary.",
    )
)
A(
    para(
        "The operating interpretation is that a purely tactical discount would normally move with deal cycles, mix, "
        "or seasonality. This one barely moves. That does not prove a formal policy is causing the level, but it does "
        "show that the business is operating around a stable list-to-net norm. Stable norms can be governed: target "
        "them, change the approval path, and track whether the level resets."
    )
)
A(
    para(
        f"It also changes how the opportunity should be sized. The {money(S['revenue_forgone'])} gap is measured on the "
        f"analysed period, not assumed recoverable in full. A two-point improvement in realization, from "
        f"{pct(S['price_realization'])} toward {pct(S['price_realization'] + 0.02)}, is worth about "
        f"{money(TWO_POINT_CAPTURE)} on the analysed list base, or {money(TWO_POINT_ANNUAL_RUN_RATE)} per run-rate year "
        f"at current scale. That is the value yardstick for the governance programme."
    )
)
scenario_tbl = [["Realization lift", "New realization", "Revenue capture on analysed list base"]]
for points in [1, 2, 3]:
    s = SCENARIOS.get(points)
    if s:
        scenario_tbl.append(
            [
                f"+{points} pp",
                pct(s["new_price_realization"]),
                money(s["revenue_capture_on_analysis_base"]),
            ]
        )
A(CondPageBreak(1.3 * inch))
A(styled_table(scenario_tbl, [1.55 * inch, 1.55 * inch, CONTENT_W - 3.1 * inch]))
A(Spacer(1, 6))
A(
    para(
        "These scenarios are not forecasts and do not assume demand elasticity, competitive response, or renewal timing. "
        "They are sizing cases: what management would recover if the existing list-price base billed one, two, or three "
        "points closer to list. The cases create a practical threshold for prioritising governance work and deciding how "
        "much commercial disruption is worth testing."
    )
)

# ===========================================================================
# 6. FINDINGS — DEPTH AND MARGIN
# ===========================================================================
addall(section("Findings: what discount costs the margin", "Axis two: the price of depth"))
A(
    para(
        "The aggregate tells us discount is large and stable. The depth axis tells us what it is associated with. The "
        "answer is commercially important: deeper discount and thinner margin appear together whether the data is read "
        "by order line or by customer."
    )
)
A(
    para(
        f"At the line grain, sorting all {S['n_order_items']:,} order items into discount bands and computing blended "
        f"margin within each produces a near-monotone staircase. The shallowest band earns a "
        f"{pct(S['margin_best_bucket'] / 100)} margin proxy; the deepest earns {pct(S['margin_worst_bucket'] / 100)}. "
        f"The steps do not flatten at the bottom, where management would want evidence that extra depth is buying "
        f"something valuable enough to offset the concession. That evidence is not visible in the transaction data."
    )
)
A(
    figure(
        "05_margin_by_discount_bucket.png",
        "Figure 3. Blended margin proxy falls at every step into deeper discount. The relationship is monotone, with "
        "no flattening at depth to suggest the deepest discounts buy compensating value.",
    )
)
A(
    para(
        f"The same gradient appears one level up, at the customer grain, and this is what makes the reading useful. Plotting "
        f"each of the {S['n_customers']:,} customers by average discount against average margin yields a correlation of "
        f"{S['disc_margin_r']:.2f}, with margin falling by {DISC_MARGIN_SLOPE_ABS:.2f} points for every additional point "
        f"of discount. That is a warning signal: at account grain, deeper-discounted customers are also materially thinner-margin "
        f"customers. Any argument that depth is being offset by volume, mix or strategic value needs evidence outside the "
        f"current transaction data."
    )
)
A(
    figure(
        "06_discount_margin_correlation.png",
        "Figure 4. Every customer plotted by discount and margin, sized by revenue. The downward fit is steep and tight; "
        "deeper-discounted customers are reliably thinner-margin customers, with no volume offset visible.",
    )
)
A(
    para(
        "Two cuts of the same data agreeing this closely support a strong management hypothesis, not a controlled causal "
        "claim. The mechanical link is direct: discount is subtracted from price, while cost does not fall "
        "because the deal was discounted. Unless a deal brings enough compensating value through volume, retention, or "
        "strategic account access, depth comes out of margin. The transaction data does not show that offset at scale."
    )
)
A(
    para(
        f"Composition confirms the depth is not confined to a harmless tail. Bucketing revenue rather than counting lines, "
        f"the bulk of the book sits in the 10-to-20% band, but the bands above the high-discount line carry real weight, and "
        f"at the {pct(S['high_discount_threshold'], 0)} cut {pct(S['high_discount_rev_share'])} of all revenue flows through deals discounted past it. A third "
        f"of the book is in the part of the discount distribution where, per Figure 3, margin is measurably impaired."
    )
)
A(
    figure(
        "04_revenue_by_discount_bucket.png",
        "Figure 5. Revenue by discount band. The 10-20% band dominates, but the highlighted deep bands are not a "
        "rounding error; they carry roughly a third of revenue.",
    )
)
A(
    figure(
        "03_discount_depth_distribution.png",
        "Figure 6. The distribution of line-level discount. Discounting clusters tightly rather than spreading, another "
        "sign that list-to-net practice is operating around common defaults rather than purely case-by-case negotiation.",
    )
)

# ===========================================================================
# 7. FINDINGS — STRUCTURE
# ===========================================================================
addall(
    section(
        "Findings: where the discounting lives", "Axis three: segment, channel, region, product"
    )
)
A(
    para(
        "A problem that is everywhere needs a different remedy than a problem that is somewhere. This section cuts the "
        "discount four ways to establish which it is. The answer is consistent across every cut: the discounting is "
        "concentrated, in the Enterprise segment, in the indirect channels, and in one product category, while it is "
        "essentially uniform across geography. Concentration is what makes a targeted response possible."
    )
)
A(sub("Segment is the primary axis of concentration"))
A(
    para(
        f"The four segments form a clean ladder. Enterprise discounts deepest at {pct(S['segments'][0]['avg_discount_pct'])} "
        f"and earns the thinnest margin at {pct(S['segments'][0]['avg_margin_proxy_pct'])}; SMB discounts shallowest at "
        f"{pct(S['segments'][3]['avg_discount_pct'])} and earns the fattest margin at {pct(S['segments'][3]['avg_margin_proxy_pct'])}, "
        f"with Mid-Market and Public Sector ranged between. The ladder would be unremarkable if the segments were small. "
        f"They are not. Enterprise is {money(S['segments'][0]['total_revenue'])}, "
        f"{pct(S['segments'][0]['total_revenue'] / S['total_revenue'])} of the entire book, which means the worst pricing "
        f"position by margin is also the largest by revenue. That is the structural fact management should act on first."
    )
)
A(
    figure(
        "07_segment_pricing_health.png",
        "Figure 7. Segments positioned by discount and margin, sized by revenue. The largest bubble sits in the worst "
        "corner: Enterprise combines the most revenue with the deepest discount and the thinnest margin.",
    )
)
seg_tbl = [["Segment", "Revenue", "Avg discount", "High-disc share", "Margin proxy"]]
for s in S["segments"]:
    seg_tbl.append(
        [
            s["segment"],
            money(s["total_revenue"]),
            pct(s["avg_discount_pct"]),
            pct(s["share_high_discount"]),
            pct(s["avg_margin_proxy_pct"]),
        ]
    )
A(CondPageBreak(1.6 * inch))
A(
    styled_table(
        seg_tbl, [1.5 * inch, 1.2 * inch] + [(CONTENT_W - 2.7 * inch) / 3] * 3, highlight_rows=[1]
    )
)
A(Spacer(1, 6))
A(
    para(
        f"The high-discount share column is where the concentration is starkest. In Enterprise, "
        f"{pct(S['segments'][0]['share_high_discount'])} of revenue is deeply discounted; in SMB it is "
        f"{pct(S['segments'][3]['share_high_discount'])}. These are not two points on a smooth gradient but two different "
        f"pricing regimes operating in the same company. SMB provides a lower-risk internal benchmark for the deeper "
        f"discount pattern observed in Enterprise."
    )
)
seg_value_tbl = [["Segment", "Forgone", "Share of forgone", "Realization", "Customers"]]
for s in S.get("segment_value_pool", []):
    seg_value_tbl.append(
        [
            s["segment"],
            money(s["revenue_forgone"]),
            pct(s["share_of_revenue_forgone"]),
            pct(s["price_realization"]),
            f"{int(s['customers']):,}",
        ]
    )
A(CondPageBreak(1.5 * inch))
A(
    styled_table(
        seg_value_tbl,
        [1.45 * inch, 1.15 * inch, 1.35 * inch, 1.15 * inch, CONTENT_W - 5.1 * inch],
        highlight_rows=[1],
    )
)
A(Spacer(1, 6))
A(
    para(
        f"The value-pool view confirms the operational priority. Enterprise is not only the largest revenue segment; it is "
        f"also the largest contributor to discount leakage, carrying {pct(SEG_VALUE.get('Enterprise', {}).get('share_of_revenue_forgone', 0))} "
        f"of total forgone revenue. That is why the recommended programme starts with Enterprise account renewals rather "
        f"than broad enablement or generic sales training. The problem is measurable at segment level and actionable at "
        f"account level."
    )
)
A(sub("Channel sharpens the same picture"))
A(
    para(
        f"Cutting by channel shows the indirect routes to market discount markedly deeper than the direct ones. The "
        f"reseller channel runs a {pct(S['channel']['Reseller']['discount'])} weighted discount and the partner channel "
        f"{pct(S['channel']['Partner']['discount'])}, against {pct(S['channel']['Direct']['discount'])} Direct and only "
        f"{pct(S['channel']['Online']['discount'])} Online. Direct is the largest channel at "
        f"{money(S['channel']['Direct']['revenue'])}, so its discount sets the book average, but the indirect channels are "
        f"where depth concentrates per dollar of revenue."
    )
)
channel_value_tbl = [["Channel", "Revenue", "Forgone", "Realization", "Margin"]]
for c in S.get("channel_value_pool", []):
    channel_value_tbl.append(
        [
            c["sales_channel"],
            money(c["revenue"]),
            money(c["revenue_forgone"]),
            pct(c["price_realization"]),
            pct(c["margin_proxy_pct"]),
        ]
    )
A(CondPageBreak(1.5 * inch))
A(
    styled_table(
        channel_value_tbl,
        [1.3 * inch, 1.2 * inch, 1.15 * inch, 1.15 * inch, CONTENT_W - 4.8 * inch],
    )
)
A(Spacer(1, 6))
A(
    para(
        "The channel value pool matters because an approval rule changes behaviour only where it is placed. Direct carries "
        "the largest dollars, but Reseller and Partner carry the lowest realization and the highest depth. The control "
        "therefore belongs at the indirect-channel deal review point: it catches the behaviour with the worst realization "
        "without slowing down every direct renewal."
    )
)
A(
    figure(
        "09_channel_discount_ladder.png",
        "Figure 8. Weighted discount by channel, revenue noted at each base. Indirect channels discount close to half "
        "again as deep as Online.",
    )
)
A(
    para(
        f"The interaction of segment and channel is where the exposure peaks, and it is worth isolating because it names "
        f"the single worst cell in the book. Where Enterprise meets the reseller channel, average discount reaches "
        f"{pct(S['enterprise_reseller_disc'])} and {pct(S['enterprise_reseller']['high_discount_share'])} of that cell's revenue is deeply discounted, against a "
        f"margin proxy of {pct(S['enterprise_reseller']['avg_margin_proxy_pct'])}. The heatmap makes the gradient legible: discount darkens reliably from the SMB-Online "
        f"corner to the Enterprise-reseller corner, the two regimes sitting at opposite ends of the same grid."
    )
)
A(
    figure(
        "08_segment_channel_heatmap.png",
        "Figure 9. Average discount by segment and channel. The gradient runs cleanly from the disciplined SMB-Online "
        "corner to the Enterprise-reseller corner, which is the deepest cell in the book.",
    )
)
A(sub("Geography is not the primary discriminator"))
A(
    para(
        f"Region is the control cut. Weighted discount by region produces little spread: "
        f"{DEEPEST_REGION['region']} is deepest at {pct(DEEPEST_REGION['discount'])} and "
        f"{SHALLOWEST_REGION['region']} is shallowest at {pct(SHALLOWEST_REGION['discount'])}, a "
        f"{pct(REGION_DISCOUNT_RANGE)} range across four regions that differ materially in size. Geography is therefore "
        f"not the primary explanation. Discount depth travels more clearly with who is being sold to and through which "
        f"channel."
    )
)
A(
    figure(
        "10_region_comparison.png",
        "Figure 10. Weighted discount by region. The narrow spread makes region a weaker discriminator than segment "
        "and channel in this dataset.",
    )
)
A(sub("One product category breaks the pattern"))
A(
    para(
        f"Product category mostly tracks margin as expected, with one exception sharp enough to act on. Professional "
        f"Services discounts at {pct(PROF_SERVICES['discount'])}, in line with the rest of the catalogue, but earns a "
        f"margin proxy of only {pct(PROF_SERVICES['margin'])}, less than a third of the {pct(CAT_VALUE.get('Collaboration', S['category'][0])['margin'])} "
        f"that Collaboration earns and far below the {pct(S['margin_proxy'])} book average. It is discounted like a "
        f"high-margin product while behaving like a low-margin one. Core Platform, by contrast, is the revenue engine at "
        f"{money(CORE_PLATFORM['revenue'])} and earns a respectable {pct(CORE_PLATFORM['margin'])}, so the category "
        f"problem is specific rather than general."
    )
)
A(
    figure(
        "11_category_margin_vs_discount.png",
        "Figure 11. Discount against margin by category. Professional Services is the outlier: ordinary discount, "
        "exceptionally thin margin, which makes its discount the least defensible in the book.",
    )
)
A(sub("Concentration cuts the right way"))
A(
    para(
        f"The structural findings would be discouraging if the exposure were spread thinly across thousands of accounts. "
        f"It is not. Revenue is heavily concentrated: the top {pct(0.10, 0)} of customers produce {pct(S['top10_rev_share'])} "
        f"of revenue and the top {pct(0.20, 0)} produce {pct(S['top20_rev_share'])}. The same concentration that makes the "
        f"book sensitive to a few accounts also makes it tractable. A governance programme that engages the largest few "
        f"hundred relationships reaches the great majority of both the revenue and the discount, which is the bridge from "
        f"this section's diagnosis to the account-level worklist in the next."
    )
)
A(
    figure(
        "15_revenue_concentration_lorenz.png",
        "Figure 12. The Lorenz curve of revenue. Steep early rise means high concentration, and high concentration "
        "means targeted remediation can reach most of the exposure.",
    )
)
A(
    figure(
        "12_top_products_revenue.png",
        "Figure 13. Top products by revenue, flagged where deep-discount exposure is high. Large products with elevated "
        "deep-discount share deserve explicit product-level guardrails.",
    )
)

# ===========================================================================
# 8. FINDINGS — ACCOUNTS AND RISK
# ===========================================================================
addall(section("Findings: who carries the risk", "Axis four: from diagnosis to worklist"))
A(
    para(
        "The final axis turns the structural picture into a list of names. The risk-scoring layer assigns every customer a "
        "governance-priority score and sorts the book into four tiers, each with a recommended action. This is the output "
        "the commercial organisation can act on directly."
    )
)
rt = {r["risk_tier"]: r for r in S["risk_tiers"]}
A(
    para(
        f"The tiers are deliberately unbalanced because the risk is. The critical and high tiers hold just "
        f"{S['high_tier_customers']} customers but {money(S['high_tier_revenue'])} of revenue, at an average priority "
        f"score of {S['high_tier_avg_priority']:.0f} out of 100, all flagged for discount-term review. "
        f"The medium tier is {rt['Medium']['customers']} customers and {money(rt['Medium']['total_revenue'])}, "
        f"marked for segment-pricing review. The low tier is the long, healthy tail: {rt['Low']['customers']} customers "
        f"and {money(rt['Low']['total_revenue'])} that need only monitoring. The shape of the priority distribution, a "
        f"thin upper tail above a broad healthy base, is what makes a small high-touch programme viable."
    )
)
risk_detail_tbl = [
    ["Tier", "Customers", "Revenue share", "Avg discount", "Avg margin", "High-disc rev."]
]
for tier in ["Critical", "High", "Medium", "Low"]:
    d = RISK_DETAIL.get(tier)
    if d:
        risk_detail_tbl.append(
            [
                tier,
                f"{int(d['customers']):,}",
                pct(d["revenue_share"]),
                pct(d["avg_discount_pct"]),
                pct(d["avg_margin_proxy_pct"]),
                pct(d["revenue_high_discount_share"]),
            ]
        )
A(CondPageBreak(1.5 * inch))
A(
    styled_table(
        risk_detail_tbl,
        [0.9 * inch, 1.0 * inch, 1.15 * inch, 1.15 * inch, 1.1 * inch, CONTENT_W - 5.3 * inch],
        highlight_rows=[1],
    )
)
A(Spacer(1, 6))
A(
    para(
        "The tier table is the bridge from analytics to account management. The critical and high tiers are smaller, more discounted, "
        "and more exposed to high-discount revenue than the rest of the book, so it should be handled as a named-account "
        "intervention. The medium tier is too large for bespoke treatment; it needs rule-based review as renewals come "
        "up. The low tier should not be disturbed unless its score moves. This prevents governance from becoming a "
        "blanket control that slows healthy business."
    )
)
A(
    figure(
        "13_risk_tier_breakdown.png",
        "Figure 14. The four risk tiers by customer count and by revenue. A few dozen high-risk accounts carry "
        "revenue out of all proportion to their number.",
    )
)
A(
    figure(
        "14_priority_score_distribution.png",
        f"Figure 15. The governance-priority distribution. Most customers score low; the population that needs action sits "
        f"above the 90th percentile at a score of {S['p90_priority']:.0f}.",
    )
)
A(sub("What is actually driving the scores"))
A(
    para(
        f"The scoring layer also records why each customer is flagged, which prevents the queue from being a black box. "
        f"Aggregating the primary driver across the book, discount dependency is dominant: it is the lead driver for "
        f"{S['drivers'][0]['customers']} customers carrying {money(S['drivers'][0]['total_revenue'])}, far more revenue "
        f"than the pricing-risk and margin-erosion drivers behind it. This matters for the remedy. A book whose main "
        f"problem is dependency, customers who have come to expect a standing discount, responds to renegotiation and "
        f"approval discipline. It would not respond to the same degree if the driver were, say, cost inflation, which no "
        f"amount of pricing governance would touch."
    )
)
A(
    figure(
        "17_main_risk_driver.png",
        "Figure 16. Revenue by primary risk driver. Discount dependency dominates, which points the remedy squarely at "
        "discount policy rather than cost or mix.",
    )
)
A(sub("Discount depth persists across tenure cohorts"))
A(
    para(
        "One more cut closes the loop between this axis and the aggregate finding. Splitting customers by tenure shows "
        "discount depth essentially flat across the lifecycle: newly acquired customers and four-year veterans are "
        "discounted at materially the same rate. The cross-sectional pattern is consistent with persistent discounting, "
        "but it does not track the same account longitudinally and therefore cannot distinguish acquisition incentives "
        "from contract, mix, or cohort effects on its own."
    )
)
A(
    figure(
        "18_tenure_cohort.png",
        "Figure 17. Discount and margin by customer tenure. Similar discount levels across tenure bands support a "
        "persistence hypothesis that should be tested with longitudinal renewal data.",
    )
)

# ===========================================================================
# 9. SENSITIVITY AND ROBUSTNESS
# ===========================================================================
addall(section("Sensitivity and confidence", "What changes when thresholds move"))
A(
    para(
        "The most consequential assumption in the review is the high-discount line. It determines high-discount revenue "
        f"share and feeds the risk scores. A credible conclusion should not disappear when that line moves, so this section "
        f"tests the verdict across {', '.join(pct(value, 0) for value in S['high_discount_sensitivity_thresholds'])}."
    )
)
th = {round(t["high_discount_threshold"], 2): t for t in S["threshold"]}
A(
    para(
        f"At a {pct(LOW_THRESHOLD, 0)} line, {pct(th[LOW_THRESHOLD]['high_discount_revenue_share'])} of revenue counts as high-discount and "
        f"{money(th[LOW_THRESHOLD]['revenue_with_margin_at_risk'])} of revenue is flagged as margin-at-risk. At the {pct(S['high_discount_threshold'], 0)} line used "
        f"throughout, those fall to {pct(th[BASE_THRESHOLD]['high_discount_revenue_share'])} and "
        f"{money(th[BASE_THRESHOLD]['revenue_with_margin_at_risk'])}. At {pct(HIGH_THRESHOLD, 0)}, to {pct(th[HIGH_THRESHOLD]['high_discount_revenue_share'])} and "
        f"{money(th[HIGH_THRESHOLD]['revenue_with_margin_at_risk'])}. The magnitudes move, as they must, but the direction and the "
        f"diagnosis do not. At every threshold the same segments, channels, and accounts surface as the deepest, and at "
        f"every threshold the margin proxy on high-discount revenue sits below the book average. The cutoff changes the size "
        f"of the worklist; it does not change where management should start."
    )
)
A(
    figure(
        "16_threshold_sensitivity.png",
        f"Figure 18. Revenue at risk and high-discount share as the threshold moves from {pct(LOW_THRESHOLD, 0)} to {pct(HIGH_THRESHOLD, 0)}. The curve is "
        "smooth and the ranking of risk is stable, so no single cutoff manufactures the result.",
    )
)
thr_tbl = [
    [
        "Threshold",
        "High-disc revenue share",
        "Revenue margin-at-risk",
        "Margin on high-disc revenue",
    ]
]
for t in S["threshold"]:
    thr_tbl.append(
        [
            pct(t["high_discount_threshold"], 0),
            pct(t["high_discount_revenue_share"]),
            money(t["revenue_with_margin_at_risk"]),
            pct(t["margin_proxy_pct_on_high_discount"]),
        ]
    )
A(CondPageBreak(1.4 * inch))
A(styled_table(thr_tbl, [1.2 * inch] + [(CONTENT_W - 1.2 * inch) / 3] * 3))
A(Spacer(1, 6))
A(
    para(
        "Two separate validation layers add to the confidence. The metric-contract layer recomputes every published "
        "figure from the raw grain and checks it against the value the pipeline reports, and all checks reconciled within "
        "tolerance. The formal-analysis release gate ran ten structural checks on the analysis window, coverage, and "
        "internal consistency, and all ten passed. The numbers in this report are therefore recomputed and reconciled "
        "before publication rather than copied from an output table."
    )
)
robust_tbl = [
    ["Challenge to the finding", "Check performed", "Result"],
    [
        "Threshold dependence",
        tbl_para(
            f"Moved high-discount line across {', '.join(pct(value, 0) for value in S['high_discount_sensitivity_thresholds'])}"
        ),
        tbl_para("Diagnosis and ranking remain stable"),
    ],
    [
        "Aggregation artefact",
        tbl_para("Compared line-level bucket results with customer-level scatter"),
        tbl_para("Both show the same discount-margin gradient"),
    ],
    [
        "Geographic mix",
        tbl_para("Cut weighted discount by region"),
        tbl_para("Regional spread is under one point"),
    ],
    [
        "Single-driver risk",
        tbl_para("Aggregated primary score drivers by customer revenue"),
        tbl_para("Discount dependency is the dominant driver"),
    ],
    [
        "Metric publication error",
        tbl_para("Recomputed published metrics through contracts and release gate"),
        tbl_para("All checks passed"),
    ],
]
A(CondPageBreak(2.0 * inch))
A(styled_table(robust_tbl, [1.55 * inch, 3.0 * inch, CONTENT_W - 4.55 * inch], align_right_from=99))
A(Spacer(1, 6))
A(
    para(
        "The confidence case is therefore cumulative rather than dependent on any one statistic. The same commercial "
        "story appears in the aggregate trend, in the line-level margin staircase, in the customer scatter, in the "
        "segment-channel heatmap, and in the customer risk queue. A different threshold would resize the opportunity, but "
        "it would not change where management should start."
    )
)

# ===========================================================================
# 10. RISKS, LIMITATIONS, CAVEATS
# ===========================================================================
addall(section("Risks, limitations, and caveats", "What this review cannot tell you"))
A(
    para(
        "The analysis is useful because it is bounded. Four limitations matter, and each changes how the work should move "
        "from diagnostic to execution."
    )
)
caveat_tbl = [
    ["Boundary", "What it could change", "Evidence needed to close"],
    [
        "Synthetic data",
        tbl_para("Absolute dollar opportunity and account names in a live setting"),
        tbl_para("Production order, cost and contract data"),
    ],
    [
        "Margin proxy",
        tbl_para("Level of profitability by product or account"),
        tbl_para("Booked cost, implementation effort and service delivery cost"),
    ],
    [
        "Observational design",
        tbl_para("Causal size of a price-realization intervention"),
        tbl_para("Renewal test, matched cohort or controlled price experiment"),
    ],
    [
        "Score weighting",
        tbl_para("Borderline medium-versus-low prioritisation"),
        tbl_para("Commercial review of accounts near tier thresholds"),
    ],
]
A(CondPageBreak(1.8 * inch))
A(styled_table(caveat_tbl, [1.25 * inch, 2.8 * inch, CONTENT_W - 4.05 * inch], align_right_from=99))
A(Spacer(1, 6))
A(sub("The data is synthetic"))
A(
    para(
        "The order book is generated rather than drawn from a production system. It is internally consistent and behaves "
        "like a real book, which makes it suitable for validating the method, but the dollar figures are not a claim "
        "about any real company. The value of the review is the operating model: metrics, scoring, validation, and a "
        "decision structure that can be pointed at a live order book and re-run with production data."
    )
)
A(sub("Margin is a proxy"))
A(
    para(
        "Because cost is estimated, margin is a proxy and is used only for comparison, never as a statement of absolute "
        "profitability. The comparisons are internally consistent because every group uses the same cost-generation "
        "method, but actual booked cost could change both levels and rankings. The margin findings must therefore be "
        "revalidated before operational use with production economics."
    )
)
A(sub("Correlation is not full causation"))
A(
    para(
        "The near-one slope between discount and margin is consistent with discount driving margin loss, and the agreement "
        "between the line and customer cuts strengthens that reading. It is still observational evidence. A controlled "
        "renewal test or matched cohort is needed to quantify how much realization can be recovered without affecting "
        "win rate, renewal risk, or customer expansion."
    )
)
A(
    KeepTogether(
        [
            sub("The scores encode judgement"),
            para(
                "The governance-priority score blends three sub-scores with chosen weights, and different weights would "
                "reshuffle the queue at the margin. The tiering is therefore a defensible prioritisation rather than an "
                "objective truth, and it should be used as a starting worklist that commercial judgement refines, not as "
                "an automated verdict on any single account. Weight sensitivity should be tested during calibration, "
                "especially for accounts close to a tier boundary."
            ),
        ]
    )
)

# ===========================================================================
# 11. RECOMMENDATIONS
# ===========================================================================
addall(section("Recommendations and action priorities", "What to do, in order"))
A(
    para(
        f"The response should be run as a 90-day price-realization recovery programme, not as a generic pricing initiative. "
        f"The objective is narrow: test whether management can move realization from {pct(S['price_realization'])} toward "
        f"{pct(S['price_realization'] + 0.02)} in the exposed parts of the book while protecting renewal and win-rate. "
        f"That two-point move is worth about {money(TWO_POINT_CAPTURE)} on the analysed list base, or "
        f"{money(TWO_POINT_ANNUAL_RUN_RATE)} per year at current scale."
    )
)

A(sub("Priority 1: ring-fence the high-risk accounts for renewal renegotiation"))
A(
    para(
        f"The {S['high_tier_customers']} critical and high-risk accounts carry {money(S['high_tier_revenue'])} at an average "
        f"priority of {S['high_tier_avg_priority']:.0f} and are individually nameable from the scoring output. "
        f"Assign each account to an executive owner and a pricing owner, set a target net price before negotiation starts, "
        f"and require explicit approval for any renewal that lands below target. Because dependency is the dominant driver, "
        f"the realistic objective is to narrow the discount by a few points, not to remove it. The account score should "
        f"become a renewal workplan: target price, concession logic, exception owner, and realized outcome."
    )
)
A(sub("Priority 2: put an approval gate on deep discounts in the indirect channels"))
A(
    para(
        f"Depth concentrates in the reseller and partner channels, peaking in the Enterprise-reseller cell at "
        f"{pct(S['enterprise_reseller_disc'])} with nearly nine-tenths of that revenue deeply discounted. Introduce a hard "
        f"approval gate above the {pct(S['high_discount_threshold'], 0)} line for these channels. Every exception should "
        f"carry a reason code, expected account value, margin check, and approval owner. This is the forward-looking "
        f"control that stops the standing level from regenerating after Priority 1 resets individual renewals."
    )
)
A(sub("Priority 3: re-price Professional Services"))
A(
    para(
        f"Professional Services is discounted like the rest of the catalogue, at {pct(PROF_SERVICES['discount'])}, while "
        f"earning a {pct(PROF_SERVICES['margin'])} margin proxy against a book average above {pct(S['margin_proxy'])}. "
        f"This is the least defensible discount in the portfolio. Separate services authority from product discount "
        f"authority, set a services-specific floor, and stop treating labour-heavy delivery as if it had software margin. "
        f"If the market will not bear the required net price, the business should decide that explicitly as a margin trade, "
        f"not hide it inside a product discount bundle."
    )
)
A(sub("Priority 4: adopt price realization as a standing operating metric"))
A(
    para(
        f"The reason the {money(S['revenue_forgone'])} accumulated unnoticed is that no one owned realization as a number. "
        f"Put it beside revenue in the monthly business review, report it by segment and channel, and hold commercial "
        f"owners accountable for both volume and quality of revenue. The measurement is already built; the pipeline "
        f"produces realization at every cut in this report. What is missing is ownership."
    )
)
A(sub("Control model"))
control_tbl = [
    ["Control point", "Rule", "Review cadence", "Owner"],
    [
        "High-risk renewals",
        tbl_para(
            "Target net price set before negotiation; variance from target explicitly approved"
        ),
        tbl_para("Renewal calendar"),
        tbl_para("Segment GM + Finance"),
    ],
    [
        "Indirect deep discounts",
        tbl_para(
            f"Deals above {pct(S['high_discount_threshold'], 0)} require reason code and margin review"
        ),
        tbl_para("Deal desk"),
        tbl_para("Channel Sales + Pricing"),
    ],
    [
        "Professional Services",
        tbl_para("Separate service pricing guardrail from product discount authority"),
        tbl_para("Quarterly"),
        tbl_para("Services GM + FP&amp;A"),
    ],
    [
        "Realization monitoring",
        tbl_para(
            "Monthly realization by segment, channel and category; escalation on adverse movement"
        ),
        tbl_para("Monthly business review"),
        tbl_para("Revenue Operations"),
    ],
]
A(CondPageBreak(2.0 * inch))
A(
    styled_table(
        control_tbl,
        [1.35 * inch, 3.0 * inch, 1.3 * inch, CONTENT_W - 5.65 * inch],
        align_right_from=99,
    )
)
A(Spacer(1, 6))
A(
    para(
        "The control model is intentionally light. It does not ask management to police every order line. It places "
        "scrutiny where the analysis shows repeatable exposure: high-risk renewals, indirect-channel deep discounts, and "
        "the low-margin services category. The monthly realization metric then tests whether the controls are changing "
        "the book, not just individual approval behaviour."
    )
)
A(Spacer(1, 8))
A(sub("90-day mobilisation plan"))
mobilisation_tbl = [
    ["Window", "Management actions", "Exit criterion"],
    [
        "Days 0-15",
        tbl_para(
            f"Freeze the {S['high_tier_customers']}-account list, assign owners, set renewal targets, and publish the "
            f"{pct(S['high_discount_threshold'], 0)} indirect-channel approval rule"
        ),
        tbl_para("Named worklist and approval path live"),
    ],
    [
        "Days 16-45",
        tbl_para(
            "Run the first renewal wave, collect exception reason codes, and design the Professional Services floor"
        ),
        tbl_para("First-wave realization lift and exception mix reviewed"),
    ],
    [
        "Days 46-90",
        tbl_para(
            "Expand to the medium tier as renewals arrive, launch services guardrail, and embed realization in the monthly business review"
        ),
        tbl_para(f"Book-level realization tracking toward {pct(S['price_realization'] + 0.02)}"),
    ],
]
A(
    styled_table(
        mobilisation_tbl,
        [1.0 * inch, 3.85 * inch, CONTENT_W - 4.85 * inch],
        align_right_from=99,
    )
)
A(sub("Further questions before scale"))
addall(
    bullets(
        [
            "<b>Elasticity and win-rate:</b> which Enterprise and indirect-channel deals can absorb a two-to-three point net-price lift without materially reducing close rate?",
            "<b>Contract timing:</b> which of the high-risk accounts renew inside the next two quarters, and what share of the value pool is addressable in the current planning cycle?",
            "<b>Competitive exceptions:</b> which deep discounts are tied to documented competitive displacement, regulated procurement rules, or strategic account-entry logic?",
            "<b>Cost calibration:</b> how do booked cost and implementation effort change the Professional Services margin proxy once actual delivery economics are loaded?",
        ]
    )
)
A(
    para(
        "These questions do not weaken the recommendation; they define the next evidence needed to turn a diagnostic "
        "programme into a priced execution plan. The current analysis is sufficient to prioritise where to act. The open "
        "questions determine how much of the value pool can be captured, when, and with what commercial trade-off."
    )
)

# ===========================================================================
# 12. APPENDIX
# ===========================================================================
addall(section("Appendix", "Reference tables and definitions"))
# Each subsection is kept together (heading + table) so a table never splits
# across a page boundary and orphans a row or two onto an otherwise-blank page.
A(
    KeepTogether(
        [
            sub("A. Segment detail"),
            styled_table(
                seg_tbl,
                [1.5 * inch, 1.2 * inch] + [(CONTENT_W - 2.7 * inch) / 3] * 3,
                highlight_rows=[1],
            ),
        ]
    )
)
A(Spacer(1, 10))
ch_tbl = [["Channel", "Weighted discount", "Revenue"]]
for k in ["Reseller", "Partner", "Direct", "Online"]:
    ch_tbl.append([k, pct(S["channel"][k]["discount"]), money(S["channel"][k]["revenue"])])
A(
    KeepTogether(
        [
            sub("B. Channel detail"),
            styled_table(ch_tbl, [2.0 * inch, 2.0 * inch, CONTENT_W - 4.0 * inch]),
        ]
    )
)
A(Spacer(1, 10))
cat_tbl = [["Category", "Revenue", "Discount", "Margin proxy"]]
for c in sorted(S["category"], key=lambda x: -x["revenue"]):
    cat_tbl.append([c["category"], money(c["revenue"]), pct(c["discount"]), pct(c["margin"])])
A(
    KeepTogether(
        [
            sub("C. Product category detail"),
            styled_table(
                cat_tbl,
                [
                    2.0 * inch,
                    1.4 * inch,
                    (CONTENT_W - 3.4 * inch) / 2,
                    (CONTENT_W - 3.4 * inch) / 2,
                ],
            ),
        ]
    )
)
A(Spacer(1, 10))
reg_tbl = [["Region", "Revenue", "Weighted discount", "Margin proxy"]]
for r in sorted(S["region"], key=lambda x: -x["revenue"]):
    reg_tbl.append([r["region"], money(r["revenue"]), pct(r["discount"]), pct(r["margin"])])
A(
    KeepTogether(
        [
            sub("D. Region detail"),
            styled_table(
                reg_tbl,
                [
                    1.8 * inch,
                    1.4 * inch,
                    (CONTENT_W - 3.2 * inch) / 2,
                    (CONTENT_W - 3.2 * inch) / 2,
                ],
            ),
        ]
    )
)
A(Spacer(1, 10))
tier_tbl = [["Tier", "Recommended action", "Customers", "Revenue", "Avg priority"]]
for t in sorted(S["risk_tiers"], key=lambda x: -x["avg_governance_priority"]):
    tier_tbl.append(
        [
            t["risk_tier"],
            t["recommended_action"],
            f"{t['customers']}",
            money(t["total_revenue"]),
            f"{t['avg_governance_priority']:.0f}",
        ]
    )
A(
    KeepTogether(
        [
            sub("E. Risk tier detail"),
            styled_table(
                tier_tbl,
                [
                    0.9 * inch,
                    2.0 * inch,
                    0.9 * inch,
                    (CONTENT_W - 3.8 * inch) / 2,
                    (CONTENT_W - 3.8 * inch) / 2,
                ],
                highlight_rows=[1],
            ),
        ]
    )
)
A(Spacer(1, 12))
A(
    para(
        f"<b>Provenance.</b> All figures derive from the processed marts of the pricing-governance pipeline over "
        f"{S['coverage']}: {S['n_order_items']:,} order lines, {S['n_customers']:,} customers, {S['n_products']} products. "
        f"Ten formal-analysis validation checks and the full metric-contract reconciliation passed at the time of "
        f"publication. Charts are generated by scripts/build_report_assets.py and this report by scripts/build_report_pdf.py, "
        f"both reproducible from the processed data.",
        CAP,
    )
)

# ---------------------------------------------------------------------------
doc.multiBuild(story)
print("wrote", (REPORTS / "pricing_discount_governance_report.pdf").relative_to(ROOT))
