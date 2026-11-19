"""Build the Procurement and Supplier Performance Power BI project (TMDL model + PBIR report)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "_tools"))
from pbip_builder import (Column as C, Measure as M, Page, Relationship as R, Table, Visual,  # noqa: E402
                          bar_chart, col, date_table, findings_box, header, kpi_row, mea, measure_table,
                          slicer, cat_filter, write_model, write_pbip, write_report)

NAME = "Procurement and Supplier Performance"
PROJECT = "portfolio/procurement"
DATA = str(ROOT / "data" / "clean")
F = "Shipment Lines"
K = "Key Measures"

lines = Table(F, "fact_shipment_lines.csv",
              description="One row per shipment line (USAID SCMS health commodities, 2006-2015).", columns=[
    C("Line Id", "int64", hidden=True), C("Project Code"), C("PO Number"), C("Shipment Number"),
    C("Country", hidden=True), C("Vendor", hidden=True), C("Item Id", "int64", hidden=True),
    C("Shipment Mode"), C("Fulfill Via"), C("INCO Term"),
    C("Scheduled Date", "dateTime", fmt="yyyy-mm-dd"), C("Delivered Date", "dateTime", fmt="yyyy-mm-dd"),
    C("PO Date", "dateTime", fmt="yyyy-mm-dd"),
    C("Quantity", "int64", hidden=True), C("Line Value", "double", hidden=True),
    C("Pack Price", "double", hidden=True), C("Benchmark Value", "double", hidden=True),
    C("Price Variance", "double", hidden=True), C("Weight Kg", "double", hidden=True),
    C("Freight USD", "double", hidden=True), C("Insurance USD", "double", hidden=True),
    C("Freight Status"), C("Days Late", "int64", hidden=True), C("Is Late", "int64", hidden=True),
    C("PO to Delivery Days", "int64", hidden=True), C("Freight For Rate", "double", hidden=True),
    C("Weight For Rate", "double", hidden=True), C("Value With Freight", "double", hidden=True),
])

S, D, FR, P = "1. Spend", "2. Delivery", "3. Freight", "4. Price"
measures = measure_table(K, [
    M("Total Spend", f"SUM('{F}'[Line Value])", r"\$#,0", S, "Value of goods purchased (commodity cost)."),
    M("Purchase Orders", f"DISTINCTCOUNT('{F}'[PO Number])", "#,0", S),
    M("Shipment Lines", f"COUNTROWS('{F}')", "#,0", S),
    M("Active Suppliers", f"CALCULATE(DISTINCTCOUNT('{F}'[Vendor]), Vendor[Supplier Type] = \"Direct supplier\")",
      "#,0", S, "Direct suppliers only (excludes Regional Distribution Centre)."),
    M("Spend Share %", f"DIVIDE([Total Spend], CALCULATE([Total Spend], ALLSELECTED(Vendor)))", "0.0%", S),
    M("Top 5 Supplier Share %",
      "VAR t = ADDCOLUMNS(CALCULATETABLE(VALUES(Vendor[Supplier]), Vendor[Supplier Type] = \"Direct supplier\"),"
      " \"@s\", [Total Spend])\nRETURN DIVIDE(SUMX(TOPN(5, t, [@s]), [@s]), SUMX(t, [@s]))", "0.0%", S,
      "Share of direct-supplier spend that goes to the five largest suppliers (concentration risk)."),
    M("Cumulative Spend %",
      "VAR cur = [Total Spend]\nVAR t = ADDCOLUMNS(ALLSELECTED(Vendor[Supplier]), \"@s\", [Total Spend])\n"
      "RETURN IF(NOT ISBLANK(cur), DIVIDE(SUMX(FILTER(t, [@s] >= cur), [@s]), SUMX(t, [@s])))", "0%", S,
      "Running share of spend by supplier, largest first (Pareto)."),
    M("On-Time Delivery %", f"DIVIDE(CALCULATE(COUNTROWS('{F}'), '{F}'[Is Late] = 0), COUNTROWS('{F}'))", "0.0%", D,
      "Share of lines delivered on or before the scheduled date."),
    M("Late Shipments", f"CALCULATE(COUNTROWS('{F}'), '{F}'[Is Late] = 1)", "#,0", D),
    M("Avg Days Late", f"CALCULATE(AVERAGE('{F}'[Days Late]), '{F}'[Is Late] = 1)", "0.0", D,
      "Average days late, for late lines only."),
    M("Avg PO to Delivery Days", f"AVERAGE('{F}'[PO to Delivery Days])", "0", D,
      "Days from purchase order to delivery (only lines where the PO date was recorded)."),
    M("Freight Cost", f"SUM('{F}'[Freight USD])", r"\$#,0", FR),
    M("Freight % of Value", f"DIVIDE(SUM('{F}'[Freight USD]), SUM('{F}'[Value With Freight]))", "0.0%", FR,
      "Freight as a share of goods value, on lines where freight was charged separately."),
    M("Freight per Kg", f"DIVIDE(SUM('{F}'[Freight For Rate]), SUM('{F}'[Weight For Rate]))", r"\$#,0.00", FR),
    M("Insurance Cost", f"SUM('{F}'[Insurance USD])", r"\$#,0", FR),
    M("Air Share %", f"DIVIDE(CALCULATE(COUNTROWS('{F}'), '{F}'[Shipment Mode] IN {{\"Air\", \"Air Charter\"}}),"
      f" COUNTROWS('{F}'))", "0.0%", FR),
    M("Paid Above Benchmark", f"SUMX(FILTER('{F}', '{F}'[Price Variance] > 0), '{F}'[Price Variance])", r"\$#,0", P,
      "Amount paid above the same-year average price for the same item."),
    M("Price vs Benchmark %", f"DIVIDE(SUM('{F}'[Line Value]), SUM('{F}'[Benchmark Value])) - 1",
      "+0.0%;-0.0%;0.0%", P, "Positive = paid more than the same-year average price for the same items."),
])

vendor = Table("Vendor", "dim_vendor.csv", columns=[C("Vendor"), C("Supplier Type"), C("Supplier")])
item = Table("Item", "dim_item.csv", columns=[
    C("Item Id", "int64", hidden=True), C("Item"), C("Product Group"), C("Sub Classification"),
    C("Molecule or Test"), C("Brand"), C("Dosage Form"), C("First Line Drug")])
country = Table("Country", "dim_country.csv", columns=[C("Country", category="Country"), C("Region")])

tables = [lines, measures, vendor, item, country, date_table()]
rels = [R(F, "Delivered Date", "Date", "Date"), R(F, "Vendor", "Vendor", "Vendor"),
        R(F, "Item Id", "Item", "Item Id"), R(F, "Country", "Country", "Country")]

m = lambda n: mea(K, n)  # noqa: E731
year, group, region = col("Date", "Year"), col("Item", "Product Group"), col("Country", "Region")
supplier, mode = col("Vendor", "Supplier"), col(F, "Shipment Mode")
DIRECT = cat_filter("Vendor", "Supplier Type", ["Direct supplier"], "directOnly")


def with_filter(v, f):
    v.filters = v.filters + [f]
    return v


def slicers():
    return [slicer(800, 12, 150, 52, year, "Year"), slicer(960, 12, 150, 52, group, "Product Group"),
            slicer(1120, 12, 140, 52, region, "Region")]


spend = Page("spend", "Spend Overview", [
    header("Procurement Spend Overview", "USAID SCMS health commodity purchases · 2006–2015 · 43 countries · 73 suppliers"),
    *slicers(),
    kpi_row(20, 74, 1240, 100, [m("Total Spend"), m("Purchase Orders"), m("Active Suppliers"),
                                m("Top 5 Supplier Share %"), m("On-Time Delivery %"), m("Paid Above Benchmark")],
            precision={"Total Spend": 2, "Paid Above Benchmark": 1}),
    bar_chart(20, 186, 600, 258, year, m("Total Spend"), "Spend by Year and Product Group",
              vtype="columnChart", series=group, labels=False, sort_desc=False),
    Visual("lineClusteredColumnComboChart", 632, 186, 628, 258,
           roles={"Category": [supplier], "Y": [m("Total Spend")], "Y2": [m("Cumulative Spend %")]},
           title="Supplier Pareto: Direct Suppliers, Spend and Cumulative Share (Top 15)",
           sort=(m("Total Spend"), "Descending"),
           filters=bar_chart(0, 0, 0, 0, supplier, m("Total Spend"), "", top=15).filters + [DIRECT]),
    bar_chart(20, 456, 400, 248, col("Country", "Country"), m("Total Spend"), "Top 10 Countries by Spend", top=10),
    Visual("donutChart", 432, 456, 400, 248, roles={"Category": [group], "Y": [m("Total Spend")]},
           title="Spend by Product Group"),
    findings_box(844, 456, 416, 248, "Key findings", [
        ("Concentration risk:", "7 suppliers make 80% of direct spend; the top 5 alone make 73%."),
        ("Channel:", "direct drop lines arrive on time 94.7% of the time vs 82.8% from distribution centres."),
        ("Price:", "$35.9M (2.2% of spend) was paid above the same-year average price for the same item."),
        ("Action:", "add second sources for the top items and use price benchmarks in negotiations."),
    ]),
])

suppliers = Page("suppliers", "Supplier Performance", [
    header("Supplier Performance", "Delivery reliability and price competitiveness by supplier"),
    *slicers(),
    kpi_row(20, 74, 1240, 100, [m("Active Suppliers"), m("On-Time Delivery %"), m("Late Shipments"),
                                m("Avg Days Late"), m("Avg PO to Delivery Days"), m("Paid Above Benchmark")],
            precision={"Paid Above Benchmark": 1}),
    Visual("tableEx", 20, 186, 820, 258,
           roles={"Values": [supplier, col("Vendor", "Supplier Type"), m("Total Spend"), m("Spend Share %"),
                             m("Shipment Lines"), m("On-Time Delivery %"), m("Avg Days Late"),
                             m("Price vs Benchmark %"), m("Paid Above Benchmark")]},
           title="Supplier Scorecard", sort=(m("Total Spend"), "Descending")),
    bar_chart(852, 186, 408, 258, col(F, "Fulfill Via"), m("On-Time Delivery %"), "On-Time Delivery % by Channel",
              vtype="clusteredColumnChart"),
    Visual("lineChart", 20, 456, 620, 248,
           roles={"Category": [year], "Y": [m("On-Time Delivery %")], "Series": [col(F, "Fulfill Via")]},
           title="On-Time Delivery % by Year and Channel"),
    with_filter(bar_chart(652, 456, 608, 248, supplier, m("Late Shipments"), "Top 10 Direct Suppliers by Late Shipments",
                          top=10), DIRECT),
])

freight = Page("freight", "Freight and Logistics", [
    header("Freight and Logistics", "What does it cost to move the goods, and which mode is worth it?"),
    *slicers(),
    kpi_row(20, 74, 1240, 100, [m("Freight Cost"), m("Freight % of Value"), m("Freight per Kg"),
                                m("Air Share %"), m("Insurance Cost"), m("Avg Days Late")],
            precision={"Freight Cost": 1, "Insurance Cost": 1}),
    bar_chart(20, 186, 410, 258, mode, m("Freight per Kg"), "Freight Cost per Kg by Shipment Mode"),
    bar_chart(442, 186, 818, 258, year, m("Freight Cost"), "Freight Cost by Year and Shipment Mode",
              vtype="columnChart", series=mode, labels=False, sort_desc=False),
    Visual("pivotTable", 20, 456, 620, 248,
           roles={"Rows": [region, col("Country", "Country")], "Columns": [mode], "Values": [m("Freight per Kg")]},
           title="Freight per Kg by Region, Country and Mode"),
    Visual("donutChart", 652, 456, 280, 248, roles={"Category": [col(F, "Freight Status")], "Y": [m("Shipment Lines")]},
           title="Lines by Freight Status"),
    findings_box(944, 456, 316, 248, "Key findings", [
        ("Air costs $5.26/kg,", "about 3x truck ($1.59) and ocean ($1.85)."),
        ("Most lines fly:", "about 65% go by air or air charter."),
        ("Action:", "order earlier on stable items so more volume can move by ocean or truck."),
    ]),
])

if __name__ == "__main__":
    write_model(ROOT / f"{NAME}.SemanticModel", PROJECT, NAME, DATA, tables, rels)
    write_report(ROOT / f"{NAME}.Report", PROJECT, NAME, f"{NAME}.SemanticModel", [spend, suppliers, freight])
    write_pbip(ROOT, NAME)
    print("built", ROOT / f"{NAME}.pbip")
