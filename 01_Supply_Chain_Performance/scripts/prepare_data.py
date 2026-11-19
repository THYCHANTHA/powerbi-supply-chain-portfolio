"""
Prepare the DataCo Smart Supply Chain data for the Power BI star schema.

Input : data/raw/DataCoSupplyChainDataset.csv (Mendeley Data, DOI 10.17632/8gx2fvg2k6.5)
Output: data/clean/*.csv  (one fact table, five dimensions)

Data decisions (documented in README):
- Keep orders from Jan 2015 to Sep 2017. From Oct 2017 the product range drops from ~50 to 8-20
  products a month and sales fall sharply, so those months are not comparable.
- Customer names, emails, passwords and street addresses are dropped (not needed, and personal).
- "Late" = Delivery Status "Late delivery" (actual shipping days > scheduled days).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "DataCoSupplyChainDataset.csv"
OUT = ROOT / "data" / "clean"
OUT.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(RAW, encoding="latin-1")
df["Order Date"] = pd.to_datetime(df["order date (DateOrders)"], format="%m/%d/%Y %H:%M").dt.normalize()
df["Ship Date"] = pd.to_datetime(df["shipping date (DateOrders)"], format="%m/%d/%Y %H:%M").dt.normalize()

before = len(df)
df = df[(df["Order Date"] >= "2015-01-01") & (df["Order Date"] < "2017-10-01")].copy()
print(f"rows kept {len(df):,} of {before:,}")

# ---------------------------------------------------------------- dimensions
region = (df[["Market", "Order Region"]].drop_duplicates()
          .sort_values(["Market", "Order Region"]).reset_index(drop=True))
region.insert(0, "Region Id", np.arange(1, len(region) + 1))
region = region.rename(columns={"Order Region": "Region"})
df = df.merge(region.rename(columns={"Region": "Order Region"}), on=["Market", "Order Region"], how="left")

product = (df[["Product Card Id", "Product Name", "Category Name", "Department Name", "Product Price"]]
           .drop_duplicates("Product Card Id")
           .rename(columns={"Product Card Id": "Product Id", "Category Name": "Category",
                            "Department Name": "Department", "Product Price": "List Price"}))

country_map = {"EE. UU.": "United States", "Puerto Rico": "Puerto Rico"}
customer = (df[["Customer Id", "Customer Segment", "Customer State", "Customer Country"]]
            .drop_duplicates("Customer Id")
            .rename(columns={"Customer Segment": "Segment", "Customer State": "State",
                             "Customer Country": "Country"}))
customer["Country"] = customer["Country"].map(country_map).fillna(customer["Country"])

ship = pd.DataFrame({
    "Shipping Mode": ["Same Day", "First Class", "Second Class", "Standard Class"],
    "Mode Sort": [1, 2, 3, 4],
})
ship = ship.merge(df.groupby("Shipping Mode")["Days for shipment (scheduled)"].median()
                  .rename("Planned Ship Days").reset_index(), on="Shipping Mode")

# Date table ends with the data (Sep 2017) so YoY compares like-for-like months.
dates = pd.DataFrame({"Date": pd.date_range("2015-01-01", "2017-09-30", freq="D")})
dates["Year"] = dates["Date"].dt.year
dates["Quarter"] = "Q" + dates["Date"].dt.quarter.astype(str)
dates["Year Quarter"] = dates["Year"].astype(str) + " " + dates["Quarter"]
dates["Year Quarter Key"] = dates["Year"] * 10 + dates["Date"].dt.quarter
dates["Month Number"] = dates["Date"].dt.month
dates["Month"] = dates["Date"].dt.strftime("%b")
dates["Year Month"] = dates["Date"].dt.strftime("%b %Y")
dates["Year Month Key"] = dates["Year"] * 100 + dates["Month Number"]
dates["Month Start"] = dates["Date"].values.astype("datetime64[M]")

# --------------------------------------------------------------------- fact
fact = pd.DataFrame({
    "Order Line Id": df["Order Item Id"],
    "Order Id": df["Order Id"],
    "Order Date": df["Order Date"],
    "Ship Date": df["Ship Date"],
    "Customer Id": df["Customer Id"],
    "Product Id": df["Product Card Id"],
    "Region Id": df["Region Id"],
    "Shipping Mode": df["Shipping Mode"],
    "Delivery Status": df["Delivery Status"],
    "Order Status": df["Order Status"].str.replace("_", " ").str.title(),
    "Payment Type": df["Type"].str.title(),
    "Is Late": (df["Delivery Status"] == "Late delivery").astype(int),
    "Is Cancelled": (df["Delivery Status"] == "Shipping canceled").astype(int),
    "Actual Ship Days": df["Days for shipping (real)"],
    "Scheduled Ship Days": df["Days for shipment (scheduled)"],
    "Quantity": df["Order Item Quantity"],
    "Gross Sales": df["Sales"].round(2),
    "Discount": df["Order Item Discount"].round(2),
    "Net Sales": df["Order Item Total"].round(2),
    "Profit": df["Order Profit Per Order"].round(2),
})
fact["Delay Days"] = (fact["Actual Ship Days"] - fact["Scheduled Ship Days"]).clip(lower=0)

for name, frame in {"fact_order_lines": fact, "dim_product": product, "dim_customer": customer,
                    "dim_region": region, "dim_shipping_mode": ship, "dim_date": dates}.items():
    frame.to_csv(OUT / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    print(f"{name}: {len(frame):,} rows")

# ------------------------------------------------- numbers for the findings box
shipped = fact[fact["Is Cancelled"] == 0]
orders = shipped.groupby("Order Id").agg(late=("Is Late", "max"), mode=("Shipping Mode", "first"),
                                         sales=("Net Sales", "sum"))
print("\nLate delivery % (orders, excl. cancelled):", round(orders["late"].mean() * 100, 1))
print(orders.groupby("mode")["late"].mean().mul(100).round(1).to_string())
print("Net sales of late orders %:", round(orders.loc[orders.late == 1, "sales"].sum() / orders["sales"].sum() * 100, 1))
print(shipped.groupby("Shipping Mode")[["Actual Ship Days", "Scheduled Ship Days"]].mean().round(2).to_string())
reg = shipped.merge(region, on="Region Id").groupby("Region")["Is Late"].mean().mul(100).round(1)
print("region late % range:", reg.min(), "-", reg.max())
print("profit margin %:", round(fact["Profit"].sum() / fact["Net Sales"].sum() * 100, 1))
print("cancelled orders %:", round(fact.groupby("Order Id")["Is Cancelled"].max().mean() * 100, 1))
