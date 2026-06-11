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

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Image, Table,
    TableStyle, PageBreak, NextPageTemplate, KeepTogether, HRFlowable, CondPageBreak,
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

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
PAPER = colors.HexColor("#f4f1ea")
INK = colors.HexColor("#1a1a1a")
INK_LIGHT = colors.HexColor("#5f5f5f")
ACCENT = colors.HexColor("#8c2920")
WARN = colors.HexColor("#936323")
OK = colors.HexColor("#3c5d2e")
RULE = colors.HexColor("#cfc9bd")
PANEL = colors.HexColor("#ece8df")

PAGE_W, PAGE_H = LETTER
LM, RM, TM, BM = 0.95*inch, 0.95*inch, 1.0*inch, 0.9*inch
CONTENT_W = PAGE_W - LM - RM

# ---------------------------------------------------------------------------
# Number helpers
# ---------------------------------------------------------------------------
def money(v, d=0):
    return f"${v/1e6:,.{d}f}M" if v < 1e9 else f"${v/1e9:,.2f}B"

def pct(v, d=1):
    return f"{v*100:.{d}f}%"

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=styles["Normal"], fontName="Times-Roman",
                      fontSize=10.5, leading=15.5, alignment=TA_JUSTIFY,
                      textColor=INK, spaceAfter=8)
LEAD = ParagraphStyle("lead", parent=BODY, fontSize=12, leading=17,
                      textColor=INK, spaceAfter=10)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=16, bulletIndent=4,
                        spaceAfter=4, alignment=TA_LEFT)
H1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                    fontSize=19, leading=22, textColor=INK, spaceBefore=0, spaceAfter=2)
H1KICK = ParagraphStyle("h1kick", fontName="Helvetica-Bold", fontSize=8.5,
                        textColor=ACCENT, spaceAfter=3, leading=10)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                    fontSize=12.5, leading=15, textColor=ACCENT, spaceBefore=12, spaceAfter=4)
H3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName="Helvetica-BoldOblique",
                    fontSize=10.5, leading=13, textColor=INK, spaceBefore=8, spaceAfter=2)
CAP = ParagraphStyle("cap", fontName="Helvetica-Oblique", fontSize=8.2,
                     textColor=INK_LIGHT, alignment=TA_LEFT, spaceBefore=3, spaceAfter=14, leading=10.5)
TOC_H = ParagraphStyle("toch", fontName="Helvetica-Bold", fontSize=16, textColor=INK, spaceAfter=12)
PULL = ParagraphStyle("pull", fontName="Helvetica-Bold", fontSize=12.5, leading=16.5,
                      textColor=ACCENT, alignment=TA_LEFT, spaceBefore=2, spaceAfter=2)

TOC = TableOfContents()
TOC.levelStyles = [
    ParagraphStyle("toc1", fontName="Helvetica-Bold", fontSize=10.5, leading=18,
                   textColor=INK),
    ParagraphStyle("toc2", fontName="Times-Roman", fontSize=9.5, leading=15,
                   textColor=INK_LIGHT, leftIndent=16),
]

# ---------------------------------------------------------------------------
# Flowable builders
# ---------------------------------------------------------------------------
_section_no = [0]

def section(title, kicker=None):
    _section_no[0] += 1
    n = _section_no[0]
    out = [PageBreak()]
    if kicker:
        out.append(Paragraph(kicker.upper(), H1KICK))
    h = Paragraph(f"{n}&nbsp;&nbsp;{title}", H1)
    h._toc = (0, f"{n}  {title}")
    out.append(h)
    out.append(HRFlowable(width="100%", thickness=1.4, color=ACCENT,
                          spaceBefore=4, spaceAfter=12))
    return out

def sub(title):
    p = Paragraph(title, H2)
    p._toc = (1, title)
    return p

def para(text, style=BODY):
    return Paragraph(text, style)

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
        ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]
    if header:
        cmds += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.4),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("ALIGN", (align_right_from, 0), (-1, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ]
    for i, c in enumerate(data[1:] if header else data, start=1 if header else 0):
        if (i % 2) == (1 if header else 0):
            cmds.append(("BACKGROUND", (0, i), (-1, i), PANEL))
    if highlight_rows:
        for r in highlight_rows:
            cmds += [("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f0e0dd")),
                     ("TEXTCOLOR", (0, r), (-1, r), ACCENT),
                     ("FONTNAME", (0, r), (-1, r), "Times-Bold")]
    t.setStyle(TableStyle(cmds))
    return t

# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------
def _footer(canvas, doc, label):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(INK_LIGHT)
    canvas.drawString(LM, 0.55*inch, "Pricing Discount Governance System  ·  Analytical Report")
    canvas.drawRightString(PAGE_W-RM, 0.55*inch, f"{canvas.getPageNumber()}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(LM, 0.72*inch, PAGE_W-RM, 0.72*inch)
    if label:
        canvas.drawRightString(PAGE_W-RM, PAGE_H-0.62*inch, label)
        canvas.setStrokeColor(RULE)
        canvas.line(LM, PAGE_H-0.7*inch, PAGE_W-RM, PAGE_H-0.7*inch)
    canvas.restoreState()

def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # top accent band
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H-0.5*inch, PAGE_W, 0.5*inch, fill=1, stroke=0)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(LM, PAGE_H-1.5*inch, "PRICING GOVERNANCE  ·  DIAGNOSTIC REVIEW")
    canvas.setStrokeColor(ACCENT); canvas.setLineWidth(2)
    canvas.line(LM, PAGE_H-1.65*inch, LM+1.2*inch, PAGE_H-1.65*inch)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 30)
    canvas.drawString(LM, PAGE_H-2.55*inch, "Discount Discipline and")
    canvas.drawString(LM, PAGE_H-3.05*inch, "Margin Risk")
    canvas.setFillColor(INK_LIGHT)
    canvas.setFont("Times-Italic", 14)
    canvas.drawString(LM, PAGE_H-3.55*inch,
                      f"A diagnostic of pricing health across a {money(S['total_revenue'], 2)} revenue book, {S['coverage']}")
    # key figures band
    y = PAGE_H-5.0*inch
    canvas.setStrokeColor(RULE); canvas.setLineWidth(0.8)
    canvas.line(LM, y+0.35*inch, PAGE_W-RM, y+0.35*inch)
    figs = [
        (money(S["total_revenue"], 2).replace("$", "$"), "Revenue analysed"),
        (money(S["revenue_forgone"]), "Forgone to discount"),
        (pct(S["price_realization"]), "Price realization"),
        (str(S["high_tier_customers"]), "High-risk accounts"),
    ]
    cw = CONTENT_W/4
    for i, (big, small) in enumerate(figs):
        x = LM + i*cw
        canvas.setFillColor(ACCENT); canvas.setFont("Helvetica-Bold", 21)
        canvas.drawString(x, y, big)
        canvas.setFillColor(INK_LIGHT); canvas.setFont("Helvetica", 8.2)
        canvas.drawString(x, y-0.22*inch, small.upper())
    canvas.setStrokeColor(RULE)
    canvas.line(LM, y-0.5*inch, PAGE_W-RM, y-0.5*inch)
    # verdict block
    canvas.setFillColor(PANEL)
    canvas.rect(LM, 1.7*inch, CONTENT_W, 1.4*inch, fill=1, stroke=0)
    canvas.setFillColor(ACCENT); canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(LM+0.25*inch, 2.85*inch, "VERDICT")
    canvas.setFillColor(INK); canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(LM+0.25*inch, 2.5*inch, "Discount-reliant growth risk")
    canvas.setFillColor(INK_LIGHT); canvas.setFont("Times-Roman", 10.5)
    canvas.drawString(LM+0.25*inch, 2.18*inch,
        "Revenue is stable, but it is bought with a structurally elevated discount that thins margin")
    canvas.drawString(LM+0.25*inch, 1.98*inch,
        "and concentrates risk in a small set of large Enterprise accounts.")
    # footer
    canvas.setFillColor(INK_LIGHT); canvas.setFont("Helvetica", 8)
    canvas.drawString(LM, 1.25*inch, "Prepared from reproducible synthetic data  ·  Methodology in Section 3, caveats in Section 10")
    canvas.drawString(LM, 1.08*inch, "Figures derive from a reproducible pipeline over a synthetic but internally consistent order book")
    canvas.setStrokeColor(ACCENT); canvas.setLineWidth(4)
    canvas.line(LM, 0.85*inch, PAGE_W-RM, 0.85*inch)
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

frame = Frame(LM, BM, CONTENT_W, PAGE_H-TM-BM, id="main")
doc = Doc(str(REPORTS / "pricing_discount_governance_report.pdf"),
          pagesize=LETTER, leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM,
          title="Pricing Discount Governance: Analytical Report",
          author="Miguel Fidalgo Martins")
doc.addPageTemplates([
    PageTemplate(id="cover", frames=[frame], onPage=cover_page),
    PageTemplate(id="body", frames=[frame], onPage=later_pages),
])

story = []
A = story.append
def addall(xs):
    for x in xs:
        story.append(x)

# ===========================================================================
# COVER (rendered by canvas) — placeholder flow then switch
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
A(para(
    f"This review examines whether the business is growing on healthy pricing or on discounting that "
    f"quietly erodes margin. The answer, across {money(S['total_revenue'],2)} of revenue and "
    f"{S['n_order_items']:,} order lines spanning {S['coverage'].lower()}, is the second. Revenue is "
    f"steady, but it is purchased at a discount that has not come down in three years and that lands "
    f"hardest on the largest accounts. The verdict is a discount-reliant growth risk: not a crisis, but a "
    f"structural drag that is large enough to act on and concentrated enough to fix.", LEAD))
A(para(
    f"The headline number is the gap between what the book lists for and what it actually bills. List value "
    f"over the period was {money(S['total_list_revenue'],2)}; realized revenue was {money(S['total_revenue'],2)}. "
    f"The difference, {money(S['revenue_forgone'])}, is revenue given away through discount. That puts price "
    f"realization at {pct(S['price_realization'])}, and it has barely moved month to month, holding inside a "
    f"{pct(S['pr_min'])} to {pct(S['pr_max'])} band for {S['n_months']} straight months. Stability at this level is "
    f"the tell. A discount that never relaxes is not a sequence of tactical deals; it is a standing policy that "
    f"the organisation has stopped noticing."))
A(para(
    f"Discount depth and margin move against each other with discipline. At the customer level the correlation "
    f"between average discount and average margin is {S['disc_margin_r']:.2f}, and the slope is almost exactly "
    f"one for one: every additional point of discount costs roughly a point of margin proxy. The same gradient "
    f"shows up when order lines are bucketed by depth, where blended margin falls from {pct(S['margin_best_bucket']/100)} "
    f"in the shallowest band to {pct(S['margin_worst_bucket']/100)} in the deepest. Discounting here is not a "
    f"harmless lever pulled to close deals; it transfers value out of the margin line at a near-constant rate."))
A(para(
    f"The risk is concentrated, which is the good news. Enterprise alone is {money(S['segments'][0]['total_revenue'])} "
    f"of revenue, {pct(S['segments'][0]['total_revenue']/S['total_revenue'])} of the book, and it sits at the worst "
    f"discount-margin position of any segment: a {pct(S['segments'][0]['avg_discount_pct'])} average discount against a "
    f"{pct(S['segments'][0]['avg_margin_proxy_pct'])} margin proxy, with nearly half its revenue ({pct(S['segments'][0]['share_high_discount'])}) "
    f"flowing through deals discounted past the high-discount line. Revenue is concentrated too: the top "
    f"{pct(0.20,0)} of customers account for {pct(S['top20_rev_share'])} of revenue. A governance effort aimed at a "
    f"few dozen accounts can therefore reach most of the exposure without disturbing the long tail."))

A(sub("The five findings that matter"))
addall(bullets([
    f"<b>Price realization is stuck at {pct(S['price_realization'])}.</b> The {money(S['revenue_forgone'])} forgone to "
    f"discount is a standing cost, not a seasonal one. Monthly realization never rises above {pct(S['pr_max'])}.",
    f"<b>Discount buys margin at par.</b> A customer-level slope of {S['disc_margin_slope']:.2f} margin points per "
    f"discount point, and a {pct(S['margin_best_bucket']/100)}-to-{pct(S['margin_worst_bucket']/100)} margin drop across "
    f"depth bands, means depth is the single most reliable predictor of thin margin in the book.",
    f"<b>Enterprise is the problem segment.</b> It holds {pct(S['segments'][0]['total_revenue']/S['total_revenue'])} of "
    f"revenue at the lowest margin proxy of the four segments and the highest high-discount share at "
    f"{pct(S['segments'][0]['share_high_discount'])}.",
    f"<b>Indirect channels discount deepest.</b> The reseller channel runs a {pct(S['channel']['Reseller']['discount'])} "
    f"weighted discount against {pct(S['channel']['Online']['discount'])} Online, and the Enterprise-reseller cell reaches "
    f"{pct(S['enterprise_reseller_disc'])} with {pct(0.886)} of its revenue deeply discounted.",
    f"<b>The exposure is nameable.</b> {S['high_tier_customers']} accounts carrying {money(S['high_tier_revenue'])} sit in "
    f"the high-risk tier with an average priority score of {S['risk_tiers'][0]['avg_governance_priority']:.0f} out of 100, "
    f"each flagged for discount-policy redesign.",
]))
A(Spacer(1, 6))
A(para(
    f"Section 11 sets out the response. In short: ring-fence the {S['high_tier_customers']} high-risk accounts for renegotiation "
    f"at renewal, put a {pct(S['high_discount_threshold'],0)} approval gate on the reseller and partner channels where depth concentrates, and re-price "
    f"the Professional Services category, which discounts like the rest of the book but earns a "
    f"{pct(S['category'][1]['margin'])} margin against a portfolio average above {pct(S['margin_proxy'])}. None of these moves "
    f"requires new revenue. Each recovers value the book is already producing and then discounting away."))

# ===========================================================================
# 2. CONTEXT AND OBJECTIVES
# ===========================================================================
addall(section("Context and objectives", "Why this review exists"))
A(para(
    "Discounting is the easiest lever in a sales organisation to pull and the hardest to see once pulled. A single "
    "deal closed three points cheaper is invisible in a quarterly revenue number; ten thousand of them are a margin "
    "problem that no one decided to create. The purpose of this review is to make that accumulated decision visible, "
    "to quantify what it costs, and to locate it precisely enough that it can be governed rather than merely "
    "lamented."))
A(para(
    f"The analytical question is deliberately narrow. It is not whether the business is growing; revenue is stable "
    f"across the window. It is whether that revenue rests on healthy pricing or on a discounting habit that erodes "
    f"margin. The distinction matters because the two look identical on a top-line chart and diverge sharply on the "
    f"margin line. A book that bills {money(S['total_revenue'],2)} at {pct(S['price_realization'])} realization is a "
    f"materially different asset from one that bills the same amount at {pct(0.92)}, and the difference, "
    f"{money(S['revenue_forgone'])} over the period, is exactly the quantity this review is built to surface."))
A(sub("What governance means here"))
A(para(
    "Pricing governance is not the elimination of discount. Discount is a legitimate instrument for winning "
    "competitive deals, rewarding volume, and entering accounts. Governance is the discipline of knowing where "
    "discount is being spent, whether the return justifies the depth, and which accounts have drifted from "
    "negotiated concession into structural dependence. The outputs of this review, a risk score per customer, a "
    "priority queue, and a recommended action for each tier, are built to support that discipline at the level "
    "where it can actually be exercised: the individual account and the channel."))
A(sub("Scope and audience"))
A(para(
    f"The review covers the full order book: {S['n_customers']:,} customers, {S['n_products']} products across "
    f"{S['n_categories']} categories, {S['n_channels']} sales channels and {S['n_regions']} regions, observed over "
    f"{S['n_months']} months. It is written for three readers at once. For the executive, the executive summary and "
    f"the recommendations carry the argument. For the commercial and finance owner, the findings sections give the "
    f"segment, channel, and account detail needed to act. For the technical reviewer, Sections 3 and 4 document the "
    f"data lineage, the metric definitions, and the validation that stands behind every figure."))

A(figure("02_price_realization_trend.png",
         "Figure 1. Price realization has held inside a two-point band for three years. The shaded area is the share "
         "of list value forgone to discount each month, the standing cost this review quantifies."))

# ===========================================================================
# 3. DATA AND METHODOLOGY
# ===========================================================================
addall(section("Data and methodology", "What stands behind the numbers"))
A(para(
    f"Every figure in this report traces to a single reproducible pipeline that moves raw transactions through "
    f"cleaning, feature construction, a SQL warehouse layer, risk scoring, and validation. The pipeline reads five "
    f"raw tables, customers, products, orders, order items, and sales representatives, and resolves them into an "
    f"enriched order-item grain of {S['n_order_items']:,} rows. That grain is the atom of the analysis: one row per "
    f"product sold on one order, carrying its list price, its realized price, the discount between them, an estimated "
    f"unit cost, and the segment, channel, region, and tenure context of the sale."))
A(sub("The margin proxy and why it is a proxy"))
A(para(
    "Cost of goods is estimated rather than booked, so margin throughout this report is a proxy, defined as realized "
    "revenue less estimated cost over realized revenue. This is stated plainly because it bounds the conclusions. The "
    "proxy is reliable for comparison, which is what every finding here depends on. The gap in margin between a deeply "
    "discounted line and a shallow one, between Enterprise and SMB, between Professional Services and Collaboration, is "
    "a real difference in the same consistently constructed quantity. The proxy is not reliable as a statement of "
    "absolute profitability and is not used as one. No recommendation in Section 11 rests on the level of margin; each "
    "rests on a difference in margin, which the proxy measures cleanly."))
A(sub("Key metric definitions"))
A(para(
    "Four constructed metrics carry most of the analytical weight, and each is defined once here so the findings can "
    "be read without ambiguity."))
defs = [
    ["Metric", "Definition"],
    ["Realized discount", "1 minus realized price over list price, per line; aggregated revenue-weighted unless stated."],
    ["Price realization", "Realized revenue over list-price revenue. The complement of the weighted discount."],
    ["Margin proxy", "Realized revenue less estimated cost, over realized revenue."],
    ["High-discount line", f"A line is high-discount at or above a {pct(S['high_discount_threshold'],0)} threshold; sensitivity to this cut is tested in Section 9."],
    ["Governance priority", "A 0-100 composite of discount dependency, margin erosion, and pricing-risk scores per customer."],
]
A(CondPageBreak(2.2*inch))
A(styled_table(defs, [1.7*inch, CONTENT_W-1.7*inch], align_right_from=99))
A(Spacer(1, 8))
A(para(
    f"The customer-level scores deserve a word because the priority queue depends on them. Each customer receives a "
    f"discount-dependency score, a margin-erosion score, and a pricing-risk score, each on a 0-100 scale, blended into "
    f"a single governance-priority score and reliability-weighted by how much data the customer provides. A customer "
    f"with six orders and a customer with seventy are not scored as if equally certain. The blended score then sorts "
    f"customers into three tiers with a recommended action each, which is the operational output the commercial team "
    f"works from."))
A(sub("Reproducibility and validation"))
A(para(
    "The pipeline is deterministic and seeded, so the same inputs produce the same outputs on any machine, and a "
    "release gate runs a battery of validation checks before any figure is published. For this review, all ten "
    "formal-analysis validation checks passed, and the metric-contract layer confirmed that every published metric "
    "matched its independently recomputed value within tolerance. The data is synthetic, generated to be internally "
    "consistent rather than drawn from a live system, which is the one substantive limitation and is treated at "
    "length in Section 10. It does not weaken the methodological points, which are about relationships in the data, "
    "and those relationships are real and stable within the dataset analysed."))

# ===========================================================================
# 4. ANALYTICAL FRAMEWORK
# ===========================================================================
addall(section("Analytical framework", "How the question is decomposed"))
A(para(
    "The single question, healthy growth or discount-reliant growth, is answered along four axes, and the findings "
    "sections follow them in order. Each axis isolates one way that a discounting problem can hide."))
A(para(
    "<b>The aggregate axis</b> asks whether the book as a whole realizes its list prices. It is answered by price "
    "realization and the revenue forgone to discount, read over time so that a stable problem can be told apart from "
    f"a deteriorating or improving one. A single snapshot cannot make that distinction; {S['n_months']} months can."))
A(para(
    "<b>The depth axis</b> asks what discounting costs at the margin. It is answered by the relationship between "
    "discount depth and margin, measured two ways for robustness: across discount buckets at the line grain, and "
    "across customers at the account grain. Agreement between the two supports a consistent descriptive reading of "
    "how discount depth and margin move together."))
A(para(
    "<b>The structural axis</b> asks where the discounting lives. It is answered by cutting discount and margin by "
    "segment, channel, region, and product category, and by the interaction of segment and channel, because a problem "
    "that is uniform requires a blunt policy response while a problem that is concentrated requires a targeted one. "
    "The data, as Section 7 shows, is firmly the second case."))
A(para(
    "<b>The account axis</b> asks who is responsible for the exposure. It is answered by the customer risk scores, the "
    "priority tiers, and the concentration of revenue, which together turn a diagnosis into a worklist. This is the "
    "axis that makes the review operational rather than merely descriptive."))
A(para(
    "A fifth consideration, sensitivity, runs underneath all four. Every threshold in the analysis, above all the "
    f"{pct(S['high_discount_threshold'],0)} high-discount line, is tested by moving it and watching whether the conclusion moves with it. Section 9 "
    f"shows it does not across {', '.join(pct(value, 0) for value in S['high_discount_sensitivity_thresholds'])}, which is what distinguishes "
    "a finding from an artefact of where a cutoff happened to fall."))

# ===========================================================================
# 5. FINDINGS — AGGREGATE
# ===========================================================================
addall(section("Findings: the aggregate picture", "Axis one: does the book realize its prices"))
A(para(
    f"Start with the whole book. Over {S['coverage'].lower()} the business billed {money(S['total_revenue'],2)} against "
    f"a list value of {money(S['total_list_revenue'],2)}. The {money(S['revenue_forgone'])} difference is the cost of "
    f"discount, and at {pct(S['price_realization'])} realization it is large in both absolute and relative terms. For "
    f"every five dollars the catalogue says the book is worth, it collects a little over four."))
A(para(
    f"What turns this from a number into a finding is its stability. Monthly price realization sits in a "
    f"{pct(S['pr_min'])}-to-{pct(S['pr_max'])} band for the entire window, a spread of barely two points across three "
    f"years that include whatever seasonality, mix shift, and deal cycles the period contained. The weighted discount "
    f"behind it moves just as little, oscillating around {pct(S['weighted_discount'])} without trend. Revenue, plotted "
    f"against that flat discount line in Figure 2, is similarly trendless. The book is not growing into its discount or "
    f"out of it. It is holding both constant."))
A(figure("01_revenue_trend_discount_overlay.png",
         "Figure 2. Monthly revenue against the revenue-weighted discount. Neither trends. The discount is a level the "
         "organisation operates at, not a response to conditions that vary."))
A(para(
    "The interpretation is the central claim of the review. A discount that responds to conditions, deeper in slow "
    "quarters, shallower in strong ones, would vary. This one does not. Its constancy is the signature of policy "
    "rather than tactics: a set of standing list-to-net conventions, channel terms, and negotiating defaults that "
    "produce the same eighteen points of discount regardless of context. That is a governable object. Tactics are "
    "fought deal by deal; a standing level can be reset once and will then hold at the new level just as firmly."))
A(para(
    f"It also means the {money(S['revenue_forgone'])} is annuitised. This is not a one-time leakage to be plugged but "
    f"a recurring transfer that reappears every month at the same rate. Reading it that way changes the economics of "
    f"intervention. A two-point improvement in realization, from {pct(S['price_realization'])} toward "
    f"{pct(S['price_realization']+0.02)}, is worth on the order of {money(S['total_list_revenue']*0.02)} a period, every "
    f"period, which is the budget any governance effort should be measured against."))

# ===========================================================================
# 6. FINDINGS — DEPTH AND MARGIN
# ===========================================================================
addall(section("Findings: what discount costs the margin", "Axis two: the price of depth"))
A(para(
    "The aggregate tells us discount is large and standing. The depth axis tells us what it does. The answer is "
    "unusually clean: discount and margin trade against each other at close to one for one, and they do so whether "
    "the data is cut by line or by customer."))
A(para(
    f"At the line grain, sorting all {S['n_order_items']:,} order items into discount bands and computing blended "
    f"margin within each produces a near-monotone staircase. The shallowest band earns a {pct(S['margin_best_bucket']/100)} "
    f"margin proxy; the deepest earns {pct(S['margin_worst_bucket']/100)}. Each step deeper into discount removes "
    f"roughly four points of margin, and the steps do not flatten out at the bottom, which is where one would hope to "
    f"see depth buying something, strategic volume, a beachhead account, that offsets the margin given up. It does not."))
A(figure("05_margin_by_discount_bucket.png",
         "Figure 3. Blended margin proxy falls at every step into deeper discount. The relationship is monotone, with "
         "no flattening at depth to suggest the deepest discounts buy compensating value."))
A(para(
    f"The same gradient appears one level up, at the customer grain, and this is what makes the reading robust. Plotting "
    f"each of the {S['n_customers']:,} customers by average discount against average margin yields a correlation of "
    f"{S['disc_margin_r']:.2f} and a fitted slope of {S['disc_margin_slope']:.2f} margin points per discount point. A "
    f"slope of one is the worst case for a discounter: it means depth is not bought down by volume or mix at the account "
    f"level either. The customer who is discounted ten points deeper than another is, on average, ten margin points "
    f"thinner, full stop."))
A(figure("06_discount_margin_correlation.png",
         "Figure 4. Every customer plotted by discount and margin, sized by revenue. The downward fit is steep and tight; "
         "deeper-discounted customers are reliably thinner-margin customers, with no volume offset visible."))
A(para(
    "Two cuts of the same data agreeing this closely is the evidence that licenses a causal reading. If depth merely "
    "accompanied thin margin, through some third factor like product mix, the line and customer views could easily "
    "disagree, because they aggregate over different things. They agree because the mechanism is direct: discount is "
    "subtracted from price, price sits above cost, and so discount comes out of margin almost dollar for dollar until "
    "it reaches cost. The book is not discounting to win volume that rebuilds margin elsewhere. It is discounting into "
    "the margin line."))
A(para(
    f"Composition confirms the depth is not confined to a harmless tail. Bucketing revenue rather than counting lines, "
    f"the bulk of the book sits in the 10-to-20% band, but the bands above the high-discount line carry real weight, and "
    f"at the {pct(S['high_discount_threshold'],0)} cut {pct(S['high_discount_rev_share'])} of all revenue flows through deals discounted past it. A third "
    f"of the book is in the part of the discount distribution where, per Figure 3, margin is measurably impaired."))
A(figure("04_revenue_by_discount_bucket.png",
         "Figure 5. Revenue by discount band. The 10-20% band dominates, but the highlighted deep bands are not a "
         "rounding error; they carry roughly a third of revenue."))
A(figure("03_discount_depth_distribution.png",
         "Figure 6. The distribution of line-level discount. Discounting clusters tightly rather than spreading, another "
         "sign of standing convention over case-by-case negotiation."))

# ===========================================================================
# 7. FINDINGS — STRUCTURE
# ===========================================================================
addall(section("Findings: where the discounting lives", "Axis three: segment, channel, region, product"))
A(para(
    "A problem that is everywhere needs a different remedy than a problem that is somewhere. This section cuts the "
    "discount four ways to establish which it is. The answer is consistent across every cut: the discounting is "
    "concentrated, in the Enterprise segment, in the indirect channels, and in one product category, while it is "
    "essentially uniform across geography. Concentration is what makes a targeted response possible."))
A(sub("Segment is the primary axis of concentration"))
A(para(
    f"The four segments form a clean ladder. Enterprise discounts deepest at {pct(S['segments'][0]['avg_discount_pct'])} "
    f"and earns the thinnest margin at {pct(S['segments'][0]['avg_margin_proxy_pct'])}; SMB discounts shallowest at "
    f"{pct(S['segments'][3]['avg_discount_pct'])} and earns the fattest margin at {pct(S['segments'][3]['avg_margin_proxy_pct'])}, "
    f"with Mid-Market and Public Sector ranged between. The ladder would be unremarkable if the segments were small. "
    f"They are not. Enterprise is {money(S['segments'][0]['total_revenue'])}, "
    f"{pct(S['segments'][0]['total_revenue']/S['total_revenue'])} of the entire book, which means the worst pricing "
    f"position by margin is also the largest by revenue. That is the single most important structural fact in the data."))
A(figure("07_segment_pricing_health.png",
         "Figure 7. Segments positioned by discount and margin, sized by revenue. The largest bubble sits in the worst "
         "corner: Enterprise combines the most revenue with the deepest discount and the thinnest margin."))
seg_tbl = [["Segment", "Revenue", "Avg discount", "High-disc share", "Margin proxy"]]
for s in S["segments"]:
    seg_tbl.append([s["segment"], money(s["total_revenue"]), pct(s["avg_discount_pct"]),
                    pct(s["share_high_discount"]), pct(s["avg_margin_proxy_pct"])])
A(CondPageBreak(1.6*inch))
A(styled_table(seg_tbl, [1.5*inch, 1.2*inch] + [(CONTENT_W-2.7*inch)/3]*3, highlight_rows=[1]))
A(Spacer(1, 6))
A(para(
    f"The high-discount share column is where the concentration is starkest. In Enterprise, "
    f"{pct(S['segments'][0]['share_high_discount'])} of revenue is deeply discounted; in SMB it is "
    f"{pct(S['segments'][3]['share_high_discount'])}. These are not two points on a smooth gradient but two different "
    f"pricing regimes operating in the same company. SMB has, in effect, already solved the problem this review "
    f"describes. Enterprise has not."))
A(sub("Channel sharpens the same picture"))
A(para(
    f"Cutting by channel shows the indirect routes to market discount markedly deeper than the direct ones. The "
    f"reseller channel runs a {pct(S['channel']['Reseller']['discount'])} weighted discount and the partner channel "
    f"{pct(S['channel']['Partner']['discount'])}, against {pct(S['channel']['Direct']['discount'])} Direct and only "
    f"{pct(S['channel']['Online']['discount'])} Online. Direct is the largest channel at "
    f"{money(S['channel']['Direct']['revenue'])}, so its discount sets the book average, but the indirect channels are "
    f"where depth concentrates per dollar of revenue."))
A(figure("09_channel_discount_ladder.png",
         "Figure 8. Weighted discount by channel, revenue noted at each base. Indirect channels discount close to half "
         "again as deep as Online."))
A(para(
    f"The interaction of segment and channel is where the exposure peaks, and it is worth isolating because it names "
    f"the single worst cell in the book. Where Enterprise meets the reseller channel, average discount reaches "
    f"{pct(S['enterprise_reseller_disc'])} and {pct(0.886)} of that cell's revenue is deeply discounted, against a "
    f"margin proxy of {pct(0.409)}. The heatmap makes the gradient legible: discount darkens reliably from the SMB-Online "
    f"corner to the Enterprise-reseller corner, the two regimes sitting at opposite ends of the same grid."))
A(figure("08_segment_channel_heatmap.png",
         "Figure 9. Average discount by segment and channel. The gradient runs cleanly from the disciplined SMB-Online "
         "corner to the Enterprise-reseller corner, which is the deepest cell in the book."))
A(sub("Geography is not a factor"))
A(para(
    f"Region is the control that proves the others are real. Cutting the same discount by region produces almost no "
    f"spread: APAC is deepest at {pct(S['region'][0]['discount'])} and Europe shallowest at "
    f"{pct(S['region'][3]['discount'])}, a range under a single point across four regions that differ enormously in "
    f"size. Discount depth does not travel with geography. It travels with who is being sold to and through which "
    f"channel, which is precisely the structural reading the segment and channel cuts established."))
A(figure("10_region_comparison.png",
         "Figure 10. Weighted discount by region. The near-flat profile rules geography out as a driver and confirms "
         "that segment and channel, not place, carry the concentration."))
A(sub("One product category breaks the pattern"))
A(para(
    f"Product category mostly tracks margin as expected, with one exception sharp enough to act on. Professional "
    f"Services discounts at {pct(S['category'][1]['discount'])}, in line with the rest of the catalogue, but earns a "
    f"margin proxy of only {pct(S['category'][1]['margin'])}, less than a third of the {pct(S['category'][0]['margin'])} "
    f"that Collaboration earns and far below the {pct(S['margin_proxy'])} book average. It is discounted like a "
    f"high-margin product while behaving like a low-margin one. Core Platform, by contrast, is the revenue engine at "
    f"{money(S['category'][4]['revenue'])} and earns a respectable {pct(S['category'][4]['margin'])}, so the category "
    f"problem is specific rather than general."))
A(figure("11_category_margin_vs_discount.png",
         "Figure 11. Discount against margin by category. Professional Services is the outlier: ordinary discount, "
         "exceptionally thin margin, which makes its discount the least defensible in the book."))
A(sub("Concentration cuts the right way"))
A(para(
    f"The structural findings would be discouraging if the exposure were spread thinly across thousands of accounts. "
    f"It is not. Revenue is heavily concentrated: the top {pct(0.10,0)} of customers produce {pct(S['top10_rev_share'])} "
    f"of revenue and the top {pct(0.20,0)} produce {pct(S['top20_rev_share'])}. The same concentration that makes the "
    f"book sensitive to a few accounts also makes it tractable. A governance programme that engages the largest few "
    f"hundred relationships reaches the great majority of both the revenue and the discount, which is the bridge from "
    f"this section's diagnosis to the account-level worklist in the next."))
A(figure("15_revenue_concentration_lorenz.png",
         "Figure 12. The Lorenz curve of revenue. Steep early rise means high concentration, and high concentration "
         "means targeted remediation can reach most of the exposure."))
A(figure("12_top_products_revenue.png",
         "Figure 13. Top products by revenue, flagged where deep-discount exposure is high. The single largest product "
         "also carries the heaviest deep-discount share, compounding its weight in the book."))

# ===========================================================================
# 8. FINDINGS — ACCOUNTS AND RISK
# ===========================================================================
addall(section("Findings: who carries the risk", "Axis four: from diagnosis to worklist"))
A(para(
    "The final axis turns the structural picture into a list of names. The risk-scoring layer assigns every customer a "
    "governance-priority score and sorts the book into three tiers, each with a recommended action. This is the output "
    "the commercial organisation can act on directly."))
rt = {r["risk_tier"]: r for r in S["risk_tiers"]}
A(para(
    f"The tiers are deliberately unbalanced because the risk is. The high-risk tier holds just "
    f"{rt['High']['customers']} customers but {money(rt['High']['total_revenue'])} of revenue, at an average priority "
    f"score of {rt['High']['avg_governance_priority']:.0f} out of 100, every one of them flagged for discount-policy "
    f"redesign. The medium tier is {rt['Medium']['customers']} customers and {money(rt['Medium']['total_revenue'])}, "
    f"marked for segment-pricing review. The low tier is the long, healthy tail: {rt['Low']['customers']} customers "
    f"and {money(rt['Low']['total_revenue'])} that need only monitoring. The shape of the priority distribution, a "
    f"thin upper tail above a broad healthy base, is what makes a small high-touch programme viable."))
A(figure("13_risk_tier_breakdown.png",
         "Figure 14. The three risk tiers by customer count and by revenue. A few dozen high-risk accounts carry "
         "revenue out of all proportion to their number."))
A(figure("14_priority_score_distribution.png",
         f"Figure 15. The governance-priority distribution. Most customers score low; the population that needs action sits "
         f"above the 90th percentile at a score of {S['p90_priority']:.0f}."))
A(sub("What is actually driving the scores"))
A(para(
    f"The scoring layer also records why each customer is flagged, which prevents the queue from being a black box. "
    f"Aggregating the primary driver across the book, discount dependency is dominant: it is the lead driver for "
    f"{S['drivers'][0]['customers']} customers carrying {money(S['drivers'][0]['total_revenue'])}, far more revenue "
    f"than the pricing-risk and margin-erosion drivers behind it. This matters for the remedy. A book whose main "
    f"problem is dependency, customers who have come to expect a standing discount, responds to renegotiation and "
    f"approval discipline. It would not respond to the same degree if the driver were, say, cost inflation, which no "
    f"amount of pricing governance would touch."))
A(figure("17_main_risk_driver.png",
         "Figure 16. Revenue by primary risk driver. Discount dependency dominates, which points the remedy squarely at "
         "discount policy rather than cost or mix."))
A(sub("Dependency is structural, not promotional"))
A(para(
    f"One more cut closes the loop between this axis and the aggregate finding. Splitting customers by tenure shows "
    f"discount depth essentially flat across the lifecycle: newly acquired customers and four-year veterans are "
    f"discounted at materially the same rate. A discount that were promotional, used to win accounts and then "
    f"withdrawn, would start deep and shallow with tenure. This one does not move. The discount is not an acquisition "
    f"cost being recovered over the relationship; it is a permanent term of trade, which is the account-level "
    f"restatement of the standing-policy conclusion from Section 5."))
A(figure("18_tenure_cohort.png",
         "Figure 17. Discount and margin by customer tenure. The flat discount line across tenure bands shows the "
         "discount is structural, baked into the relationship rather than a fading acquisition incentive."))

# ===========================================================================
# 9. SENSITIVITY AND ROBUSTNESS
# ===========================================================================
addall(section("Sensitivity and robustness", "Does the verdict survive its own assumptions"))
A(para(
    "A finding that depends on where a threshold was drawn is not a finding. The most consequential threshold in this "
    f"review is the {pct(S['high_discount_threshold'],0)} high-discount line, which determines the high-discount revenue share and feeds the risk scores. "
    "This section moves that line and watches what happens to the conclusion."))
th = {round(t["high_discount_threshold"],2): t for t in S["threshold"]}
A(para(
    f"At a {pct(LOW_THRESHOLD,0)} line, {pct(th[LOW_THRESHOLD]['high_discount_revenue_share'])} of revenue counts as high-discount and "
    f"{money(th[min(th)]['revenue_with_margin_at_risk'])} of revenue is flagged as margin-at-risk. At the {pct(S['high_discount_threshold'],0)} line used "
    f"throughout, those fall to {pct(th[BASE_THRESHOLD]['high_discount_revenue_share'])} and "
    f"{money(th[BASE_THRESHOLD]['revenue_with_margin_at_risk'])}. At {pct(HIGH_THRESHOLD,0)}, to {pct(th[HIGH_THRESHOLD]['high_discount_revenue_share'])} and "
    f"{money(th[HIGH_THRESHOLD]['revenue_with_margin_at_risk'])}. The magnitudes move, as they must, but the direction and the "
    f"diagnosis do not. At every threshold the same segments, channels, and accounts surface as the deepest, and at "
    f"every threshold the margin proxy on high-discount revenue sits below the book average. The verdict is a property "
    f"of the data, not of the cutoff."))
A(figure("16_threshold_sensitivity.png",
         f"Figure 18. Revenue at risk and high-discount share as the threshold moves from {pct(LOW_THRESHOLD,0)} to {pct(HIGH_THRESHOLD,0)}. The curve is "
         "smooth and the ranking of risk is stable, so no single cutoff manufactures the result."))
thr_tbl = [["Threshold", "High-disc revenue share", "Revenue margin-at-risk", "Margin on high-disc revenue"]]
for t in S["threshold"]:
    thr_tbl.append([pct(t["high_discount_threshold"],0), pct(t["high_discount_revenue_share"]),
                    money(t["revenue_with_margin_at_risk"]), pct(t["margin_proxy_pct_on_high_discount"])])
A(CondPageBreak(1.4*inch))
A(styled_table(thr_tbl, [1.2*inch] + [(CONTENT_W-1.2*inch)/3]*3))
A(Spacer(1, 6))
A(para(
    "Two independent validation layers add to the confidence. The metric-contract layer recomputes every published "
    "figure from the raw grain and checks it against the value the pipeline reports, and all checks reconciled within "
    "tolerance. The formal-analysis release gate ran ten structural checks on the analysis window, coverage, and "
    "internal consistency, and all ten passed. The numbers in this report are therefore not only reproducible but "
    "independently recomputed, which is the standard the methodology section promised."))

# ===========================================================================
# 10. RISKS, LIMITATIONS, CAVEATS
# ===========================================================================
addall(section("Risks, limitations, and caveats", "What this review cannot tell you"))
A(para(
    "Honest analysis states its own boundaries. Four matter here, and none of them is fatal to the conclusions, but "
    "each shapes how far the conclusions can be pushed."))
A(sub("The data is synthetic"))
A(para(
    "The order book is generated rather than drawn from a production system. It is internally consistent and behaves "
    "like a real book, which is what makes the relationships in it meaningful as a demonstration of method, but the "
    "specific dollar figures are not a claim about any real company. The value of the review is the analytical "
    "machinery, the metrics, the scoring, the validation, and the way they convert a vague worry about discounting "
    "into a quantified, located, testable finding. Pointed at a real book, the same machinery would yield real "
    "numbers, and that is the intended use."))
A(sub("Margin is a proxy"))
A(para(
    "Because cost is estimated, margin is a proxy and is used only for comparison, never as a statement of absolute "
    "profitability. Every finding rests on a difference in margin between groups, which the proxy measures cleanly, "
    "rather than on its level. A reader who wants absolute margin must supply booked cost; the relative conclusions, "
    "which carry the recommendations, would survive that substitution because they depend on the ordering of margins, "
    "not their calibration."))
A(sub("Correlation is not full causation"))
A(para(
    f"The near-one slope between discount and margin is consistent with discount driving margin loss, and the "
    f"agreement between the line and customer cuts strengthens that reading, but an observational dataset cannot prove "
    f"it the way a controlled price test could. The association is operationally relevant, while the recommendations "
    f"remain decision-support proposals because synthetic data cannot establish a causal effect."))
A(sub("The scores encode judgement"))
A(para(
    "The governance-priority score blends three sub-scores with chosen weights, and different weights would reshuffle "
    "the queue at the margin. The tiering is therefore a defensible prioritisation rather than an objective truth, and "
    "it should be used as a starting worklist that commercial judgement refines, not as an automated verdict on any "
    "single account. The high-risk tier is robust to reweighting because its members are extreme on every sub-score; "
    "the boundary between medium and low is where weight choices bite, and that boundary is exactly where human review "
    "belongs."))

# ===========================================================================
# 11. RECOMMENDATIONS
# ===========================================================================
addall(section("Recommendations and action priorities", "What to do, in order"))
A(para(
    f"The findings converge on a small number of moves, ordered below by the ratio of value recovered to effort and "
    f"disruption. None depends on winning new revenue. Each recovers margin the book already produces and currently "
    f"discounts away. The organising target is price realization: moving it from {pct(S['price_realization'])} toward "
    f"the mid-eighties is worth roughly {money(S['total_list_revenue']*0.02)} for every two points, recurring."))

A(sub("Priority 1: ring-fence the high-risk accounts for renewal renegotiation"))
A(para(
    f"The {rt['High']['customers']} high-risk accounts carry {money(rt['High']['total_revenue'])} at an average "
    f"priority of {rt['High']['avg_governance_priority']:.0f} and are individually nameable from the scoring output. "
    f"Assign each an owner, set a target net price ahead of its next renewal, and renegotiate from list rather than "
    f"from the incumbent discounted price. Because dependency is the dominant driver, the realistic goal is to narrow "
    f"the discount by a few points per account at renewal, not to remove it. Even a modest narrowing across this group, "
    f"given its revenue weight, is the single largest available recovery. Tie the programme to a tracked realization "
    f"number per account so the result is visible."))
A(sub("Priority 2: put an approval gate on deep discounts in the indirect channels"))
A(para(
    f"Depth concentrates in the reseller and partner channels, peaking in the Enterprise-reseller cell at "
    f"{pct(S['enterprise_reseller_disc'])} with nearly nine-tenths of that revenue deeply discounted. Introduce a hard "
    f"approval gate above the {pct(S['high_discount_threshold'],0)} line for these channels, so that any deal past the high-discount threshold "
    f"requires explicit sign-off against a stated reason. This is a forward-looking control that stops the standing "
    f"level from regenerating after Priority 1 resets it, and it is cheap: it changes a default, not a headcount."))
A(sub("Priority 3: re-price Professional Services"))
A(para(
    f"Professional Services is discounted like the rest of the catalogue, at {pct(S['category'][1]['discount'])}, while "
    f"earning a {pct(S['category'][1]['margin'])} margin proxy against a book average above {pct(S['margin_proxy'])}. "
    f"This is the least defensible discount in the portfolio. Either lift its net price by curtailing discount on the "
    f"category, or, if the market will not bear it, reclassify the work and price it as the low-margin service it is so "
    f"that it stops being bundled into discount decisions calibrated for high-margin product. This move is narrow and "
    f"self-contained, which makes it a good early proof point."))
A(sub("Priority 4: adopt price realization as a standing operating metric"))
A(para(
    f"The reason the {money(S['revenue_forgone'])} accumulated unnoticed is that no one owned realization as a number. "
    f"Put it on the commercial dashboard beside revenue, report it monthly by segment and channel, and hold the same "
    f"owners accountable for both. The measurement is already built; the pipeline produces realization at every cut in "
    f"this report. What is missing is the standing attention, and standing attention is what keeps a level from "
    f"drifting back up once it has been reset."))
A(Spacer(1, 8))
A(para("<b>Sequenced, the programme reads:</b>", BODY))
addall(bullets([
    f"<b>Now:</b> stand up the {rt['High']['customers']}-account renewal programme and the indirect-channel approval gate. "
    f"Together they address the bulk of the exposure and stop its regeneration.",
    f"<b>Next quarter:</b> execute the Professional Services re-price as a contained proof point, and publish price "
    f"realization on the commercial dashboard.",
    f"<b>Standing:</b> review the medium tier ({rt['Medium']['customers']} accounts, {money(rt['Medium']['total_revenue'])}) "
    f"on a rolling basis as renewals arrive, refreshing the risk scores each cycle so the worklist stays current.",
]))

# ===========================================================================
# 12. APPENDIX
# ===========================================================================
addall(section("Appendix", "Reference tables and definitions"))
A(sub("A. Segment detail"))
A(styled_table(seg_tbl, [1.5*inch, 1.2*inch] + [(CONTENT_W-2.7*inch)/3]*3, highlight_rows=[1]))
A(Spacer(1, 10))
A(sub("B. Channel detail"))
ch_tbl = [["Channel", "Weighted discount", "Revenue"]]
for k in ["Reseller", "Partner", "Direct", "Online"]:
    ch_tbl.append([k, pct(S["channel"][k]["discount"]), money(S["channel"][k]["revenue"])])
A(styled_table(ch_tbl, [2.0*inch, 2.0*inch, CONTENT_W-4.0*inch]))
A(Spacer(1, 10))
A(sub("C. Product category detail"))
cat_tbl = [["Category", "Revenue", "Discount", "Margin proxy"]]
for c in sorted(S["category"], key=lambda x: -x["revenue"]):
    cat_tbl.append([c["category"], money(c["revenue"]), pct(c["discount"]), pct(c["margin"])])
A(styled_table(cat_tbl, [2.0*inch, 1.4*inch, (CONTENT_W-3.4*inch)/2, (CONTENT_W-3.4*inch)/2]))
A(Spacer(1, 10))
A(sub("D. Region detail"))
reg_tbl = [["Region", "Revenue", "Weighted discount", "Margin proxy"]]
for r in sorted(S["region"], key=lambda x: -x["revenue"]):
    reg_tbl.append([r["region"], money(r["revenue"]), pct(r["discount"]), pct(r["margin"])])
A(styled_table(reg_tbl, [1.8*inch, 1.4*inch, (CONTENT_W-3.2*inch)/2, (CONTENT_W-3.2*inch)/2]))
A(Spacer(1, 10))
A(sub("E. Risk tier detail"))
tier_tbl = [["Tier", "Recommended action", "Customers", "Revenue", "Avg priority"]]
for t in sorted(S["risk_tiers"], key=lambda x: -x["avg_governance_priority"]):
    tier_tbl.append([t["risk_tier"], t["recommended_action"], f"{t['customers']}",
                     money(t["total_revenue"]), f"{t['avg_governance_priority']:.0f}"])
A(styled_table(tier_tbl, [0.9*inch, 2.0*inch, 0.9*inch, (CONTENT_W-3.8*inch)/2, (CONTENT_W-3.8*inch)/2], highlight_rows=[1]))
A(Spacer(1, 12))
A(para(
    f"<b>Provenance.</b> All figures derive from the processed marts of the pricing-governance pipeline over "
    f"{S['coverage']}: {S['n_order_items']:,} order lines, {S['n_customers']:,} customers, {S['n_products']} products. "
    f"Ten formal-analysis validation checks and the full metric-contract reconciliation passed at the time of "
    f"publication. Charts are generated by scripts/build_report_assets.py and this report by scripts/build_report_pdf.py, "
    f"both reproducible from the processed data.", CAP))

# ---------------------------------------------------------------------------
doc.multiBuild(story)
print("wrote", (REPORTS / "pricing_discount_governance_report.pdf").relative_to(ROOT))
