"""
Small builder for Power BI Projects (.pbip): TMDL semantic model + PBIR report.

Used by every dashboard project in this portfolio so they share one look and one
set of conventions. Each project's build_report.py describes its tables, measures,
relationships and pages; this module writes the files.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
TOOLS_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- ids
def _hex(seed: str, n: int = 20) -> str:
    return hashlib.md5(seed.encode("utf-8")).hexdigest()[:n]


def _guid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    if name.replace("_", "").isalnum() and not name[0].isdigit():
        return name
    return "'" + name.replace("'", "''") + "'"


# ------------------------------------------------------------------------- model
M_TYPES = {
    "int64": "Int64.Type",
    "double": "type number",
    "decimal": "Currency.Type",
    "string": "type text",
    "dateTime": "type date",
    "boolean": "type logical",
}


@dataclass
class Column:
    name: str
    dtype: str = "string"            # int64 | double | decimal | string | dateTime | boolean
    fmt: str | None = None
    summarize: str = "none"
    hidden: bool = False
    sort_by: str | None = None
    key: bool = False
    category: str | None = None      # e.g. Country, Continent
    description: str | None = None


@dataclass
class Measure:
    name: str
    expr: str
    fmt: str | None = None
    folder: str | None = None
    description: str | None = None
    hidden: bool = False


@dataclass
class Table:
    name: str
    csv: str | None                  # file name inside the data folder (None = no partition)
    columns: list[Column] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    hidden: bool = False
    is_date: bool = False
    description: str | None = None
    m_source: str | None = None      # custom M instead of the CSV loader


@dataclass
class Relationship:
    from_table: str
    from_col: str
    to_table: str
    to_col: str
    active: bool = True


def _desc(lines: list[str], text: str | None, indent: str) -> None:
    if text:
        for ln in text.splitlines():
            lines.append(f"{indent}/// {ln}")


def _csv_m(t: Table) -> str:
    types = ", ".join(f'{{"{c.name}", {M_TYPES[c.dtype]}}}' for c in t.columns)
    return (
        "let\n"
        f'    Source = Csv.Document(File.Contents(DataFolder & "{t.csv}"), '
        '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n"
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")\n'
        "in\n"
        "    Typed"
    )


def _table_tmdl(t: Table, project: str) -> str:
    L: list[str] = []
    _desc(L, t.description, "")
    L.append(f"table {q(t.name)}")
    if t.hidden:
        L.append("\tisHidden")
    if t.is_date:
        L.append("\tdataCategory: Time")
    L.append(f"\tlineageTag: {_guid(project + '/t/' + t.name)}")
    L.append("")
    for m in t.measures:
        _desc(L, m.description, "\t")
        expr = m.expr.strip()
        if "\n" in expr:
            body = "\n".join("\t\t\t" + ln for ln in expr.splitlines())
            L.append(f"\tmeasure {q(m.name)} = ```\n{body}\n\t\t\t```")
        else:
            L.append(f"\tmeasure {q(m.name)} = {expr}")
        if m.fmt:
            L.append(f"\t\tformatString: {m.fmt}")
        if m.folder:
            L.append(f"\t\tdisplayFolder: {m.folder}")
        if m.hidden:
            L.append("\t\tisHidden")
        L.append(f"\t\tlineageTag: {_guid(project + '/m/' + t.name + '/' + m.name)}")
        L.append("")
    for c in t.columns:
        _desc(L, c.description, "\t")
        L.append(f"\tcolumn {q(c.name)}")
        L.append(f"\t\tdataType: {c.dtype}")
        if c.key:
            L.append("\t\tisKey")
        if c.hidden:
            L.append("\t\tisHidden")
        if c.fmt:
            L.append(f"\t\tformatString: {c.fmt}")
        if c.category:
            L.append(f"\t\tdataCategory: {c.category}")
        L.append(f"\t\tlineageTag: {_guid(project + '/c/' + t.name + '/' + c.name)}")
        L.append(f"\t\tsummarizeBy: {c.summarize}")
        L.append(f"\t\tsourceColumn: {c.name}")
        if c.sort_by:
            L.append(f"\t\tsortByColumn: {q(c.sort_by)}")
        L.append("")
        L.append("\t\tannotation SummarizationSetBy = User")
        if c.dtype == "dateTime":
            L.append("")
            L.append("\t\tannotation UnderlyingDateTimeDataType = Date")
        L.append("")
    if t.csv or t.m_source:
        src = t.m_source or _csv_m(t)
        body = "\n".join("\t\t\t\t" + ln for ln in src.splitlines())
        L.append(f"\tpartition {q(t.name)} = m")
        L.append("\t\tmode: import")
        L.append("\t\tsource =")
        L.append(body)
        L.append("")
    L.append("\tannotation PBI_ResultType = Table")
    L.append("")
    return "\n".join(L)


def write_model(sm_dir: Path, project: str, display_name: str, data_folder: str,
                tables: list[Table], rels: list[Relationship]) -> None:
    d = sm_dir / "definition"
    if sm_dir.exists():
        shutil.rmtree(sm_dir)
    (d / "tables").mkdir(parents=True)

    (sm_dir / "definition.pbism").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
    (sm_dir / ".platform").write_text(json.dumps({
        "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": display_name},
        "config": {"version": "2.0", "logicalId": _guid(project + "/sm")}}, indent=2), encoding="utf-8")

    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n\n", encoding="utf-8")

    model = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        "annotation PBI_QueryOrder = " + json.dumps(["DataFolder"] + [t.name for t in tables if t.csv or t.m_source]),
        "",
    ]
    model += [f"ref table {q(t.name)}" for t in tables]
    (d / "model.tmdl").write_text("\n".join(model) + "\n\n", encoding="utf-8")

    folder = data_folder if data_folder.endswith("\\") else data_folder + "\\"
    (d / "expressions.tmdl").write_text(
        "/// Folder that holds the cleaned CSV files. Change it if you move the project.\n"
        f'expression DataFolder = "{folder}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {_guid(project + '/DataFolder')}\n\n"
        "\tannotation PBI_ResultType = Text\n\n", encoding="utf-8")

    for t in tables:
        (d / "tables" / f"{t.name}.tmdl").write_text(_table_tmdl(t, project), encoding="utf-8")

    rl = []
    for r in rels:
        rl.append(f"relationship {_guid(project + '/r/' + r.from_table + r.from_col + r.to_table)}")
        if not r.active:
            rl.append("\tisActive: false")
        rl.append(f"\tfromColumn: {q(r.from_table)}.{q(r.from_col)}")
        rl.append(f"\ttoColumn: {q(r.to_table)}.{q(r.to_col)}")
        rl.append("")
    (d / "relationships.tmdl").write_text("\n".join(rl) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------ report
def lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = f"{v}L"
    elif isinstance(v, float):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def color(hex_: str):
    return {"solid": {"color": lit(hex_)}}


def col(table: str, column: str):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}


def mea(table: str, measure: str):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": measure}}


def _proj(f, active=False):
    inner = f.get("Column") or f.get("Measure")
    t = inner["Expression"]["SourceRef"]["Entity"]
    n = inner["Property"]
    p = {"field": f, "queryRef": f"{t}.{n}", "nativeQueryRef": n}
    if active:
        p["active"] = True
    return p


def props(**kw):
    """Build one formatting-object entry: props(show=True, fontSize=12)."""
    out = {}
    for k, v in kw.items():
        if isinstance(v, dict):
            out[k] = v
        elif isinstance(v, str) and v.startswith("#") and len(v) in (7, 9):
            out[k] = color(v)
        else:
            out[k] = lit(v)
    return out


@dataclass
class Visual:
    vtype: str
    x: float
    y: float
    w: float
    h: float
    roles: dict = field(default_factory=dict)       # role -> list of field dicts
    title: str | None = None
    objects: dict = field(default_factory=dict)     # raw visual "objects"
    container: dict = field(default_factory=dict)   # extra visualContainerObjects
    sort: tuple | None = None                       # (field, "Descending"|"Ascending")
    filters: list = field(default_factory=list)
    name: str | None = None


@dataclass
class Page:
    name: str
    display: str
    visuals: list[Visual] = field(default_factory=list)
    width: int = 1280
    height: int = 720
    filters: list = field(default_factory=list)


def textbox(x, y, w, h, runs, name=None, align=None):
    """runs: list of paragraphs; each paragraph = list of (text, style dict)."""
    paragraphs = []
    for para in runs:
        p = {"textRuns": [{"value": t, **({"textStyle": s} if s else {})} for t, s in para]}
        if align:
            p["horizontalTextAlignment"] = align
        paragraphs.append(p)
    v = Visual("textbox", x, y, w, h, name=name)
    v.objects = {"general": [{"properties": {"paragraphs": paragraphs}}]}
    v.container = {"background": [{"properties": props(show=False)}],
                   "border": [{"properties": props(show=False)}],
                   "title": [{"properties": props(show=False)}],
                   "visualHeader": [{"properties": props(show=False)}]}
    return v


def topn_filter(dim_table: str, dim_col: str, m_table: str, measure: str, n: int, name: str):
    """Visual-level Top N filter (same shape Power BI Desktop writes)."""
    return {
        "name": name,
        "field": col(dim_table, dim_col),
        "type": "TopN",
        "filter": {
            "Version": 2,
            "From": [
                {"Name": "subquery", "Expression": {"Subquery": {"Query": {
                    "Version": 2,
                    "From": [{"Name": "d", "Entity": dim_table, "Type": 0},
                             {"Name": "m", "Entity": m_table, "Type": 0}],
                    "Select": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": dim_col},
                                "Name": "field"}],
                    "OrderBy": [{"Direction": 2, "Expression": {"Measure": {
                        "Expression": {"SourceRef": {"Source": "m"}}, "Property": measure}}}],
                    "Top": n}}}, "Type": 2},
                {"Name": "d", "Entity": dim_table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": dim_col}}],
                "Table": {"SourceRef": {"Source": "subquery"}}}}}],
        },
    }


def _visual_json(v: Visual, page: str, idx: int) -> dict:
    name = v.name or _hex(f"{page}/{idx}/{v.vtype}")
    vis: dict = {"visualType": v.vtype}
    if v.roles:
        qs = {}
        for role, fields in v.roles.items():
            qs[role] = {"projections": [_proj(f, active=(role in ("Category", "Rows") and v.vtype != "slicer"))
                                        for f in fields]}
        query: dict = {"queryState": qs}
        if v.sort:
            query["sortDefinition"] = {"sort": [{"field": v.sort[0], "direction": v.sort[1]}],
                                       "isDefaultSort": True}
        vis["query"] = query
    if v.objects:
        vis["objects"] = v.objects
    vco = dict(v.container)
    if v.title is not None and "title" not in vco:
        vco["title"] = [{"properties": props(show=True, text=v.title)}]
    if vco:
        vis["visualContainerObjects"] = vco
    vis["drillFilterOtherVisuals"] = True
    out = {
        "$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.4.0/schema.json",
        "name": name,
        "position": {"x": v.x, "y": v.y, "z": idx * 1000, "height": v.h, "width": v.w, "tabOrder": idx * 1000},
        "visual": vis,
    }
    if v.filters:
        out["filterConfig"] = {"filters": v.filters}
    return out


def write_report(rep_dir: Path, project: str, display_name: str, sm_folder_name: str,
                 pages: list[Page], theme_path: Path = TOOLS_DIR / "PortfolioTheme.json") -> None:
    if rep_dir.exists():
        shutil.rmtree(rep_dir)
    d = rep_dir / "definition"
    (d / "pages").mkdir(parents=True)
    res = rep_dir / "StaticResources" / "RegisteredResources"
    res.mkdir(parents=True)
    theme_name = "PortfolioTheme.json"
    shutil.copyfile(theme_path, res / theme_name)

    (rep_dir / ".platform").write_text(json.dumps({
        "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": display_name},
        "config": {"version": "2.0", "logicalId": _guid(project + "/report")}}, indent=2), encoding="utf-8")
    (rep_dir / "definition.pbir").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{sm_folder_name}"}}}, indent=2), encoding="utf-8")
    (d / "version.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"}, indent=2), encoding="utf-8")
    ver = {"visual": "1.8.101", "report": "2.0.101", "page": "1.3.101"}
    (d / "report.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {"customTheme": {"name": theme_name, "reportVersionAtImport": ver,
                                            "type": "RegisteredResources"}},
        "objects": {"outspacePane": [{"properties": props(expanded=False)}]},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": theme_name, "path": theme_name, "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "defaultDrillFilterOtherVisuals": True},
    }, indent=2), encoding="utf-8")

    order = []
    for p in pages:
        pid = _hex(project + "/page/" + p.name)
        order.append(pid)
        pd_ = d / "pages" / pid
        (pd_ / "visuals").mkdir(parents=True)
        (pd_ / "page.json").write_text(json.dumps({
            "$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
            "name": pid, "displayName": p.display, "displayOption": "FitToPage",
            "height": p.height, "width": p.width,
            **({"filterConfig": {"filters": p.filters}} if p.filters else {})}, indent=2), encoding="utf-8")
        for i, v in enumerate(p.visuals, start=1):
            vj = _visual_json(v, pid, i)
            vd = pd_ / "visuals" / vj["name"]
            vd.mkdir()
            (vd / "visual.json").write_text(json.dumps(vj, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / "pages" / "pages.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": order, "activePageName": order[0]}, indent=2), encoding="utf-8")


def write_pbip(root: Path, name: str) -> None:
    (root / f"{name}.pbip").write_text(json.dumps({
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{name}.Report"}}],
        "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n", encoding="utf-8")


# ------------------------------------------------------------- common visuals
NAVY, TEAL, AMBER, RED, GREY, INK = "#12355B", "#1B998B", "#F4A259", "#E15554", "#5C6B73", "#1F2933"


def kpi_row(x, y, w, h, fields, cols=None, precision=None, font=None):
    """New card visual with several KPIs side by side.
    precision: {measure name: decimals} for values shown in K/M/bn (e.g. $1.63bn instead of $2bn)."""
    v = Visual("cardVisual", x, y, w, h, roles={"Data": fields})
    per_measure = []
    for f in fields:
        mm = f.get("Measure")
        if not mm:
            continue
        sel = {"metadata": f"{mm['Expression']['SourceRef']['Entity']}.{mm['Property']}"}
        pr = {}
        if precision and mm["Property"] in precision:
            pr["labelPrecision"] = int(precision[mm["Property"]])
        if font and mm["Property"] in font:
            pr["fontSize"] = float(font[mm["Property"]])
        if pr:
            per_measure.append({"properties": props(**pr), "selector": sel})
    v.objects = {
        "layout": [{"properties": props(orientation=0.0, columnCount=cols or len(fields), rowCount=1,
                                         alignment="middle", cellPadding=8)}],
        "value": [{"properties": props(horizontalAlignment="center", fontSize=22.0, fontColor=NAVY,
                                        bold=True), "selector": {"id": "default"}}] + per_measure,
        "label": [{"properties": props(position="belowValue", fontSize=10.0, fontColor=GREY),
                   "selector": {"id": "default"}}],
        "accentBar": [{"properties": props(show=True, position="Top", width=3.0, color=TEAL),
                       "selector": {"id": "default"}}],
        "fillCustom": [{"properties": props(show=True, fillColor="#FFFFFF"), "selector": {"id": "default"}}],
    }
    v.container = {"title": [{"properties": props(show=False)}],
                   "background": [{"properties": props(show=False)}],
                   "border": [{"properties": props(show=False)}]}
    return v


def slicer(x, y, w, h, field_, title, dropdown=True):
    y, h = 6, max(h, 62)            # tall enough for header + dropdown value
    v = Visual("slicer", x, y, w, h, roles={"Values": [field_]}, title=title)
    if dropdown:
        v.objects = {"data": [{"properties": props(mode="Dropdown")}]}
    v.container = {"title": [{"properties": props(show=False)}]}
    return v


def header(page_title: str, subtitle: str, w=1280):
    return textbox(14, 4, 760, 66, [
        [(page_title, {"fontWeight": "bold", "fontSize": "18pt", "color": NAVY})],
        [(subtitle, {"fontSize": "9.5pt", "color": GREY})],
    ])


def bar_chart(x, y, w, h, cat, meas, title, vtype="clusteredBarChart", series=None, top=None,
              labels=True, sort_desc=True):
    """Bar/column chart; meas may be one measure field or a list. Optional Top N on the category."""
    ms = meas if isinstance(meas, list) else [meas]
    roles = {"Category": [cat], "Y": ms}
    if series:
        roles["Series"] = [series]
    v = Visual(vtype, x, y, w, h, roles=roles, title=title,
               sort=(ms[0], "Descending") if sort_desc else None)
    if labels:
        v.objects = {"labels": [{"properties": props(show=True, fontSize=9.0)}]}
    if top:
        c = cat["Column"]
        m = ms[0]["Measure"]
        v.filters = [topn_filter(c["Expression"]["SourceRef"]["Entity"], c["Property"],
                                 m["Expression"]["SourceRef"]["Entity"], m["Property"], top,
                                 f"top{top}{c['Property'].replace(' ', '')}")]
    return v


def findings_box(x, y, w, h, title, items, size="9.5pt"):
    paras = [[(title, {"fontWeight": "bold", "fontSize": "12pt", "color": NAVY})]]
    for head, body in items:
        paras.append([("■ " + head + " ", {"fontWeight": "bold", "fontSize": size, "color": INK}),
                      (body, {"fontSize": size, "color": GREY})])
    v = textbox(x, y, w, h, paras)
    v.container["background"] = [{"properties": props(show=True, color="#FFFFFF", transparency=0.0)}]
    v.container["border"] = [{"properties": props(show=True, color="#E3E8EF", radius=8.0)}]
    return v


def date_table(name="Date", end_hidden=True):
    """Standard Date dimension columns matching the dim_date.csv files in this portfolio."""
    return Table(name, "dim_date.csv", is_date=True, columns=[
        Column("Date", "dateTime", fmt="yyyy-mm-dd", key=True), Column("Year", "int64", fmt="0"),
        Column("Quarter"), Column("Year Quarter", sort_by="Year Quarter Key"),
        Column("Year Quarter Key", "int64", hidden=True), Column("Month Number", "int64", hidden=True),
        Column("Month", sort_by="Month Number"), Column("Year Month", sort_by="Year Month Key"),
        Column("Year Month Key", "int64", hidden=True)])


def measure_table(name, measures, description="All report measures live here."):
    return Table(name, None, columns=[Column("Placeholder", hidden=True)],
                 m_source='let\n    Source = #table(type table [Placeholder = text], {})\nin\n    Source',
                 description=description, measures=measures)


def cat_filter(table: str, column: str, values: list, name: str):
    """Basic (categorical) filter: column IN values. Use on a visual or a page."""
    def v(x):
        return {"Literal": {"Value": f"'{x}'" if isinstance(x, str) else (f"{x}L" if isinstance(x, int) else str(x))}}
    return {
        "name": name,
        "field": col(table, column),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                "Values": [[v(x)] for x in values]}}}],
        },
        "howCreated": "User",
    }
