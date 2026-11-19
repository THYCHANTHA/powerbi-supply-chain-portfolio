"""Build the Variance Reporting (Zebra BI) Power BI project (TMDL model + PBIR report).

Variance views use the Zebra BI Tables custom visual from AppSource. The GUID and data roles below
come from the visual's own package (capabilities.json, version 8.4.2.53):
  Category, Group, Values (= actual, AC), PreviousYear (PY), Plan (PL), Forecast (FC), Tooltips, Comments

Free version limits seen when testing 8.4.2.53: more than two measures in one visual shows "Feature Limit
Reached", the table view shows "Available with a Paid Plan", and "invert" (colours for lower-is-better
measures) is only read with a paid licence. So every Zebra visual here uses the chart view, the actual plus
one comparison (PY or PL), and higher-is-better measures (on-time %, not late %). With a Pro licence,
set table=True, add both comparisons and use invert=True for cost or late measures.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "_tools"))
from pbip_builder import (GREY, INK, NAVY, Column as C, Measure as M, Page, Relationship as R,  # noqa: E402
                          Table, Visual, cat_filter, col, findings_box, header, kpi_row, mea, props,
                          slicer, textbox, write_model, write_pbip, write_report)

NAME = "Variance Reporting Zebra BI"
PROJECT = "portfolio/variance-zebra"
DATA = str(ROOT / "data" / "clean")
F, P, K = "Order Lines", "Plan", "Key Measures"
ZEBRA_TABLES = "ZebraBITablesBAE31B370F254F808553548EFB35BFA5"

# ------------------------------------------------------------------ model
order_lines = Table(F, "fact_order_lines.csv", description="One row per order line (DataCo, Jan 2015 - Sep 2017).",
                    columns=[
    C("Order Id", "int64", fmt="0"), C("Order Date", "dateTime", fmt="yyyy-mm-dd"),
    C("Product Id", "int64", hidden=True), C("Shipping Mode", "string", hidden=True),
    C("Is Late", "int64", hidden=True), C("Is Cancelled", "int64", hidden=True),
    C("Actual Ship Days", "int64", hidden=True), C("Scheduled Ship Days", "int64", hidden=True),
    C("Net Sales", "double", hidden=True), C("Profit", "double", hidden=True),
])
plan = Table(P, "fact_plan.csv", description=(
    "Illustrative 2017 plan (Jan-Sep): 2016 actual for the same month and product x (1 + department growth "
    "target). Built by scripts/prepare_data.py. Not a real company budget."), columns=[
    C("Plan Date", "dateTime", fmt="yyyy-mm-dd", hidden=True), C("Product Id", "int64", hidden=True),
    C("Growth Target", "double", fmt="0%", summarize="none"),
    C("Net Sales Plan", "double", hidden=True), C("Profit Plan", "double", hidden=True),
])

S, D = "1. Sales vs PY and Plan", "2. Delivery vs Promise"
PCT = "+0.0%;-0.0%;0.0%"
measures = Table(K, None, columns=[C("Placeholder", hidden=True)],
                 m_source='let\n    Source = #table(type table [Placeholder = text], {})\nin\n    Source',
                 description="All report measures. AC = actual, PY = previous year, PL = plan.", measures=[
    M("Net Sales", f"SUM('{F}'[Net Sales])", r"\$#,0", S, "AC: sales after discount."),
    M("Net Sales PY", "CALCULATE([Net Sales], SAMEPERIODLASTYEAR('Date'[Date]))", r"\$#,0", S,
      "PY: same dates one year earlier. The date table ends Sep 2017, so 2017 compares Jan-Sep with Jan-Sep."),
    M("Net Sales PL", f"SUM('{P}'[Net Sales Plan])", r"\$#,0", S, "PL: illustrative plan (see Plan table)."),
    M("Net Sales vs PY", "VAR PY = [Net Sales PY]\nRETURN IF(NOT ISBLANK(PY), [Net Sales] - PY)", r"+\$#,0;-\$#,0;\$0", S),
    M("Net Sales vs PY %", "VAR PY = [Net Sales PY]\nRETURN IF(NOT ISBLANK(PY), DIVIDE([Net Sales] - PY, PY))", PCT, S),
    M("Net Sales vs PL", "VAR PL = [Net Sales PL]\nRETURN IF(NOT ISBLANK(PL), [Net Sales] - PL)", r"+\$#,0;-\$#,0;\$0", S),
    M("Net Sales vs PL %", "VAR PL = [Net Sales PL]\nRETURN IF(NOT ISBLANK(PL), DIVIDE([Net Sales] - PL, PL))", PCT, S),
    M("Profit", f"SUM('{F}'[Profit])", r"\$#,0", S),
    M("Profit PY", "CALCULATE([Profit], SAMEPERIODLASTYEAR('Date'[Date]))", r"\$#,0", S),
    M("Profit PL", f"SUM('{P}'[Profit Plan])", r"\$#,0", S),
    M("Profit vs PL %", "VAR PL = [Profit PL]\nRETURN IF(NOT ISBLANK(PL), DIVIDE([Profit] - PL, ABS(PL)))", PCT, S),
    M("Orders", f"DISTINCTCOUNT('{F}'[Order Id])", "#,0", D),
    M("Shipped Orders", f"CALCULATE([Orders], '{F}'[Is Cancelled] = 0)", "#,0", D, "Orders that were not cancelled."),
    M("Late Orders", f"CALCULATE([Orders], '{F}'[Is Late] = 1)", "#,0", D),
    M("Late Delivery %", "DIVIDE([Late Orders], [Shipped Orders])", "0.0%", D,
      "Share of shipped orders with actual shipping days > scheduled days. Lower is better."),
    M("Late Delivery % PY", "CALCULATE([Late Delivery %], SAMEPERIODLASTYEAR('Date'[Date]))", "0.0%", D),
    M("On-Time Orders", f"CALCULATE([Orders], '{F}'[Is Late] = 0, '{F}'[Is Cancelled] = 0)", "#,0", D),
    M("On-Time Delivery %", "DIVIDE([On-Time Orders] + 0, [Shipped Orders])", "0.0%", D,
      "Share of shipped orders that shipped within the promised days. Higher is better."),
    M("On-Time Delivery % PY", "CALCULATE([On-Time Delivery %], SAMEPERIODLASTYEAR('Date'[Date]))", "0.0%", D),
    M("Avg Actual Ship Days", f"CALCULATE(AVERAGE('{F}'[Actual Ship Days]), '{F}'[Is Cancelled] = 0)", "0.00", D,
      "AC for delivery: average days from order to shipping."),
    M("Avg Promised Ship Days", f"CALCULATE(AVERAGE('{F}'[Scheduled Ship Days]), '{F}'[Is Cancelled] = 0)", "0.00", D,
      "PL for delivery: the shipping days promised to the customer (real data, not a built plan)."),
    M("Ship Days vs Promise", "[Avg Actual Ship Days] - [Avg Promised Ship Days]", "+0.00;-0.00;0.00", D,
      "Days late (+) or early (-) against the promise. Lower is better."),
])

product = Table("Product", "dim_product.csv", columns=[
    C("Product Id", "int64", hidden=True), C("Product Name"), C("Category"), C("Department"),
    C("List Price", "double", fmt=r"\$#,0.00", summarize="none")])
ship = Table("Shipping Mode", "dim_shipping_mode.csv", columns=[
    C("Shipping Mode", sort_by="Mode Sort"), C("Mode Sort", "int64", hidden=True),
    C("Planned Ship Days", "int64", summarize="none")])
date = Table("Date", "dim_date.csv", is_date=True, columns=[
    C("Date", "dateTime", fmt="yyyy-mm-dd", key=True), C("Year", "int64", fmt="0"),
    C("Quarter"), C("Year Quarter", sort_by="Year Quarter Key"), C("Year Quarter Key", "int64", hidden=True),
    C("Month Number", "int64", hidden=True), C("Month", sort_by="Month Number"),
    C("Year Month", sort_by="Year Month Key"), C("Year Month Key", "int64", hidden=True),
    C("Month Start", "dateTime", fmt="mmm yyyy", hidden=True)])

tables = [order_lines, plan, measures, product, ship, date]
rels = [R(F, "Order Date", "Date", "Date"), R(F, "Product Id", "Product", "Product Id"),
        R(F, "Shipping Mode", "Shipping Mode", "Shipping Mode"),
        R(P, "Plan Date", "Date", "Date"), R(P, "Product Id", "Product", "Product Id")]

# ----------------------------------------------------------------- report
m = lambda n: mea(K, n)  # noqa: E731
dept, category = col("Product", "Department"), col("Product", "Category")
mode, month = col("Shipping Mode", "Shipping Mode"), col("Date", "Month")
year2017 = cat_filter("Date", "Year", [2017], "year2017")


def zebra(x, y, w, h, cats, ac, title, py=None, pl=None, extra=None, invert=False, table=False):
    """Zebra BI Tables visual. table=False = chart view (free version); table=True and invert=True need Pro."""
    roles = {"Category": cats, "Values": [ac] + (extra or [])}
    if py:
        roles["PreviousYear"] = [py]
    if pl:
        roles["Plan"] = [pl]
    # months keep calendar order; other categories use the visual's default (largest actual first)
    v = Visual(ZEBRA_TABLES, x, y, w, h, roles=roles, sort=(cats[0], "Ascending") if cats[0] is month else None)
    # Zebra BI writes its own title from the field names; the text here is kept as the intended title.
    v.objects = {
        "titleSettings": [{"properties": props(show=True, text=title)}],
        "chartSettings": [{"properties": props(invert=invert, showAsTable=table, suppressZeros=False)}],
    }
    if cats[0] is month:   # Zebra BI sorts by value unless its own sort is set to None ("0")
        v.objects["sortSettings"] = [{"properties": props(chartSort="0", categorySort="0")}]
    v.container = {"title": [{"properties": props(show=False)}]}
    return v


def note(x, y, w, h, text):
    return textbox(x, y, w, h, [[(text, {"fontSize": "8.5pt", "color": GREY})]])


sales = Page("sales", "Sales vs PY and Plan", filters=[year2017], visuals=[
    header("Sales vs Previous Year and Plan", "DataCo · Jan–Sep 2017 · AC = actual, PY = Jan–Sep 2016, "
           "PL = illustrative plan (2016 + department growth target)"),
    slicer(1020, 12, 240, 52, dept, "Department"),
    kpi_row(20, 74, 1240, 96, [m("Net Sales"), m("Net Sales PL"), m("Net Sales vs PL %"), m("Net Sales PY"),
                               m("Net Sales vs PY %"), m("Profit vs PL %")],
            precision={"Net Sales": 2, "Net Sales PL": 2, "Net Sales PY": 2}),
    zebra(20, 180, 620, 250, [month], m("Net Sales"), "Net sales by month, AC vs plan", pl=m("Net Sales PL")),
    zebra(652, 180, 608, 250, [dept, category], m("Net Sales"),
          "Net sales by department vs plan (expand a department to see categories)", pl=m("Net Sales PL")),
    zebra(20, 442, 620, 250, [dept], m("Net Sales"), "Net sales by department, AC vs previous year",
          py=m("Net Sales PY")),
    findings_box(652, 442, 608, 250, "What the variance shows", [
        ("On plan in total:", "net sales +0.1% vs plan and +4.7% vs PY."),
        ("The core missed plan:", "Fan Shop −2.5%, Apparel −5.1%, Golf −3.6%. These three are 83% of sales."),
        ("Small departments filled the gap:", "Outdoors +91% and Fitness +70% vs plan, from products "
                                              "added in Q2–Q3 2017."),
        ("Action:", "the total hides a weak core. Review Fan Shop and Apparel pricing and range before "
                    "planning on Outdoors growth again."),
    ]),
    note(20, 696, 1240, 20, "Market and region are left out on purpose: in this dataset the market of the orders "
                            "changes from quarter to quarter, so a variance by market would only show that shift."),
])

delivery = Page("delivery", "Delivery vs Promise", filters=[year2017], visuals=[
    header("Delivery vs Promise", "Jan–Sep 2017 · on-time = shipped within the promised days · "
           "on-time % (not late %), so green means good"),
    slicer(1020, 12, 240, 52, dept, "Department"),
    kpi_row(20, 74, 1240, 96, [m("Shipped Orders"), m("On-Time Delivery %"), m("On-Time Delivery % PY"),
                               m("Avg Actual Ship Days"), m("Avg Promised Ship Days"), m("Ship Days vs Promise")]),
    zebra(20, 180, 620, 250, [mode], m("On-Time Delivery %"), "On-time delivery % by mode, AC vs PY",
          py=m("On-Time Delivery % PY")),
    Visual("clusteredColumnChart", 652, 180, 608, 250,
           roles={"Category": [mode], "Y": [m("Avg Promised Ship Days"), m("Avg Actual Ship Days")]},
           title="Promised vs actual shipping days by mode (built-in visual)",
           objects={"labels": [{"properties": props(show=True, fontSize=9.0)}]}),
    zebra(20, 442, 620, 250, [month], m("On-Time Delivery %"), "On-time delivery % by month, AC vs PY",
          py=m("On-Time Delivery % PY")),
    findings_box(652, 442, 608, 250, "What the variance shows", [
        ("First Class:", "2.0 days against a 1-day promise. 0% on time, both years."),
        ("Second Class:", "4.0 days against 2. 20% on time."),
        ("Standard Class:", "on promise (4.0 vs 4). 61% on time, the best mode."),
        ("Same Day got worse:", "on time down from 55% to 48% vs PY (−6.9 pp)."),
        ("Action:", "change the First and Second Class promises to real lead times, and look into "
                    "what changed for Same Day in 2017."),
    ]),
])

compare = Page("compare", "Built-in vs Zebra BI", filters=[year2017], visuals=[
    header("Same question, two visuals", "Net sales by department vs plan and PY · left: Power BI built-in · "
           "right: Zebra BI Tables"),
    Visual("clusteredBarChart", 20, 80, 400, 300,
           roles={"Category": [dept], "Y": [m("Net Sales PY"), m("Net Sales PL"), m("Net Sales")]},
           title="Built-in: clustered bar", sort=(m("Net Sales"), "Descending")),
    Visual("pivotTable", 20, 392, 400, 300,
           roles={"Rows": [dept], "Values": [m("Net Sales"), m("Net Sales vs PL %"), m("Net Sales vs PY %")]},
           title="Built-in: matrix"),
    zebra(432, 80, 520, 300, [dept, category], m("Net Sales"), "Zebra BI: AC vs plan", pl=m("Net Sales PL")),
    zebra(432, 392, 520, 300, [dept], m("Net Sales"), "Zebra BI: AC vs previous year", py=m("Net Sales PY")),
    findings_box(964, 80, 296, 612, "Why use Zebra BI here", [
        ("Variance is drawn, not read:", "red and green bars show the gap to plan and PY without "
                                         "comparing three bar lengths by eye."),
        ("Value and gap together:", "actual, variance and % variance in one visual, with a hierarchy "
                                    "you can expand."),
        ("Standard notation (IBCS):", "AC solid, PY grey, PL outlined. Finance readers know it."),
        ("Same measures:", "both sides use the same DAX measures, so the numbers match."),
        ("Cost:", "the free version allows two measures per visual, the chart view only, and no colour "
                  "invert. AC vs PL and PY in one table needs Pro. Check what the client has."),
    ], size="9pt"),
])

if __name__ == "__main__":
    write_model(ROOT / f"{NAME}.SemanticModel", PROJECT, NAME, DATA, tables, rels)
    write_report(ROOT / f"{NAME}.Report", PROJECT, NAME, f"{NAME}.SemanticModel", [sales, delivery, compare],
                 public_custom_visuals=[ZEBRA_TABLES])
    write_pbip(ROOT, NAME)
    print("built", ROOT / f"{NAME}.pbip")
