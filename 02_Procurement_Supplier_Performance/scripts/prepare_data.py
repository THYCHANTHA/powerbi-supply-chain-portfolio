"""
Prepare USAID SCMS shipment data (health commodities, 2006-2015) for a procurement and supplier
performance star schema.

Input : data/raw/SCMS_Delivery_History_Dataset.csv  (USAID "Supply Chain Shipment Pricing Data",
        public domain; same file confirmed from two independent mirrors, SHA-256 918b992d...)
Output: data/clean/*.csv

Data decisions (documented in README):
- Late = Delivered to Client Date later than Scheduled Delivery Date.
- Freight and weight are numbers only on some lines. Other lines say "Freight Included in Commodity
  Cost", "Invoiced Separately" or "See ASN-..." (shared with another line). Those are kept as a
  Freight Status label and excluded from freight-rate maths.
- Price benchmark = quantity-weighted average pack price of the same item (exact item description)
  in the same delivery year. Price variance = what was paid minus quantity x benchmark.
- "SCMS from RDC" is not a supplier; it means the line was supplied from a Regional Distribution
  Centre. It is labelled as its own supplier type so supplier KPIs can exclude it.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "SCMS_Delivery_History_Dataset.csv"
OUT = ROOT / "data" / "clean"
OUT.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(RAW, encoding="utf-8-sig")

df["Scheduled Date"] = pd.to_datetime(df["Scheduled Delivery Date"], format="%d-%b-%y")
df["Delivered Date"] = pd.to_datetime(df["Delivered to Client Date"], format="%d-%b-%y")
df["PO Date"] = pd.to_datetime(df["PO Sent to Vendor Date"], format="%m/%d/%y", errors="coerce")

num = lambda s: pd.to_numeric(s, errors="coerce")  # noqa: E731
df["Freight USD"] = num(df["Freight Cost (USD)"])
df["Weight Kg"] = num(df["Weight (Kilograms)"])
fc = df["Freight Cost (USD)"].astype(str)
df["Freight Status"] = np.select(
    [df["Freight USD"].notna(), fc.str.contains("Included", case=False), fc.str.contains("Invoiced", case=False),
     fc.str.startswith("See")],
    ["Charged on this line", "Included in commodity cost", "Invoiced separately", "Shared with another line"],
    "Not recorded")

# --------------------------------------------------------------- dimensions
region_map = {
    "Afghanistan": "Asia", "Vietnam": "Asia", "Pakistan": "Asia", "Kazakhstan": "Asia", "Kyrgyzstan": "Asia",
    "Lebanon": "Middle East", "Haiti": "Latin America & Caribbean", "Guyana": "Latin America & Caribbean",
    "Dominican Republic": "Latin America & Caribbean", "Guatemala": "Latin America & Caribbean",
    "Belize": "Latin America & Caribbean",
}
countries = sorted(df["Country"].unique())
country = pd.DataFrame({"Country": countries})
country["Region"] = country["Country"].map(region_map).fillna("Africa")

vendor = pd.DataFrame({"Vendor": sorted(df["Vendor"].unique())})
vendor["Supplier Type"] = np.where(vendor["Vendor"] == "SCMS from RDC", "Regional Distribution Centre",
                                   "Direct supplier")
vendor["Vendor"] = vendor["Vendor"].str.strip()
# Short display name: drop "(FORMERLY ...)" notes and legal suffixes, title case, keep unique.
short = (vendor["Vendor"].str.replace(r"\s*\(.*?\)", "", regex=True)
         .str.replace(r",?\s+(LTD\.?|LIMITED|PLC|INC\.?|GMBH.*|S\.A\.?|B\.V\.?|PVT\.?|CO\.?)$", "", regex=True, case=False)
         .str.strip(" ,.").str.title().str.slice(0, 32))
short = short.where(~short.duplicated(keep=False), vendor["Vendor"].str.title().str.slice(0, 32))
vendor["Supplier"] = np.where(vendor["Vendor"] == "SCMS from RDC", "Regional Distribution Centre", short)
assert vendor["Supplier"].is_unique

group_names = {"ARV": "Antiretroviral (ARV)", "HRDT": "HIV rapid test", "ANTM": "Antimalarial",
               "ACT": "Artemisinin therapy (ACT)", "MRDT": "Malaria rapid test"}
item = (df[["Item Description", "Product Group", "Sub Classification", "Molecule/Test Type", "Brand",
            "Dosage Form", "First Line Designation"]]
        .drop_duplicates("Item Description").reset_index(drop=True))
item.insert(0, "Item Id", np.arange(1, len(item) + 1))
item["Product Group"] = item["Product Group"].map(group_names)
item = item.rename(columns={"Item Description": "Item", "Molecule/Test Type": "Molecule or Test",
                            "First Line Designation": "First Line Drug"})
df = df.merge(item[["Item Id", "Item"]], left_on="Item Description", right_on="Item")

# Price benchmark per item and delivery year (quantity-weighted average pack price, quantity > 0).
# Same year, because medicine prices fell a lot between 2006 and 2015.
df["Bench Year"] = df["Delivered Date"].dt.year
pos = df[df["Line Item Quantity"] > 0]
bench = (pos.groupby(["Item Id", "Bench Year"])
         .apply(lambda g: g["Line Item Value"].sum() / g["Line Item Quantity"].sum(), include_groups=False)
         .rename("Benchmark Pack Price").reset_index())
df = df.merge(bench, on=["Item Id", "Bench Year"], how="left")
df["Benchmark Value"] = (df["Line Item Quantity"] * df["Benchmark Pack Price"]).round(2)
df["Price Variance"] = (df["Line Item Value"] - df["Benchmark Value"]).round(2)

lo, hi = df["Delivered Date"].min(), df["Delivered Date"].max()
dates = pd.DataFrame({"Date": pd.date_range(f"{lo.year}-01-01", hi, freq="D")})
dates["Year"] = dates["Date"].dt.year
dates["Quarter"] = "Q" + dates["Date"].dt.quarter.astype(str)
dates["Year Quarter"] = dates["Year"].astype(str) + " " + dates["Quarter"]
dates["Year Quarter Key"] = dates["Year"] * 10 + dates["Date"].dt.quarter
dates["Month Number"] = dates["Date"].dt.month
dates["Month"] = dates["Date"].dt.strftime("%b")
dates["Year Month"] = dates["Date"].dt.strftime("%b %Y")
dates["Year Month Key"] = dates["Year"] * 100 + dates["Month Number"]

# --------------------------------------------------------------------- fact
days_late = (df["Delivered Date"] - df["Scheduled Date"]).dt.days
fact = pd.DataFrame({
    "Line Id": df["ID"],
    "Project Code": df["Project Code"],
    "PO Number": df["PO / SO #"],
    "Shipment Number": df["ASN/DN #"],
    "Country": df["Country"],
    "Vendor": df["Vendor"].str.strip(),
    "Item Id": df["Item Id"],
    "Shipment Mode": df["Shipment Mode"].fillna("Not recorded"),
    "Fulfill Via": df["Fulfill Via"].replace({"From RDC": "From RDC", "Direct Drop": "Direct drop"}),
    "INCO Term": df["Vendor INCO Term"],
    "Scheduled Date": df["Scheduled Date"],
    "Delivered Date": df["Delivered Date"],
    "PO Date": df["PO Date"],
    "Quantity": df["Line Item Quantity"],
    "Line Value": df["Line Item Value"].round(2),
    "Pack Price": df["Pack Price"],
    "Benchmark Value": df["Benchmark Value"],
    "Price Variance": df["Price Variance"],
    "Weight Kg": df["Weight Kg"],
    "Freight USD": df["Freight USD"].round(2),
    "Insurance USD": num(df["Line Item Insurance (USD)"]).round(2),
    "Freight Status": df["Freight Status"],
    "Days Late": days_late,
    "Is Late": (days_late > 0).astype(int),
    "PO to Delivery Days": (df["Delivered Date"] - df["PO Date"]).dt.days,
})
# freight rate helpers: only where freight and weight are both real numbers
both = fact["Freight USD"].notna() & fact["Weight Kg"].notna() & (fact["Weight Kg"] > 0)
fact["Freight For Rate"] = np.where(both, fact["Freight USD"], np.nan)
fact["Weight For Rate"] = np.where(both, fact["Weight Kg"], np.nan)
fact["Value With Freight"] = np.where(fact["Freight USD"].notna(), fact["Line Value"], np.nan)

for name, frame in {"fact_shipment_lines": fact, "dim_vendor": vendor, "dim_item": item,
                    "dim_country": country, "dim_date": dates}.items():
    frame.to_csv(OUT / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    print(f"{name}: {len(frame):,} rows")

# ------------------------------------------------- numbers for the findings box
print("\nyears:", lo.date(), "-", hi.date())
print("spend total $M:", round(fact["Line Value"].sum() / 1e6, 1))
print("on-time %:", round((1 - fact["Is Late"].mean()) * 100, 1))
d = fact[fact["Vendor"] != "SCMS from RDC"]
vs = d.groupby("Vendor")["Line Value"].sum().sort_values(ascending=False)
print("direct suppliers:", len(vs), " top5 share of direct spend %:", round(vs.head(5).sum() / vs.sum() * 100, 1))
print("suppliers making 80% of direct spend:", int((vs.cumsum() / vs.sum() <= 0.8).sum()) + 1)
print(vs.head(5).div(1e6).round(1).to_string())
print("on-time by fulfil:", fact.groupby("Fulfill Via")["Is Late"].mean().rsub(1).mul(100).round(1).to_dict())
r = fact.dropna(subset=["Freight For Rate"])
print("freight % of value (lines with freight):",
      round(r["Freight For Rate"].sum() / fact.loc[r.index, "Line Value"].sum() * 100, 1))
g = r.groupby("Shipment Mode").agg(f=("Freight For Rate", "sum"), w=("Weight For Rate", "sum"), n=("Line Id", "count"))
g["usd_per_kg"] = (g.f / g.w).round(2)
print(g.to_string())
print("overpaid vs benchmark $M (positive variance):", round(fact.loc[fact["Price Variance"] > 0, "Price Variance"].sum() / 1e6, 1))
print("overpaid by vendor $M:", fact[fact["Price Variance"]>0].groupby("Vendor")["Price Variance"].sum().div(1e6).round(1).sort_values(ascending=False).head(5).to_dict())
print("late days avg (late only):", round(fact.loc[fact["Is Late"] == 1, "Days Late"].mean(), 1))
print("on-time by year:", fact.groupby(fact["Delivered Date"].dt.year)["Is Late"].mean().rsub(1).mul(100).round(1).to_dict())
