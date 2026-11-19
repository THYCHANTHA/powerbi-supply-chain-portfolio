"""Build the Supply Chain Performance Power BI project (TMDL model + PBIR report)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "_tools"))
from pbip_builder import (AMBER, GREY, INK, NAVY, RED, TEAL, Column as C, Measure as M, Page,  # noqa: E402
                          Relationship as R, Table, Visual, col, header, kpi_row, mea, props, slicer,
                          textbox, topn_filter, write_model, write_pbip, write_report)

NAME = "Supply Chain Performance"
PROJECT = "portfolio/supply-chain"
DATA = str(ROOT / "data" / "clean")
F = "Order Lines"
K = "Key Measures"

# ------------------------------------------------------------------ model
order_lines = Table(F, "fact_order_lines.csv", description="One row per order line (DataCo, Jan 2015 - Sep 2017).", columns=[
    C("Order Line Id", "int64", hidden=True), C("Order Id", "int64", fmt="0"),
    C("Order Date", "dateTime", fmt="yyyy-mm-dd"), C("Ship Date", "dateTime", fmt="yyyy-mm-dd"),
    C("Customer Id", "int64", hidden=True), C("Product Id", "int64", hidden=True),
    C("Region Id", "int64", hidden=True), C("Shipping Mode", "string", hidden=True),
    C("Delivery Status"), C("Order Status"), C("Payment Type"),
    C("Is Late", "int64", hidden=True), C("Is Cancelled", "int64", hidden=True),
    C("Actual Ship Days", "int64", hidden=True), C("Scheduled Ship Days", "int64", hidden=True),
    C("Quantity", "int64", hidden=True), C("Gross Sales", "double", hidden=True),
    C("Discount", "double", hidden=True), C("Net Sales", "double", hidden=True),
    C("Profit", "double", hidden=True), C("Delay Days", "int64", hidden=True),
])

S, D = "1. Sales and Profit", "2. Delivery Performance"
measures = Table(K, None, columns=[C("Placeholder", hidden=True)],
                 m_source='let\n    Source = #table(type table [Placeholder = text], {})\nin\n    Source',
                 description="All report measures live here.", measures=[
    M("Net Sales", f"SUM('{F}'[Net Sales])", r"\$#,0", S, "Sales after discount."),
    M("Gross Sales", f"SUM('{F}'[Gross Sales])", r"\$#,0", S),
    M("Discount %", f"DIVIDE(SUM('{F}'[Discount]), [Gross Sales])", "0.0%", S),
    M("Profit", f"SUM('{F}'[Profit])", r"\$#,0", S),
    M("Profit Margin %", "DIVIDE([Profit], [Net Sales])", "0.0%", S),
    M("Orders", f"DISTINCTCOUNT('{F}'[Order Id])", "#,0", S),
    M("Units", f"SUM('{F}'[Quantity])", "#,0", S),
    M("Avg Order Value", "DIVIDE([Net Sales], [Orders])", r"\$#,0.00", S),
    M("Net Sales PY", "CALCULATE([Net Sales], SAMEPERIODLASTYEAR('Date'[Date]))", r"\$#,0", S),
    M("Net Sales YoY %", "VAR PY = [Net Sales PY]\nRETURN IF(NOT ISBLANK(PY), DIVIDE([Net Sales] - PY, PY))", "+0.0%;-0.0%;0.0%", S),
    M("Shipped Orders", f"CALCULATE([Orders], '{F}'[Is Cancelled] = 0)", "#,0", D, "Orders that were not cancelled."),
    M("Late Orders", f"CALCULATE([Orders], '{F}'[Is Late] = 1)", "#,0", D),
    M("On-Time Orders", f"CALCULATE([Orders], '{F}'[Is Late] = 0, '{F}'[Is Cancelled] = 0)", "#,0", D),
    M("On-Time Delivery %", "DIVIDE([On-Time Orders], [Shipped Orders])", "0.0%", D,
      "Share of shipped orders that shipped within the scheduled days."),
    M("Late Delivery %", "DIVIDE([Late Orders], [Shipped Orders])", "0.0%", D),
    M("Cancelled Orders %", f"DIVIDE(CALCULATE([Orders], '{F}'[Is Cancelled] = 1), [Orders])", "0.0%", D),
    M("Avg Actual Ship Days", f"CALCULATE(AVERAGE('{F}'[Actual Ship Days]), '{F}'[Is Cancelled] = 0)", "0.0", D),
    M("Avg Scheduled Ship Days", f"CALCULATE(AVERAGE('{F}'[Scheduled Ship Days]), '{F}'[Is Cancelled] = 0)", "0.0", D),
    M("Ship Days vs Plan", "[Avg Actual Ship Days] - [Avg Scheduled Ship Days]", "+0.0;-0.0;0.0", D,
      "Average days late (+) or early (-) compared with the promised shipping days."),
    M("Avg Delay (Late Orders)", f"CALCULATE(AVERAGE('{F}'[Delay Days]), '{F}'[Is Late] = 1)", "0.0", D),
    M("Net Sales of Late Orders", f"CALCULATE([Net Sales], '{F}'[Is Late] = 1)", r"\$#,0", D,
      "Revenue tied to orders that shipped late (customer experience at risk)."),
    M("Late Sales %", "DIVIDE([Net Sales of Late Orders], [Net Sales])", "0.0%", D),
])

product = Table("Product", "dim_product.csv", columns=[
    C("Product Id", "int64", hidden=True), C("Product Name"), C("Category"), C("Department"),
    C("List Price", "double", fmt=r"\$#,0.00", summarize="none")])
customer = Table("Customer", "dim_customer.csv", columns=[
    C("Customer Id", "int64", hidden=True), C("Segment"), C("State"), C("Country", category="Country")])
region = Table("Region", "dim_region.csv", columns=[
    C("Region Id", "int64", hidden=True), C("Market"), C("Region")])
ship = Table("Shipping Mode", "dim_shipping_mode.csv", columns=[
    C("Shipping Mode", sort_by="Mode Sort"), C("Mode Sort", "int64", hidden=True),
    C("Planned Ship Days", "int64", summarize="none")])
date = Table("Date", "dim_date.csv", is_date=True, columns=[
    C("Date", "dateTime", fmt="yyyy-mm-dd", key=True), C("Year", "int64", fmt="0"),
    C("Quarter"), C("Year Quarter", sort_by="Year Quarter Key"), C("Year Quarter Key", "int64", hidden=True),
    C("Month Number", "int64", hidden=True), C("Month", sort_by="Month Number"),
    C("Year Month", sort_by="Year Month Key"), C("Year Month Key", "int64", hidden=True),
    C("Month Start", "dateTime", fmt="mmm yyyy", hidden=True)])

tables = [order_lines, measures, product, customer, region, ship, date]
rels = [R(F, "Order Date", "Date", "Date"), R(F, "Product Id", "Product", "Product Id"),
        R(F, "Customer Id", "Customer", "Customer Id"), R(F, "Region Id", "Region", "Region Id"),
        R(F, "Shipping Mode", "Shipping Mode", "Shipping Mode")]

# ----------------------------------------------------------------- report
m = lambda n: mea(K, n)  # noqa: E731
year, market, mode = col("Date", "Year"), col("Region", "Market"), col("Shipping Mode", "Shipping Mode")


def slicers():
    return [slicer(800, 12, 150, 52, year, "Year"), slicer(960, 12, 150, 52, market, "Market"),
            slicer(1120, 12, 140, 52, mode, "Shipping Mode")]


def bar(x, y, w, h, cat, meas, title, vtype="clusteredBarChart", series=None, top=None, labels=True):
    roles = {"Category": [cat], "Y": meas if isinstance(meas, list) else [meas]}
    if series:
        roles["Series"] = [series]
    v = Visual(vtype, x, y, w, h, roles=roles, title=title,
               sort=((meas[0] if isinstance(meas, list) else meas), "Descending"))
    if labels:
        v.objects = {"labels": [{"properties": props(show=True, fontSize=9.0)}]}
    if top:
        inner = cat["Column"]
        v.filters = [topn_filter(inner["Expression"]["SourceRef"]["Entity"], inner["Property"], K,
                                 (meas[0] if isinstance(meas, list) else meas)["Measure"]["Property"], top,
                                 f"top{top}{inner['Property'].replace(' ', '')}")]
    return v


def findings(x, y, w, h, title, items):
    paras = [[(title, {"fontWeight": "bold", "fontSize": "12pt", "color": NAVY})]]
    for head, body in items:
        paras.append([("■ " + head + " ", {"fontWeight": "bold", "fontSize": "9.5pt", "color": INK}),
                      (body, {"fontSize": "9.5pt", "color": GREY})])
    v = textbox(x, y, w, h, paras)
    v.container["background"] = [{"properties": props(show=True, color="#FFFFFF", transparency=0.0)}]
    v.container["border"] = [{"properties": props(show=True, color="#E3E8EF", radius=8.0)}]
    return v


overview = Page("overview", "Overview", [
    header("Supply Chain Performance", "DataCo global orders · Jan 2015 – Sep 2017 · 65k orders, 172k order lines"),
    *slicers(),
    kpi_row(20, 74, 1240, 100, [m("Net Sales"), m("Orders"), m("Profit Margin %"), m("On-Time Delivery %"),
                                m("Avg Actual Ship Days"), m("Net Sales of Late Orders")],
            precision={"Net Sales": 1, "Net Sales of Late Orders": 1}),
    Visual("lineClusteredColumnComboChart", 20, 186, 800, 258,
           roles={"Category": [col("Date", "Year Month")], "Y": [m("Net Sales")], "Y2": [m("Late Delivery %")]},
           title="Net Sales and Late Delivery % by Month"),
    bar(832, 186, 428, 258, mode, m("Late Delivery %"), "Late Delivery % by Shipping Mode"),
    bar(20, 456, 400, 248, market, m("Net Sales"), "Net Sales by Market"),
    bar(432, 456, 400, 248, col("Region", "Region"), m("Late Delivery %"), "Top 10 Regions by Late Delivery %", top=10),
    findings(844, 456, 416, 248, "Key findings", [
        ("57% of shipped orders are late,", "in every market (52–60% by region)."),
        ("First Class: 100% late.", "Promise 1 day, actual 2."),
        ("Second Class: 80% late.", "Promise 2 days, actual 4."),
        ("Standard Class: 40% late.", "Meets its 4-day promise best."),
        ("Action:", "the cause is the promise per mode, not location. Reset First and Second Class "
                    "promises to real lead times or fix the carrier step."),
    ]),
])

delivery = Page("delivery", "Delivery Performance", [
    header("Delivery Performance", "Are we shipping when we promised? Late = actual shipping days > scheduled days"),
    *slicers(),
    kpi_row(20, 74, 1240, 100, [m("Shipped Orders"), m("On-Time Delivery %"), m("Late Orders"),
                                m("Avg Actual Ship Days"), m("Avg Scheduled Ship Days"), m("Avg Delay (Late Orders)")]),
    bar(20, 186, 620, 258, mode, [m("Avg Scheduled Ship Days"), m("Avg Actual Ship Days")],
        "Promised vs Actual Shipping Days by Mode", vtype="clusteredColumnChart"),
    Visual("donutChart", 652, 186, 300, 258, roles={"Category": [col(F, "Delivery Status")], "Y": [m("Orders")]},
           title="Orders by Delivery Status"),
    bar(964, 186, 296, 258, col("Customer", "Segment"), m("Late Delivery %"), "Late Delivery % by Segment"),
    Visual("pivotTable", 20, 456, 640, 248,
           roles={"Rows": [market, col("Region", "Region")], "Columns": [mode], "Values": [m("Late Delivery %")]},
           title="Late Delivery % by Market, Region and Shipping Mode"),
    Visual("lineChart", 672, 456, 588, 248,
           roles={"Category": [col("Date", "Year Quarter")], "Y": [m("On-Time Delivery %")], "Series": [mode]},
           title="On-Time Delivery % by Quarter and Shipping Mode"),
])

products = Page("products", "Products and Customers", [
    header("Products and Customers", "Where the revenue and profit come from, and which products ship late"),
    *slicers(),
    kpi_row(20, 74, 1240, 100, [m("Net Sales"), m("Profit"), m("Profit Margin %"), m("Units"),
                                m("Avg Order Value"), m("Discount %")], precision={"Net Sales": 1, "Profit": 2}),
    bar(20, 186, 410, 258, col("Product", "Department"), m("Net Sales"), "Net Sales by Department"),
    bar(442, 186, 410, 258, col("Product", "Category"), m("Profit"), "Top 10 Categories by Profit", top=10),
    Visual("donutChart", 864, 186, 396, 258, roles={"Category": [col("Customer", "Segment")], "Y": [m("Net Sales")]},
           title="Net Sales by Customer Segment"),
    Visual("tableEx", 20, 456, 1240, 248,
           roles={"Values": [col("Product", "Product Name"), col("Product", "Category"), m("Units"), m("Net Sales"),
                             m("Profit Margin %"), m("Late Delivery %"), m("Net Sales of Late Orders")]},
           title="Product Detail", sort=(m("Net Sales"), "Descending")),
])

if __name__ == "__main__":
    write_model(ROOT / f"{NAME}.SemanticModel", PROJECT, NAME, DATA, tables, rels)
    write_report(ROOT / f"{NAME}.Report", PROJECT, NAME, f"{NAME}.SemanticModel", [overview, delivery, products])
    write_pbip(ROOT, NAME)
    print("built", ROOT / f"{NAME}.pbip")
