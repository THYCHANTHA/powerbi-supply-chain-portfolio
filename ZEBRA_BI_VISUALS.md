# Zebra BI Visuals in Power BI: Study Notes

These notes are about the Zebra BI custom visuals in the Power BI Visualizations pane. They cover what the visuals are, when to use each one, how to set them up with the measures in this portfolio, and what to say about them in an interview.

> **Which icon is which:** hover over each icon in the Visualizations pane and Power BI shows its name. Zebra BI icons use black/grey bars with green and red marks. Other vendors make icons that look similar (Inforiver, xViz, Acterys, among others), so check the name before you build.

---

## 1. What Zebra BI is

- A set of **custom visuals for Power BI**, from AppSource, made by Zebra BI. The same company also sells an Excel add-in.
- They are built for **financial and business performance reporting**: actual vs budget, actual vs last year, actual vs forecast, and the variance between them.
- They follow **IBCS®** (International Business Communication Standards), a set of rules that makes every report read the same way. This is why finance and controlling teams use them a lot, especially in Europe and Australia.
- The main idea: a normal Power BI chart shows *values*. Zebra BI shows *values and the gap to target*, already worked out and coloured, inside one visual.

### The three main visuals

| Visual | What it is for | Use it instead of |
|---|---|---|
| **Zebra BI Tables** | Variance tables: hierarchy (expand/collapse), actual vs plan/PY, absolute and % variance, small charts inside the table, calculated rows, comments | Matrix + conditional formatting |
| **Zebra BI Charts** | Column/bar charts with variance built in, waterfall, small multiples, charts that switch between time and category | Clustered column/bar charts, built-in waterfall |
| **Zebra BI Cards** | KPI cards with actual, target, variance and a small trend chart | Card / KPI / multi-row card |

---

## 2. The IBCS notation (you need to know this)

Zebra BI draws each scenario with a fixed look. Once you know it, you can read any Zebra BI report:

| Scenario | Short code | How it is drawn |
|---|---|---|
| Actual | **AC** | Solid dark grey/black |
| Previous year | **PY** | Solid light grey |
| Plan / budget | **PL** | Outline (empty box) |
| Forecast | **FC** | Hatched (striped) |

Variances:

- **ΔPY / ΔPL / ΔFC** = absolute variance (for example +$12k), drawn as green/red bars.
- **ΔPY% / ΔPL%** = relative variance (for example +8%), drawn as "pins" (a line with a dot at the end).
- **Green = good, red = bad.** This is not always "up is good". For costs, late deliveries or forecast error, *lower* is better, so the colours have to be **inverted** (see section 5).

Other IBCS habits: time runs left to right on columns, categories go top to bottom on horizontal bars, the same scale across charts that are compared, and the message goes in the title ("Net sales 8% above last year, driven by Fan Shop").

---

## 3. How to add and set up a Zebra BI visual

1. **Get the visual:** Visualizations pane → `...` (Get more visuals) → search "Zebra BI" → Add. Organisations sometimes block AppSource visuals. If yours does, an admin has to allow them.
2. **Field wells** (names can differ a little between versions):
   - **Category**: date (month/quarter) or a dimension (region, supplier, product)
   - **Actual (AC)**: your main measure
   - **Previous year / Plan / Forecast**: the comparison measures (add one or more)
   - **Group**: makes small multiples (one chart per region, and so on)
   - **Tooltips / Comments**: extra measures, or a text column for comments
3. Most settings are **on the visual itself** (click the chart, then the on-visual menu), not only in the Format pane. Zebra BI is set up mostly by clicking on the chart.
4. **Licence:** there is a **free version** with limits and a paid **Pro** licence that unlocks everything. For a client project, ask whether the client already has a licence before you design around Zebra BI. Testing Zebra BI Tables 8.4.2.53 in [project 04](04_Variance_Reporting_ZebraBI/) showed these free-version limits (they can change, so check zebrabi.com):
   - **two measures per visual** (AC + one comparison); a third shows "Feature Limit Reached"
   - **chart view only**; the table view shows "Available with a Paid Plan"
   - **no colour invert**, so for "lower is better" KPIs show a "higher is better" version instead (on-time % instead of late %)
   - **zero values are hidden** (a 0% row does not appear)

---

## 4. Examples from this portfolio

How the measures already in the three projects would map into Zebra BI.

### Project 1: Supply Chain Performance

| Question | Visual | Category | AC | Comparison | Invert? |
|---|---|---|---|---|---|
| Are sales growing? | Charts (columns) | Month | `Net Sales` | PY = `Net Sales PY` | No |
| Which departments drive growth? | Tables or Charts (horizontal bars, sorted by ΔPY) | Department → Category | `Net Sales` | PY = `Net Sales PY` | No |
| Are we shipping on promise? | Charts (horizontal bars) | Shipping Mode | `Avg Actual Ship Days` | PL = `Avg Scheduled Ship Days` | **Yes** (more days = bad) |
| Late rate by region | Tables | Region | `Late Delivery %` | PY version of the measure | **Yes** |

The shipping-mode chart tells the main story of project 1 by itself: First Class AC 2 days against PL 1 day shows a red +1 day (+100%) variance.

### Project 2: Procurement and Supplier Performance

| Question | Visual | Category | AC | Comparison | Invert? |
|---|---|---|---|---|---|
| Who gets the spend? | Charts (bars, Top N + "Others") | Supplier | `Total Spend` | none, or PY | No |
| Are we paying too much? | Tables | Product group → Item | `Total Spend` | PL = benchmark spend; Δ shows `Paid Above Benchmark` | **Yes** |
| Freight cost by mode | Cards | Shipment mode | `Freight per Kg` | PY | **Yes** |
| What moved spend year on year? | Charts (waterfall) | Supplier | `Total Spend` | PY | **Yes** |

### Project 3: Demand Forecasting

| Question | Visual | Category | AC | Comparison | Invert? |
|---|---|---|---|---|---|
| Forecast vs actual | Charts (columns) | Week | `Actual Units` | FC = `Forecast Units` (shown hatched) | No |
| Where is the forecast weakest? | Tables | Product (ABC-XYZ class → product) | `Actual Units` | FC = `Forecast Units`; extra columns `WAPE`, `Bias %` | — |
| Accuracy KPI | Cards | — | `Forecast Accuracy %` | target value | No |

Note: the variance colour for forecast vs actual is not "good" or "bad" by itself. Over-forecasting and under-forecasting are both errors, so explain this in the title or a comment.

---

## 5. Features worth knowing

- **Invert colours** for measures where lower is better: cost, freight, late %, days late, error. This mistake is easy to spot. A red bar for "costs went down" tells the reader the wrong story. (Pro only. In the free version, use a measure where higher is better.)
- **Top N + Others:** show the top 10 suppliers and group the rest, without writing a DAX Top N measure.
- **Sort by variance:** puts the biggest gains and losses at the top. In a review meeting this is often the only view people need.
- **Waterfall:** explains how you got from PY to AC (which suppliers or regions added or removed value).
- **Small multiples:** one small chart per region or category, all on the same scale.
- **Calculated rows (Tables):** for example Gross profit = Revenue − COGS, worked out inside the table. This works for P&L-style reports, but core logic is better kept as DAX measures in the model so it can be reused and tested.
- **Comments:** put a comment marker on a data point and explain it ("Port strike, March"). The comment text comes from a column or measure in the model.
- **Responsive layout:** the visual hides labels and detail when it gets small, so it still reads well on a phone or in a small tile.
- **Scaling across visuals:** several Zebra BI charts can share one scale, so a big bar in one chart is not compared unfairly with a small bar in another.

---

## 6. Zebra BI vs built-in visuals: when to use which

**Use Zebra BI when**
- the report is about **performance against a target** (budget, PY, forecast): finance, sales, procurement, operations reviews
- the client already uses Zebra BI or IBCS (common in Australian and European corporate finance)
- you need hierarchical variance tables that a built-in matrix can only do with a lot of conditional formatting work

**Use built-in visuals when**
- there is no licence, or the organisation does not allow custom visuals
- the page is exploratory (scatter, map, decomposition tree, key influencers)
- you need features that do not work well with custom visuals in every situation. Test **export to PDF/PowerPoint, subscriptions, mobile, and Publish to web** before you promise a client anything.

**Good practice in either case:** keep the logic in **DAX measures** (`Net Sales`, `Net Sales PY`, plan measures). Then the same model works with Zebra BI and with built-in visuals, and you can switch without rebuilding anything.

---

## 7. Interview talking points

- "I know the IBCS notation: AC solid, PY grey, PL outlined, FC hatched, variances as bars and pins, and inverted colours for cost KPIs."
- "I build the comparison measures in DAX first (actual, prior year, plan, forecast), so any visual, Zebra BI or built-in, can use them."
- "For a supply chain review, I would show on-time delivery and lead time against plan as inverted variance bars sorted by variance, so the worst lanes or suppliers come first."
- "Before using a custom visual, I check that the client has a licence and allows AppSource visuals, and I test PDF export and mobile."

---

## 8. Practice

Done in [04_Variance_Reporting_ZebraBI](04_Variance_Reporting_ZebraBI/): net sales AC vs PY and PL by month and by department → category, on-time delivery % vs PY by shipping mode and month, and a page comparing built-in visuals with Zebra BI. Market was left out because in DataCo the market rotates by quarter.

Still to do:
- [ ] Add a Zebra BI Table to project 2 with Product group → Item and spend vs benchmark
- [ ] Try the Pro trial: one table with AC, PL and PY, and inverted colours for cost and late measures

Official resources: zebrabi.com (product pages, Zebra BI Academy free courses, documentation) and ibcs.com (the IBCS standards).
