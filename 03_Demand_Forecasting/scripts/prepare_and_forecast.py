"""
Weekly demand forecasting for a UK online gift retailer (UCI Online Retail II, Dec 2009 - Dec 2011).

Input : data/raw/online_retail_II.csv  (converted once from the UCI .xlsx, both sheets)
Output: data/clean/*.csv for the Power BI model

Steps
1. Clean: drop cancellation invoices (C...) and the original lines they cancel, non-product codes
   (postage, fees, manual adjustments), zero/negative prices and quantities.
2. Weekly demand per product (weeks start Monday; last partial week dropped).
3. ABC (revenue, last 52 weeks) and XYZ (demand variability, CV of weekly units) classes.
4. Forecast the 30 highest-revenue products that sell almost every week.
   Hold-out test = last 13 weeks (Sep - Nov 2011). Models: naive, seasonal naive (same week last
   year), 8-week moving average, Holt exponential smoothing with damped trend (parameters
   chosen by grid search on one-step-ahead error) and a global gradient boosting model.
   Metrics: WAPE, MAPE, bias, RMSE. One model is chosen for all products on a separate validation
   window (13 weeks before the test), then scored on the test window. Picking a different model per
   product on that short window overfits (worse test error), so it is reported only for comparison.
5. Refit the best model on all weeks and forecast the next 8 weeks (Dec 2011 - Jan 2012).
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "online_retail_II.csv"
OUT = ROOT / "data" / "clean"
OUT.mkdir(parents=True, exist_ok=True)
TEST_WEEKS, FUTURE_WEEKS, N_PRODUCTS = 13, 8, 30

# ------------------------------------------------------------------ 1. clean
df = pd.read_csv(RAW, dtype={"Invoice": str, "StockCode": str}, parse_dates=["InvoiceDate"])
n0 = len(df)
# Power BI compares text case-insensitively, and the data has codes like 84030b and 84030B.
df["StockCode"] = df["StockCode"].str.strip().str.upper()
cancel = df[df["Invoice"].str.startswith("C")].copy()
sales = df[~df["Invoice"].str.startswith("C")].copy()
sales = sales[(sales["Quantity"] > 0) & (sales["Price"] > 0)]
sales = sales[sales["StockCode"].str.match(r"^\d{5}")]          # real products only

# remove original lines that were later cancelled (same customer, product and quantity)
cancel["Quantity"] = -cancel["Quantity"]
key = ["Customer ID", "StockCode", "Quantity"]
c_keys = cancel.dropna(subset=["Customer ID"]).groupby(key).size().rename("n_cancel").reset_index()
sales["_rank"] = sales.groupby(key, dropna=False).cumcount()
sales = sales.merge(c_keys, on=key, how="left")
sales = sales[~(sales["_rank"] < sales["n_cancel"].fillna(0))].drop(columns=["_rank", "n_cancel"])
print(f"rows: raw {n0:,} -> clean sales lines {len(sales):,}")

sales["Revenue"] = sales["Quantity"] * sales["Price"]
sales["Week Start"] = sales["InvoiceDate"].dt.normalize() - pd.to_timedelta(sales["InvoiceDate"].dt.weekday, unit="D")
last_full = sales["Week Start"].max() - pd.Timedelta(weeks=1)        # last week is partial (data ends Fri 9 Dec)
sales = sales[sales["Week Start"] <= last_full]
weeks = pd.date_range(sales["Week Start"].min(), last_full, freq="W-MON")
print("weeks:", len(weeks), weeks[0].date(), "-", weeks[-1].date())

desc = (sales.groupby(["StockCode", "Description"]).size().reset_index(name="n")
        .sort_values("n").drop_duplicates("StockCode", keep="last").set_index("StockCode")["Description"])

weekly = (sales.groupby(["Week Start", "StockCode"])
          .agg(Units=("Quantity", "sum"), Revenue=("Revenue", "sum"), Orders=("Invoice", "nunique"))
          .reset_index())
weekly["Revenue"] = weekly["Revenue"].round(2)

# ------------------------------------------------------ 2-3. ABC / XYZ classes
units_wide = weekly.pivot(index="Week Start", columns="StockCode", values="Units").reindex(weeks).fillna(0)
last52 = units_wide.iloc[-52:]
rev52 = weekly[weekly["Week Start"] > weeks[-53]].groupby("StockCode")["Revenue"].sum().sort_values(ascending=False)
cum = rev52.cumsum() / rev52.sum()
abc = pd.Series(np.where(cum <= 0.80, "A", np.where(cum <= 0.95, "B", "C")), index=rev52.index)
cv = (last52.std() / last52.mean()).replace([np.inf, -np.inf], np.nan)
xyz = pd.Series(np.where(cv < 0.5, "X", np.where(cv <= 1.0, "Y", "Z")), index=cv.index)
weeks_selling = (units_wide > 0).sum()

product = pd.DataFrame({"StockCode": units_wide.columns})
product["Description"] = product["StockCode"].map(desc).str.strip().str.title()
product["ABC Class"] = product["StockCode"].map(abc).fillna("C")
product["XYZ Class"] = product["StockCode"].map(xyz).fillna("Z")
product["ABC-XYZ"] = product["ABC Class"] + product["XYZ Class"]
product["Revenue Rank"] = product["StockCode"].map(rev52.rank(ascending=False, method="first")).fillna(99999).astype(int)
product["Weeks Selling"] = product["StockCode"].map(weeks_selling).astype(int)

candidates = product[product["Weeks Selling"] >= 0.85 * len(weeks)].sort_values("Revenue Rank")
chosen = candidates.head(N_PRODUCTS)["StockCode"].tolist()
product["Is Forecasted"] = np.where(product["StockCode"].isin(chosen), "Yes", "No")

# --------------------------------------------------------------- 4. models
def m_naive(y, h):
    return np.repeat(y[-1], h)


def m_snaive(y_full_hist, start, h):
    """same week last year; y_full_hist = full series, start = index of first forecast week"""
    return np.array([y_full_hist[start + i - 52] for i in range(h)])


def m_ma8(y, h):
    return np.repeat(y[-8:].mean(), h)


def m_ets(y, h):
    """Holt exponential smoothing with damped trend; alpha/beta/phi by grid search on one-step SSE."""
    best, best_sse = None, np.inf
    for alpha in (0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
        for beta in (0.0, 0.05, 0.1, 0.2):
            for phi in (0.8, 0.9, 0.98):
                level, trend, sse = y[0], 0.0, 0.0
                for t in range(1, len(y)):
                    pred = level + phi * trend
                    sse += (y[t] - pred) ** 2
                    new_level = alpha * y[t] + (1 - alpha) * (level + phi * trend)
                    trend = beta * (new_level - level) + (1 - beta) * phi * trend
                    level = new_level
                if sse < best_sse:
                    best_sse, best = sse, (level, trend, phi)
    level, trend, phi = best
    damp = np.cumsum([phi ** i for i in range(1, h + 1)])
    return np.clip(level + damp * trend, 0, None)


def gb_features(series, origin, target, scale):
    """features known at the forecast origin for a target week"""
    return [series[origin - 7:origin + 1].mean() / scale,           # recent level
            series[target - 52] / scale,                            # same week last year
            series[target - 53:target - 50].mean() / scale,         # around that week last year
            series[origin - 51:origin + 1].mean() / scale,          # last-year level
            target - origin,                                        # horizon
            weeks[target].isocalendar().week if target < len(weeks) else (weeks[-1] + pd.Timedelta(weeks=target - len(weeks) + 1)).isocalendar().week]


def m_gb(Y, train_end, h):
    """global model across products; Y: dict code -> full array (may be extended with NaN)"""
    X, t = [], []
    for code, s in Y.items():
        scale = max(s[:train_end + 1].mean(), 1)
        for target in range(60, train_end + 1):
            for hz in range(1, h + 1):
                origin = target - hz
                if origin < 59:
                    continue
                X.append(gb_features(s, origin, target, scale))
                t.append(s[target] / scale)
    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, random_state=7)
    model.fit(np.array(X), np.array(t))
    out = {}
    for code, s in Y.items():
        scale = max(s[:train_end + 1].mean(), 1)
        Xp = [gb_features(s, train_end, train_end + hz, scale) for hz in range(1, h + 1)]
        out[code] = np.clip(model.predict(np.array(Xp)) * scale, 0, None)
    return out


def run_models(Y, train_end, h):
    """returns {model: {code: forecast array}} using data up to index train_end"""
    res = {"Naive (last week)": {}, "Seasonal naive": {}, "Moving average (8 weeks)": {},
           "Exponential smoothing": {}}
    for code, s in Y.items():
        hist = s[:train_end + 1]
        res["Naive (last week)"][code] = m_naive(hist, h)
        res["Seasonal naive"][code] = m_snaive(s, train_end + 1, h)
        res["Moving average (8 weeks)"][code] = m_ma8(hist, h)
        res["Exponential smoothing"][code] = m_ets(hist, h)
    res["Gradient boosting"] = m_gb(Y, train_end, h)
    return res


Y = {c: units_wide[c].to_numpy(dtype=float) for c in chosen}
n = len(weeks)
train_end = n - TEST_WEEKS - 1
test_idx = range(train_end + 1, n)
print(f"forecasting {len(chosen)} products; test weeks {weeks[train_end + 1].date()} - {weeks[-1].date()}")
test_fc = run_models(Y, train_end, TEST_WEEKS)

acc_rows, fc_rows = [], []
for model, by_code in test_fc.items():
    for code, f in by_code.items():
        a = Y[code][train_end + 1:]
        e = f - a
        nz = a > 0
        acc_rows.append({"StockCode": code, "Model": model, "Actual Units": a.sum(),
                         "Abs Error": np.abs(e).sum().round(2), "Error": e.sum().round(2),
                         "WAPE": (np.abs(e).sum() / a.sum()).round(4),
                         "MAPE": (np.mean(np.abs(e[nz]) / a[nz])).round(4),
                         "RMSE": np.sqrt(np.mean(e ** 2)).round(2)})
        for i, wk in enumerate(test_idx):
            fc_rows.append({"Week Start": weeks[wk], "StockCode": code, "Model": model,
                            "Forecast Units": round(float(f[i]), 1), "Set": "Test"})
acc = pd.DataFrame(acc_rows)

# Model selection on a separate validation window (the 13 weeks before the test window), so the
# test score of the selected model is an honest out-of-sample number.
val_end = train_end - TEST_WEEKS
val_fc = run_models(Y, val_end, TEST_WEEKS)
val = pd.DataFrame([{"StockCode": c, "Model": mdl,
                     "Val WAPE": np.abs(f - Y[c][val_end + 1:train_end + 1]).sum() / max(Y[c][val_end + 1:train_end + 1].sum(), 1)}
                    for mdl, by in val_fc.items() for c, f in by.items()])
val["Val Actual"] = [Y[c][val_end + 1:train_end + 1].sum() for c in val["StockCode"]]
val["Val Abs Error"] = val["Val WAPE"] * val["Val Actual"].clip(lower=1)
vg = val.groupby("Model")[["Val Abs Error", "Val Actual"]].sum()
val_wape = (vg["Val Abs Error"] / vg["Val Actual"]).sort_values()
print("validation WAPE by model:", val_wape.round(3).to_dict())
SELECTED = val_wape.index[0]          # one model for all products (per-product picks overfit, see README)
per_pick = val.loc[val.groupby("StockCode")["Val WAPE"].idxmin(), ["StockCode", "Model"]]
pp = acc.merge(per_pick, on=["StockCode", "Model"])
print("per-product pick test WAPE (for comparison):", round(pp["Abs Error"].sum() / pp["Actual Units"].sum(), 3))
acc["Is Best"] = (acc["Model"] == SELECTED).astype(int)
acc = acc.merge(val[["StockCode", "Model", "Val WAPE"]].round(4), on=["StockCode", "Model"])

# ------------------------------------------------- 5. future with best model
future_weeks = pd.date_range(weeks[-1] + pd.Timedelta(weeks=1), periods=FUTURE_WEEKS, freq="W-MON")
Yx = {c: np.concatenate([s, np.full(FUTURE_WEEKS, np.nan)]) for c, s in Y.items()}
fut = run_models(Yx, n - 1, FUTURE_WEEKS)
best_model = acc[acc["Is Best"] == 1].set_index("StockCode")["Model"]
for code in chosen:
    for model in fut:
        f = fut[model][code]
        for i, wk in enumerate(future_weeks):
            fc_rows.append({"Week Start": wk, "StockCode": code, "Model": model,
                            "Forecast Units": round(float(f[i]), 1), "Set": "Future"})
fc = pd.DataFrame(fc_rows)

# ----------------------------------------------------------------- outputs
all_weeks = weeks.append(future_weeks)
wk = pd.DataFrame({"Week Start": all_weeks})
wk["Year"] = wk["Week Start"].dt.year
wk["ISO Week"] = wk["Week Start"].dt.isocalendar().week.astype(int)
wk["Month Number"] = wk["Week Start"].dt.month
wk["Month"] = wk["Week Start"].dt.strftime("%b")
wk["Year Month"] = wk["Week Start"].dt.strftime("%b %Y")
wk["Year Month Key"] = wk["Year"] * 100 + wk["Month Number"]
wk["Period"] = np.where(wk["Week Start"] > weeks[-1], "Future",
                        np.where(wk["Week Start"] > weeks[train_end], "Test", "Train"))
wk["In Forecast View"] = np.where(wk["Week Start"] >= pd.Timestamp("2011-03-01"), "Yes", "No")

model_dim = pd.DataFrame({
    "Model": ["Naive (last week)", "Seasonal naive", "Moving average (8 weeks)", "Exponential smoothing",
              "Gradient boosting"],
    "Model Type": ["Baseline", "Baseline", "Baseline", "Statistical", "Machine learning"],
    "Model Sort": [1, 2, 3, 4, 5],
})
service = pd.DataFrame({"Service Level": ["90%", "95%", "97.5%", "99%"],
                        "Service Level Value": [0.90, 0.95, 0.975, 0.99],
                        "Z": [1.2816, 1.6449, 1.9600, 2.3263]})
lead = pd.DataFrame({"Lead Time Weeks": list(range(1, 9))})

files = {"fact_weekly_sales": weekly, "fact_forecast": fc, "fact_model_accuracy": acc, "dim_product": product,
         "dim_week": wk, "dim_model": model_dim, "dim_service_level": service, "dim_lead_time": lead}
for name, frame in files.items():
    frame.to_csv(OUT / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    print(f"{name}: {len(frame):,} rows")

# ------------------------------------------------- numbers for the findings box
g = acc.groupby("Model")[["Abs Error", "Actual Units"]].sum()
print("\nWAPE by model (all 30 products):")
print((g["Abs Error"] / g["Actual Units"]).round(3).sort_values().to_string())
b = acc[acc["Is Best"] == 1]
print("SELECTED:", SELECTED, "test WAPE:", round(b["Abs Error"].sum() / b["Actual Units"].sum(), 3),
      " bias:", round(b["Error"].sum() / b["Actual Units"].sum(), 3))
print("wins:", b["Model"].value_counts().to_dict())
print("ABC counts:", product["ABC Class"].value_counts().to_dict(),
      " A share of products %:", round((product["ABC Class"] == "A").mean() * 100, 1))
print("chosen ABC-XYZ:", product[product["Is Forecasted"] == "Yes"]["ABC-XYZ"].value_counts().to_dict())
m = weekly.assign(M=weekly["Week Start"].dt.month).groupby("M")["Revenue"].sum()
print("Nov share of revenue %:", round(m[11] / m.sum() * 100, 1), " Sep-Nov %:", round(m[[9, 10, 11]].sum() / m.sum() * 100, 1))
