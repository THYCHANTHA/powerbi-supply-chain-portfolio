"""Build the Demand Forecasting and Inventory Planning Power BI project (TMDL model + PBIR report)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "_tools"))
from pbip_builder import (Column as C, Measure as M, Page, Relationship as R, Table, Visual,  # noqa: E402
                          bar_chart, cat_filter, col, findings_box, header, kpi_row, mea, measure_table, props,
                          slicer, write_model, write_pbip, write_report)

NAME = "Demand Forecasting and Inventory Planning"
PROJECT = "portfolio/demand-forecasting"
DATA = str(ROOT / "data" / "clean")
K = "Key Measures"
WS, FC, ACC = "Weekly Sales", "Forecast", "Model Accuracy"

weekly = Table(WS, "fact_weekly_sales.csv", description="Units and revenue per product per week (Mon start).", columns=[
    C("Week Start", "dateTime", fmt="yyyy-mm-dd", hidden=True), C("StockCode", hidden=True),
    C("Units", "int64", hidden=True), C("Revenue", "double", hidden=True), C("Orders", "int64", hidden=True)])
forecast = Table(FC, "fact_forecast.csv", description="Forecasts per model: Test = last 13 weeks, Future = next 8.", columns=[
    C("Week Start", "dateTime", fmt="yyyy-mm-dd", hidden=True), C("StockCode", hidden=True),
    C("Model", hidden=True), C("Forecast Units", "double", hidden=True), C("Set")])
accuracy = Table(ACC, "fact_model_accuracy.csv", description="Test-window accuracy per product and model.", columns=[
    C("StockCode", hidden=True), C("Model", hidden=True), C("Actual Units", "double", hidden=True),
    C("Abs Error", "double", hidden=True), C("Error", "double", hidden=True), C("WAPE", "double", hidden=True),
    C("MAPE", "double", hidden=True), C("RMSE", "double", hidden=True), C("Is Best", "int64", hidden=True),
    C("Val WAPE", "double", hidden=True)])

SEL = f"CALCULATE(MAX('{ACC}'[Model]), '{ACC}'[Is Best] = 1, REMOVEFILTERS('Product'), REMOVEFILTERS('Model'))"
D, F_, P = "1. Demand", "2. Forecast accuracy", "3. Inventory plan"
measures = measure_table(K, [
    M("Revenue", f"SUM('{WS}'[Revenue])", "£#,0", D),
    M("Units Sold", f"SUM('{WS}'[Units])", "#,0", D),
    M("Orders", f"SUM('{WS}'[Orders])", "#,0", D, "Invoice lines per product-week (an invoice with 3 products counts 3)."),
    M("Active Products", f"DISTINCTCOUNT('{WS}'[StockCode])", "#,0", D),
    M("Avg Weekly Revenue", "AVERAGEX(VALUES('Week'[Week Start]), [Revenue])", "£#,0", D),
    M("Revenue Share %", "DIVIDE([Revenue], CALCULATE([Revenue], ALLSELECTED('Product')))", "0.0%", D),
    M("Actual Units", "[Units Sold]", "#,0", F_),
    M("Selected Model", SEL, None, F_, "Model chosen for all products on the validation window."),
    M("Forecast Units",
      f"IF(HASONEVALUE('Model'[Model]), SUM('{FC}'[Forecast Units]),\n"
      f"    VAR sel = {SEL}\n    RETURN CALCULATE(SUM('{FC}'[Forecast Units]), '{FC}'[Model] = sel))", "#,0", F_,
      "Forecast of the model picked in the Model slicer, or of the selected model when none is picked."),
    M("WAPE", f"DIVIDE(SUM('{ACC}'[Abs Error]), SUM('{ACC}'[Actual Units]))", "0.0%", F_,
      "Weighted absolute percentage error on the 13 test weeks: sum of |forecast - actual| / sum of actual."),
    M("WAPE (Selected Model)", f"CALCULATE([WAPE], '{ACC}'[Is Best] = 1)", "0.0%", F_),
    M("Forecast Accuracy %", "1 - [WAPE (Selected Model)]", "0.0%", F_),
    M("Bias %", f"CALCULATE(DIVIDE(SUM('{ACC}'[Error]), SUM('{ACC}'[Actual Units])), '{ACC}'[Is Best] = 1)",
      "+0.0%;-0.0%;0.0%", F_, "Negative = forecast too low (under-forecast)."),
    M("Less Error vs Baseline",
      "1 - DIVIDE([WAPE (Selected Model)], CALCULATE([WAPE], 'Model'[Model] = \"Seasonal naive\"))", "0.0%", F_, "How much lower the WAPE is than the seasonal-naive baseline (same week last year)."),
    M("Products Forecasted", f"DISTINCTCOUNT('{ACC}'[StockCode])", "#,0", F_),
    M("Service Level Z", "SELECTEDVALUE('Service Level'[Z], 1.6449)", "0.00", P),
    M("Service Level", "SELECTEDVALUE('Service Level'[Service Level], \"95%\")", None, P),
    M("Lead Time (Weeks)", "SELECTEDVALUE('Lead Time'[Lead Time Weeks], 2)", "0", P),
    M("Forecast RMSE", f"CALCULATE(SUM('{ACC}'[RMSE]), '{ACC}'[Is Best] = 1)", "#,0", P,
      "Typical weekly forecast error (root mean squared error on the test weeks)."),
    M("Avg Weekly Forecast",
      f"VAR sel = {SEL}\nRETURN SUMX(VALUES('Product'[StockCode]),\n"
      f"    CALCULATE(AVERAGE('{FC}'[Forecast Units]), '{FC}'[Set] = \"Future\", '{FC}'[Model] = sel, REMOVEFILTERS('Week')))",
      "#,0", P, "Average of the next 8 weeks of forecast."),
    M("Safety Stock",
      "VAR z = [Service Level Z]\nVAR lt = [Lead Time (Weeks)]\nRETURN SUMX(VALUES('Product'[StockCode]), z * [Forecast RMSE] * SQRT(lt))",
      "#,0", P, "Z x forecast RMSE x square root of lead time (weeks)."),
    M("Reorder Point",
      "VAR lt = [Lead Time (Weeks)]\nRETURN SUMX(VALUES('Product'[StockCode]), [Avg Weekly Forecast] * lt + [Safety Stock])",
      "#,0", P, "Order again when stock falls to this level: demand during lead time + safety stock."),
])

product = Table("Product", "dim_product.csv", columns=[
    C("StockCode"), C("Description"), C("ABC Class"), C("XYZ Class"), C("ABC-XYZ"),
    C("Revenue Rank", "int64", summarize="none"), C("Weeks Selling", "int64", summarize="none"), C("Is Forecasted")])
week = Table("Week", "dim_week.csv", columns=[
    C("Week Start", "dateTime", fmt="dd mmm yyyy"), C("Year", "int64", fmt="0"), C("ISO Week", "int64", summarize="none"),
    C("Month Number", "int64", hidden=True), C("Month", sort_by="Month Number"),
    C("Year Month", sort_by="Year Month Key"), C("Year Month Key", "int64", hidden=True),
    C("Period"), C("In Forecast View")])
model = Table("Model", "dim_model.csv", columns=[C("Model", sort_by="Model Sort"), C("Model Type"),
                                                 C("Model Sort", "int64", hidden=True)])
service = Table("Service Level", "dim_service_level.csv", description="What-if: target cycle service level.", columns=[
    C("Service Level", sort_by="Service Level Value"), C("Service Level Value", "double", hidden=True),
    C("Z", "double", summarize="none")])
lead = Table("Lead Time", "dim_lead_time.csv", description="What-if: supplier lead time in weeks.",
             columns=[C("Lead Time Weeks", "int64", summarize="none")])

tables = [weekly, forecast, accuracy, measures, product, week, model, service, lead]
rels = [R(WS, "Week Start", "Week", "Week Start"), R(WS, "StockCode", "Product", "StockCode"),
        R(FC, "Week Start", "Week", "Week Start"), R(FC, "StockCode", "Product", "StockCode"),
        R(FC, "Model", "Model", "Model"), R(ACC, "StockCode", "Product", "StockCode"),
        R(ACC, "Model", "Model", "Model")]

m = lambda n: mea(K, n)  # noqa: E731
prod, abc_xyz = col("Product", "Description"), col("Product", "ABC-XYZ")
only_forecasted = [cat_filter("Product", "Is Forecasted", ["Yes"], "onlyForecasted")]


def single(v):
    v.objects.setdefault("selection", [{"properties": props(singleSelect=True)}])
    return v


demand = Page("demand", "Demand Overview", [
    header("Demand Overview", "UK online gift retailer · weekly sales Dec 2009 – Nov 2011 · 4,699 products"),
    slicer(800, 12, 150, 52, col("Week", "Year"), "Year"), slicer(960, 12, 150, 52, col("Product", "ABC Class"), "ABC"),
    slicer(1120, 12, 140, 52, col("Product", "XYZ Class"), "XYZ"),
    kpi_row(20, 74, 1240, 100, [m("Revenue"), m("Units Sold"), m("Active Products"), m("Avg Weekly Revenue"),
                                m("Orders")], precision={"Revenue": 2, "Units Sold": 1}),
    Visual("lineChart", 20, 186, 800, 258, roles={"Category": [col("Week", "Week Start")], "Y": [m("Revenue")]},
           title="Weekly Revenue"),
    bar_chart(832, 186, 428, 258, col("Week", "Month"), m("Revenue"), "Revenue by Month and Year",
              vtype="clusteredColumnChart", series=col("Week", "Year"), labels=False, sort_desc=False),
    Visual("pivotTable", 20, 456, 400, 248,
           roles={"Rows": [col("Product", "ABC Class")], "Columns": [col("Product", "XYZ Class")],
                  "Values": [m("Revenue Share %")]},
           title="Revenue Share by ABC (value) and XYZ (variability)"),
    bar_chart(432, 456, 400, 248, prod, m("Revenue"), "Top 10 Products by Revenue", top=10),
    findings_box(844, 456, 416, 248, "Key findings", [
        ("Strong seasonality:", "Sep–Nov bring 39% of yearly revenue; November alone 17.5%."),
        ("80/20:", "18% of products (class A) make 80% of revenue."),
        ("Volatile demand:", "28 of the top 30 products are Y or Z (high week-to-week variation), "
                             "so safety stock matters more than a perfect forecast."),
    ]),
])

accuracy_page = Page("accuracy", "Forecast Accuracy", filters=only_forecasted, visuals=[
    header("Forecast Accuracy", "30 top products · test = last 13 weeks (5 Sep – 28 Nov 2011) · model chosen on the 13 weeks before"),
    slicer(800, 12, 230, 52, prod, "Product"), slicer(1040, 12, 220, 52, col("Model", "Model"), "Model"),
    kpi_row(20, 74, 1240, 100, [m("Selected Model"), m("Forecast Accuracy %"), m("WAPE (Selected Model)"),
                                m("Bias %"), m("Less Error vs Baseline"), m("Products Forecasted")],
            font={"Selected Model": 13}),
    Visual("lineChart", 20, 186, 820, 258,
           roles={"Category": [col("Week", "Week Start")], "Y": [m("Actual Units"), m("Forecast Units")]},
           title="Actual vs Forecast Units (test weeks + next 8 weeks)",
           filters=[cat_filter("Week", "In Forecast View", ["Yes"], "forecastView")]),
    bar_chart(852, 186, 408, 258, col("Model", "Model"), m("WAPE"), "Test Error (WAPE) by Model · lower is better",
              sort_desc=False),
    Visual("tableEx", 20, 456, 820, 248,
           roles={"Values": [prod, abc_xyz, m("Actual Units"), m("WAPE (Selected Model)"), m("Bias %"),
                             m("Forecast RMSE")]},
           title="Accuracy by Product (selected model)", sort=(m("Actual Units"), "Descending")),
    findings_box(852, 456, 408, 248, "How the model was chosen", [
        ("Fair test:", "each model was chosen on Jun–Aug and scored on Sep–Nov, data it never saw."),
        ("Result:", "exponential smoothing has 21% less error than the seasonal-naive baseline."),
        ("Lesson:", "picking a different model per product overfits (62% error vs 52%)."),
        ("Limit:", "all models under-forecast the Q4 peak by ~25%. Next step: add a holiday uplift."),
    ], size="9pt"),
])

plan = Page("plan", "Inventory Plan", filters=only_forecasted, visuals=[
    header("Inventory Plan", "Safety stock and reorder points from the forecast · change service level and lead time"),
    single(slicer(800, 12, 220, 52, col("Service Level", "Service Level"), "Service Level")),
    single(slicer(1030, 12, 230, 52, col("Lead Time", "Lead Time Weeks"), "Lead Time (weeks)")),
    kpi_row(20, 74, 1240, 100, [m("Service Level"), m("Lead Time (Weeks)"), m("Avg Weekly Forecast"),
                                m("Safety Stock"), m("Reorder Point")]),
    Visual("tableEx", 20, 186, 820, 518,
           roles={"Values": [prod, abc_xyz, m("Avg Weekly Forecast"), m("Forecast RMSE"), m("Safety Stock"),
                             m("Reorder Point")]},
           title="Reorder Plan by Product", sort=(m("Reorder Point"), "Descending")),
    bar_chart(852, 186, 408, 258, abc_xyz, m("Safety Stock"), "Safety Stock by ABC-XYZ Class"),
    findings_box(852, 456, 408, 248, "Method", [
        ("Safety stock", "= Z × forecast RMSE × √lead time."),
        ("Reorder point", "= average weekly forecast × lead time + safety stock."),
        ("Z", "comes from the service level (95% → 1.64)."),
        ("Use:", "raise the service level for A items, accept lower levels for C items to free cash."),
    ]),
])

if __name__ == "__main__":
    write_model(ROOT / f"{NAME}.SemanticModel", PROJECT, NAME, DATA, tables, rels)
    write_report(ROOT / f"{NAME}.Report", PROJECT, NAME, f"{NAME}.SemanticModel", [demand, accuracy_page, plan])
    write_pbip(ROOT, NAME)
    print("built", ROOT / f"{NAME}.pbip")
