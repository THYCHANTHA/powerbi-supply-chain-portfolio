"""
Prepare data for the Variance Reporting (Zebra BI) project.

Input : the cleaned DataCo files from project 01 (same numbers, already checked there).
Output: data/clean/ in this project
  - fact_order_lines.csv   only the columns this report needs
  - fact_plan.csv          rule-based 2017 sales plan (see PLAN RULE below)
  - dim_*.csv              copied unchanged
It also prints the headline numbers so the DAX results can be checked against pandas.

PLAN RULE (the dataset has no budget, so the plan is built from a simple, written rule):
  Plan 2017 for a month and product = 2016 actual for the same month and product
  x (1 + growth target of the product's department). Profit plan uses the same rule on 2016 profit.
  Only Jan-Sep is planned, because the data ends in Sep 2017.
  This is an illustrative plan to show variance reporting; it is not a real company budget.

WHY NO MARKET / REGION: in DataCo the market of the orders rotates over time (2015 Q1 is all LATAM,
2016 Q1 all Pacific Asia, 2017 Q3 all Europe), so a year-on-year or plan variance by market only shows
that rotation, not performance. Department and shipping mode are stable across quarters, so the
variance views use those. The quarter check printed below shows this.
"""
from pathlib import Path
import shutil

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "01_Supply_Chain_Performance" / "data" / "clean"
OUT = ROOT / "data" / "clean"

GROWTH_TARGET = {           # illustrative growth targets by department
    "Apparel": 0.04,
    "Fan Shop": 0.05,
    "Fitness": 0.05,
    "Footwear": 0.06,
    "Golf": 0.03,
    "Outdoors": 0.05,
}
PLAN_YEAR, BASE_YEAR, LAST_MONTH = 2017, 2016, 9

FACT_COLS = ["Order Id", "Order Date", "Product Id", "Region Id", "Shipping Mode", "Is Late", "Is Cancelled",
             "Actual Ship Days", "Scheduled Ship Days", "Net Sales", "Profit"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fact = pd.read_csv(SRC / "fact_order_lines.csv", usecols=FACT_COLS, parse_dates=["Order Date"])
    product = pd.read_csv(SRC / "dim_product.csv")
    region = pd.read_csv(SRC / "dim_region.csv")
    assert set(product["Department"]) == set(GROWTH_TARGET), "every department needs a growth target"

    fact.drop(columns="Region Id").to_csv(OUT / "fact_order_lines.csv", index=False, date_format="%Y-%m-%d")
    for f in ["dim_date.csv", "dim_product.csv", "dim_shipping_mode.csv"]:
        shutil.copyfile(SRC / f, OUT / f)

    # ---------------------------------------------------------------- plan
    base = fact[(fact["Order Date"].dt.year == BASE_YEAR) & (fact["Order Date"].dt.month <= LAST_MONTH)].copy()
    base["Month"] = base["Order Date"].dt.month
    base = (base.groupby(["Month", "Product Id"], as_index=False)[["Net Sales", "Profit"]].sum()
                .merge(product[["Product Id", "Department"]], on="Product Id"))
    base["Growth Target"] = base["Department"].map(GROWTH_TARGET)
    plan = pd.DataFrame({
        "Plan Date": pd.to_datetime(dict(year=PLAN_YEAR, month=base["Month"], day=1)),
        "Product Id": base["Product Id"],
        "Growth Target": base["Growth Target"],
        "Net Sales Plan": (base["Net Sales"] * (1 + base["Growth Target"])).round(2),
        "Profit Plan": (base["Profit"] * (1 + base["Growth Target"])).round(2),
    })
    plan.to_csv(OUT / "fact_plan.csv", index=False, date_format="%Y-%m-%d")

    # ------------------------------------------------------- check numbers
    pd.set_option("display.width", 200)
    q = fact.merge(region, on="Region Id").assign(Q=lambda d: d["Order Date"].dt.to_period("Q"))
    print("Net sales ($k) by quarter and market: the market rotates, so it is left out of the variance views")
    print((q.pivot_table(index="Q", columns="Market", values="Net Sales", aggfunc="sum") / 1000).round(0).to_string())

    ac = fact[(fact["Order Date"].dt.year == PLAN_YEAR)]
    py = fact[(fact["Order Date"].dt.year == BASE_YEAR) & (fact["Order Date"].dt.month <= LAST_MONTH)]
    shipped = lambda d: d[d["Is Cancelled"] == 0]  # noqa: E731
    late = lambda d: shipped(d).groupby("Order Id")["Is Late"].max()  # noqa: E731
    print(f"\norder lines {len(fact):,}  plan rows {len(plan):,}")
    print(f"2017 Jan-Sep  AC {ac['Net Sales'].sum():,.0f}  PY {py['Net Sales'].sum():,.0f}  "
          f"PL {plan['Net Sales Plan'].sum():,.0f}")
    print(f"              vs PY {ac['Net Sales'].sum() / py['Net Sales'].sum() - 1:+.1%}  "
          f"vs PL {ac['Net Sales'].sum() / plan['Net Sales Plan'].sum() - 1:+.1%}")
    print(f"profit AC {ac['Profit'].sum():,.0f}  PY {py['Profit'].sum():,.0f}  PL {plan['Profit Plan'].sum():,.0f}")
    print(f"late % AC {late(ac).mean():.1%}  PY {late(py).mean():.1%}")
    dept = lambda d, c: d.merge(product, on="Product Id").groupby("Department")[c].sum()  # noqa: E731
    by = pd.DataFrame({"AC": dept(ac, "Net Sales"), "PY": dept(py, "Net Sales"), "PL": dept(plan, "Net Sales Plan")})
    by["vs PY %"] = by["AC"] / by["PY"] - 1
    by["vs PL %"] = by["AC"] / by["PL"] - 1
    print(by.round(3).to_string())
    s = shipped(ac)
    print(s.groupby("Shipping Mode")[["Actual Ship Days", "Scheduled Ship Days"]].mean().round(2).to_string())
    lm = lambda d: shipped(d).groupby(["Shipping Mode", "Order Id"])["Is Late"].max().groupby(level=0).mean()  # noqa: E731
    print(pd.DataFrame({"Late % AC": lm(ac), "Late % PY": lm(py)}).round(3).to_string())


if __name__ == "__main__":
    main()
