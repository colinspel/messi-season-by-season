"""
Small library for generating Tableau workbooks (.twb/.twbx) as XML, validated against Tableau's
published XSD (github.com/tableau/tableau-document-schemas). Extracted from the Euro 2024 builder.

Usage pattern (see build_xg_twb.py / build_messi_twb.py):
    wb = Workbook("My Workbook", data_dir)
    p = wb.param_list("Season", ["2011/2012", ...], "2011/2012")
    src = wb.source("seasons", "messi_seasons.csv", "Seasons")
    src.calc("Calc_x", "Caption", "SUM([a]) / SUM([b])", deps=["a", "b"])
    s = wb.sheet("Name", src, "Bar"); s.row("season", "dim"); s.col("Calc_x", "usr")
    wb.dashboard("1 Overview", "Title", "Subtitle", [p], lambda pg: wb.row_of(pg, 110, 790, [("Name", 1280)]))
    wb.save(out_twbx, images=[...], xsd=path)
"""
import hashlib
import sys
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import pandas as pd

BLUE, ORANGE, GRAY, MID, INK, INK2, SURF = "#2a78d6", "#eb6834", "#b8b7b0", "#d9d8d2", "#0b0b0b", "#52514e", "#fcfcfb"
SEQ = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]


def q(s):
    return quoteattr(str(s))


def sid(seed):
    return "{" + str(uuid.UUID(hashlib.md5(seed.encode()).hexdigest())).upper() + "}"


TYPE_MAP = {"int64": ("integer", 20, "I8", "Sum"), "float64": ("real", 5, "R8", "Sum"),
            "object": ("string", 130, "WSTR", "Count"), "bool": ("string", 130, "WSTR", "Count")}


class Param:
    def __init__(self, idx, caption, datatype, default, members=None, rng=None, aliases=None):
        self.name = f"Parameter {idx}"
        self.ref = f"[Parameters].[{self.name}]"
        self.caption, self.datatype, self.default, self.members, self.rng, self.aliases = caption, datatype, default, members, rng, aliases or {}

    def lit(self, v):
        return f'"{v}"' if self.datatype == "string" else str(v)

    def xml(self):
        dom = "list" if self.members is not None else "range"
        body = f"<calculation class='tableau' formula={q(self.lit(self.default))} />"
        if self.members is not None:
            body += "<members>" + "".join(
                f"<member value={q(self.lit(m))}" + (f" alias={q(self.aliases[m])}" if m in self.aliases else "") + " />"
                for m in self.members) + "</members>"
        else:
            lo, hi, step = self.rng
            body += f"<range granularity={q(step)} max={q(hi)} min={q(lo)} />"
        typ = "nominal" if self.datatype == "string" else "quantitative"
        return (f"<column caption={q(self.caption)} datatype={q(self.datatype)} name={q('[' + self.name + ']')} "
                f"param-domain-type={q(dom)} role='measure' type={q(typ)} value={q(self.lit(self.default))}>{body}</column>")


class Source:
    def __init__(self, data_dir, key, csv, caption, dims=(), force_string=()):
        self.key, self.csv, self.caption = key, csv, caption
        self.name = "federated." + hashlib.md5(key.encode()).hexdigest()[:27]
        self.conn = "textscan." + hashlib.md5(("c" + key).encode()).hexdigest()[:27]
        self.dims = set(dims)
        df = pd.read_csv(Path(data_dir) / csv, nrows=5000)
        self.cols = []
        for c in df.columns:
            dt = "object" if c in force_string else str(df[c].dtype)
            if dt == "float64" and c in self.dims and df[c].dropna().apply(float.is_integer).all():
                dt = "int64"
            self.cols.append((c, TYPE_MAP.get(dt, TYPE_MAP["object"])))
        self.calcs, self.calc_deps, self.calc_params = {}, {}, {}
        self.palettes, self.images = [], []

    def calc(self, name, caption, formula, datatype="real", role="measure", typ="quantitative", deps=(), params=()):
        self.calcs[name] = (caption, formula, datatype, role, typ)
        self.calc_deps[name] = list(deps)
        self.calc_params[name] = [p.name for p in params]
        return name

    def field_type(self, col):
        for c, (dt, *_r) in self.cols:
            if c == col:
                return dt
        return self.calcs[col][2]

    def column_xml(self, col):
        if col in self.calcs:
            cap, formula, dt, role, typ = self.calcs[col]
            return (f"<column caption={q(cap)} datatype={q(dt)} name={q('[' + col + ']')} role={q(role)} type={q(typ)}>"
                    f"<calculation class='tableau' formula={q(formula)} /></column>")
        dt = self.field_type(col)
        if col in self.dims or dt == "string":
            role, typ = "dimension", ("ordinal" if dt == "integer" else "nominal")
        else:
            role, typ = "measure", "quantitative"
        return f"<column caption={q(col.replace('_', ' ').title())} datatype={q(dt)} name={q('[' + col + ']')} role={q(role)} type={q(typ)} />"

    def xml(self):
        rel_cols = "".join(f"<column datatype={q(dt)} name={q(c)} ordinal='{i}' />" for i, (c, (dt, *_)) in enumerate(self.cols))
        meta = "".join(
            f"<metadata-record class='column'><remote-name>{escape(c)}</remote-name><remote-type>{rt}</remote-type>"
            f"<local-name>[{escape(c)}]</local-name><parent-name>[{escape(self.csv)}]</parent-name>"
            f"<remote-alias>{escape(c)}</remote-alias><ordinal>{i}</ordinal><local-type>{dt}</local-type>"
            f"<aggregation>{agg}</aggregation><contains-null>true</contains-null>"
            f"<attributes><attribute datatype='string' name='DebugRemoteType'>&quot;{dbg}&quot;</attribute></attributes></metadata-record>"
            for i, (c, (dt, rt, dbg, agg)) in enumerate(self.cols))
        table = "[" + self.csv.replace(".", "#") + "]"
        conn = (f"<connection class='federated'><named-connections><named-connection caption='data' name={q(self.conn)}>"
                f"<connection class='textscan' directory='Data/data' filename={q(self.csv)} password='' server='' />"
                f"</named-connection></named-connections>"
                f"<relation connection={q(self.conn)} name={q(self.csv)} table={q(table)} type='table'>"
                f"<columns character-set='UTF-8' header='yes' locale='en_US' separator=','>{rel_cols}</columns></relation>"
                f"<metadata-records>{meta}</metadata-records></connection>")
        cols = "".join(self.column_xml(c) for c, _ in self.cols) + "".join(self.column_xml(c) for c in self.calcs)
        imgs = ""
        if self.images:
            imgs = "<mapped-images>" + "".join(
                f"<mapped-image caption={q(cap)} expression={q(path)} name={q('[' + cap + ']')}>"
                f"<mapping bottom={q(b)} left={q(l)} right={q(r)} top={q(t)} x={q('[' + x + ']')} y={q('[' + y + ']')} />"
                f"<image-options lock-aspect-ratio='true' show-entire-image='true' /></mapped-image>"
                for cap, path, x, y, l, r, b, t in self.images) + "</mapped-images>"
        style = ""
        if self.palettes:
            rules = ""
            for field, mapping in self.palettes:
                if isinstance(mapping, str):   # continuous ramp: palette name
                    rules += f"<encoding attr='color' field={q(field)} palette={q(mapping)} type='interpolated' />"
                else:
                    rules += f"<encoding attr='color' field={q(field)} type='palette'>" + "".join(
                        f"<map to={q(c)}><bucket>{escape(b)}</bucket></map>" for b, c in mapping) + "</encoding>"
            style = f"<style><style-rule element='mark'>{rules}</style-rule></style>"
        return (f"<datasource caption={q(self.caption)} inline='true' name={q(self.name)} version='18.1'>{conn}"
                f"<aliases enabled='yes' />{cols}{imgs}"
                f"<layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />{style}"
                f"<semantic-values><semantic-value key='[Country].[Name]' value='&quot;United States&quot;' /></semantic-values>"
                f"</datasource>")


def inst(src, col, deriv):
    table = {"dim": ("none", "None", "nominal", "nk"), "ord": ("none", "None", "ordinal", "ok"),
             "cont": ("none", "None", "quantitative", "qk"), "sum": ("sum", "Sum", "quantitative", "qk"),
             "avg": ("avg", "Avg", "quantitative", "qk"), "usr": ("usr", "User", "quantitative", "qk"),
             "usrdim": ("usr", "User", "nominal", "nk")}
    pre, d, t, suf = table[deriv]
    name = f"{pre}:{col}:{suf}"
    return (f"[{src.name}].[{name}]",
            f"<column-instance column={q('[' + col + ']')} derivation={q(d)} name={q('[' + name + ']')} pivot='key' type={q(t)} />")


class Sheet:
    def __init__(self, wb, name, src, mark, title=None):
        self.wb, self.name, self.src, self.mark, self.title = wb, name, src, mark, title
        self.rows, self.cols_shelf, self.enc, self.instances = [], [], [], {}
        self.used, self.filters, self.sorts, self.slices, self.axis_rules, self.mark_formats = set(), [], [], [], [], []
        self.aggregate, self.params = True, set()

    def use(self, col, deriv):
        ref, xml = inst(self.src, col, deriv)
        self.instances[ref] = xml
        self._dep(col)
        return ref

    def _dep(self, col):
        self.used.add(col)
        for d in self.src.calc_deps.get(col, []):
            self._dep(d)
        for p in self.src.calc_params.get(col, []):
            self.params.add(p)

    def row(self, col, deriv):
        self.rows.append(self.use(col, deriv)); return self

    def col(self, col, deriv):
        self.cols_shelf.append(self.use(col, deriv)); return self

    def encode(self, ch, col, deriv):
        self.enc.append((ch, self.use(col, deriv))); return self

    def _member_filter(self, col, member):
        ref = self.use(col, "dim")
        lvl = ref.split("].[")[1].rstrip("]")
        self.filters.append(f"<filter class='categorical' column={q(ref)}><groupfilter function='member' level={q('[' + lvl + ']')} "
                            f"member={q(member)} user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' /></filter>")
        self.slices.append(ref); return self

    def keep_true(self, col):
        return self._member_filter(col, "true")

    def keep_value(self, col, value):
        return self._member_filter(col, f'"{value}"')

    def sort_by(self, dim_ref, using_ref, direction="DESC"):
        self.sorts.append(f"<computed-sort column={q(dim_ref)} direction={q(direction)} using={q(using_ref)} />"); return self

    def fix_axis(self, ref, scope, lo, hi, show=True, reverse=False):
        rev = " reverse='true'" if reverse else ""
        self.axis_rules.append(f"<encoding attr='space' class='0' field={q(ref)} field-type='quantitative' max={q(hi)} "
                               f"min={q(lo)} range-type='fixed'{rev} scope={q(scope)} type='space' />")
        if not show:
            self.axis_rules.append(f"<format attr='display' class='0' field={q(ref)} scope={q(scope)} value='false' />")
        return self

    def xml(self):
        deps = "".join(self.src.column_xml(c) for c in sorted(self.used)) + "".join(self.instances.values())
        ds = f"<datasource caption={q(self.src.caption)} name={q(self.src.name)} />"
        pdeps = ""
        if self.params:
            ds = "<datasource name='Parameters' />" + ds
            pdeps = ("<datasource-dependencies datasource='Parameters'>"
                     + "".join(self.wb.params[p].xml() for p in sorted(self.params)) + "</datasource-dependencies>")
        view = (f"<view><datasources>{ds}</datasources>{pdeps}"
                f"<datasource-dependencies datasource={q(self.src.name)}>{deps}</datasource-dependencies>"
                + "".join(self.filters) + "".join(self.sorts)
                + (f"<slices>{''.join('<column>' + escape(s) + '</column>' for s in self.slices)}</slices>" if self.slices else "")
                + f"<aggregation value={q('true' if self.aggregate else 'false')} /></view>")
        rules = []
        if self.axis_rules:
            rules.append(f"<style-rule element='axis'>{''.join(self.axis_rules)}</style-rule>")
        rules.append("<style-rule element='gridline'><format attr='line-visibility' scope='rows' value='off' />"
                     "<format attr='line-visibility' scope='cols' value='off' /></style-rule>")
        rules.append(f"<style-rule element='table'><format attr='background-color' value='{SURF}' /></style-rule>")
        rules.append(f"<style-rule element='pane'><format attr='background-color' value='{SURF}' /></style-rule>")
        enc = "".join(f"<{ch} column={q(ref)} />" for ch, ref in self.enc)
        mfmt = "".join(f"<format attr={q(a)} value={q(v)} />" for a, v in self.mark_formats)
        pstyle = f"<style><style-rule element='mark'>{mfmt}</style-rule></style>" if mfmt else ""
        panes = (f"<panes><pane selection-relaxation-option='selection-relaxation-allow'><view><breakdown value='auto' /></view>"
                 f"<mark class={q(self.mark)} />" + (f"<encodings>{enc}</encodings>" if enc else "") + f"{pstyle}</pane></panes>")
        shelf = lambda refs: escape(" / ".join(refs))
        title = (f"<layout-options><title><formatted-text><run bold='true' fontcolor='{INK}' fontsize='12'>{escape(self.title)}"
                 f"</run></formatted-text></title></layout-options>") if self.title else ""
        return (f"<worksheet name={q(self.name)}>{title}<table>{view}<style>{''.join(rules)}</style>{panes}"
                f"<rows>{shelf(self.rows)}</rows><cols>{shelf(self.cols_shelf)}</cols></table>"
                f"<simple-id uuid={q(sid(self.wb.title + 'ws' + self.name))} /></worksheet>")


W_, H_ = 1280, 900


class Box:
    def __init__(self, kind, x, y, w, h, **kw):
        self.kind, self.x, self.y, self.w, self.h, self.kw, self.children = kind, x, y, w, h, kw, []

    def add(self, b):
        self.children.append(b); return b

    def xml(self, ids):
        ids[0] += 1
        a = (f"h='{round(self.h / H_ * 100000)}' id='{ids[0]}' w='{round(self.w / W_ * 100000)}' "
             f"x='{round(self.x / W_ * 100000)}' y='{round(self.y / H_ * 100000)}'")
        style = (f"<zone-style><format attr='border-color' value='{SURF}' /><format attr='border-style' value='none' />"
                 f"<format attr='margin' value='6' /></zone-style>")
        if self.kind == "sheet":
            return f"<zone {a} name={q(self.kw['name'])} show-title='true'>{style}</zone>"
        if self.kind == "text":
            runs = "".join(f"<run bold={q('true' if b else 'false')} fontcolor={q(c)} fontsize={q(fs)}>{escape(t)}</run>"
                           + ("<run>Æ&#10;</run>" if nl else "") for t, b, c, fs, nl in self.kw["runs"])
            return f"<zone {a} type-v2='text'><formatted-text>{runs}</formatted-text>{style}</zone>"
        if self.kind == "param":
            return f"<zone {a} mode={q(self.kw.get('mode', 'compact'))} param={q(self.kw['param'])} type-v2='paramctrl'>{style}</zone>"
        inner = "".join(c.xml(ids) for c in self.children)
        param = f" param={q(self.kw['param'])}" if "param" in self.kw else ""
        return f"<zone {a}{param} type-v2={q(self.kind)}>{inner}{style}</zone>"


class Workbook:
    def __init__(self, title, data_dir, footer):
        self.title, self.data_dir, self.footer = title, Path(data_dir), footer
        self.params, self.sources, self.sheets, self.dashboards = {}, [], [], []

    # ---- building blocks
    def param_list(self, caption, members, default, datatype="string", aliases=None):
        p = Param(len(self.params) + 1, caption, datatype, default, members=members, aliases=aliases)
        self.params[p.name] = p; return p

    def param_range(self, caption, lo, hi, step, default, datatype="real"):
        p = Param(len(self.params) + 1, caption, datatype, default, rng=(lo, hi, step))
        self.params[p.name] = p; return p

    def source(self, key, csv, caption, dims=(), force_string=()):
        s = Source(self.data_dir, key, csv, caption, dims, force_string)
        self.sources.append(s); return s

    def sheet(self, name, src, mark, title=None):
        s = Sheet(self, name, src, mark, title)
        self.sheets.append(s); return s

    @staticmethod
    def param_column(row, x, y, w, h, params):
        """A vertical stack of parameter controls inside a layout row."""
        col = row.add(Box("layout-flow", x, y, w, h, param="vert"))
        hh = h // len(params)
        for i, p in enumerate(params):
            col.add(Box("param", x, y + i * hh, w, hh, param=p.ref, mode="slider" if p.rng else "compact"))
        return col

    def row_of(self, page, y, h, names_widths):
        r = page.add(Box("layout-flow", 0, y, W_, h, param="horz"))
        x = 0
        for nm, w in names_widths:
            if isinstance(nm, tuple) and nm[0] == "params":  # ("params", [Param, ...]) control panel
                Workbook.param_column(r, x, y, w, h, nm[1])
            elif isinstance(nm, tuple):  # ("col", [(name, height), ...]) stacked column
                col = r.add(Box("layout-flow", x, y, w, h, param="vert"))
                yy = y
                for sub, sh in nm[1]:
                    col.add(Box("sheet", x, yy, w, sh, name=sub)); yy += sh
            else:
                r.add(Box("sheet", x, y, w, h, name=nm))
            x += w
        return r

    def dashboard(self, name, title, sub, params, layout, header_h=110, header_params=None):
        root = Box("layout-basic", 0, 0, W_, H_)
        page = root.add(Box("layout-flow", 0, 0, W_, H_, param="vert"))
        hdr = page.add(Box("layout-flow", 0, 0, W_, header_h, param="horz"))
        all_params, params = params, (params if header_params is None else header_params)
        pw = 300 if len(params) <= 2 else 600
        tw = W_ - pw
        hdr.add(Box("text", 0, 0, tw, header_h, runs=[(title, True, INK, "22", True), (sub, False, INK2, "11", True),
                                                      (self.footer, False, "#8a8983", "9", False)]))
        cols = 1 if len(params) <= 2 else 2
        per_col = max(1, -(-len(params) // cols))
        grid = hdr.add(Box("layout-flow", tw, 0, pw, header_h, param="horz"))
        if not params:
            grid.add(Box("text", tw, 0, pw, header_h, runs=[(" ", False, INK2, "9", False)]))
        for ci in range(cols):
            chunk = [p for i, p in enumerate(params) if i // per_col == ci]
            if not chunk:
                continue
            c = grid.add(Box("layout-flow", tw + ci * (pw // cols), 0, pw // cols, header_h, param="vert"))
            hh = header_h // len(chunk)
            for i, p in enumerate(chunk):
                c.add(Box("param", tw + ci * (pw // cols), i * hh, pw // cols, hh, param=p.ref,
                          mode="slider" if p.rng else "compact"))
        layout(page)
        used = set()

        def walk(b):
            if b.kind == "sheet":
                used.add(b.kw["name"])
            for ch in b.children:
                walk(ch)
        walk(root)
        pdeps = ("<datasources><datasource name='Parameters' /></datasources><datasource-dependencies datasource='Parameters'>"
                 + "".join(p.xml() for p in all_params) + "</datasource-dependencies>") if all_params else ""
        ids = [3]
        xml = (f"<dashboard name={q(name)}><style><style-rule element='table'><format attr='background-color' value='{SURF}' />"
               f"</style-rule></style><size maxheight='{H_}' maxwidth='{W_}' minheight='{H_}' minwidth='{W_}' sizing-mode='fixed' />"
               f"{pdeps}<zones>{root.xml(ids)}</zones><simple-id uuid={q(sid(self.title + 'db' + name))} /></dashboard>")
        self.dashboards.append((name, xml, sorted(used)))

    # ---- output
    def xml(self):
        pal = (f"<color-palette name='Portfolio Focus' type='regular'><color>{BLUE}</color><color>{ORANGE}</color><color>{GRAY}</color></color-palette>"
               f"<color-palette name='Portfolio Diverging' type='ordered-diverging'><color>{ORANGE}</color><color>{MID}</color><color>{BLUE}</color></color-palette>"
               f"<color-palette name='Portfolio Sequential' type='ordered-sequential'>" + "".join(f"<color>{c}</color>" for c in SEQ) + "</color-palette>")
        style = ("<style><style-rule element='all'><format attr='font-family' value='Tableau Book' /></style-rule>"
                 f"<style-rule element='worksheet'><format attr='font-family' value='Tableau Book' /><format attr='color' value='{INK2}' /></style-rule></style>")
        pds = ("<datasource hasconnection='false' inline='true' name='Parameters' version='18.1'><aliases enabled='yes' />"
               + "".join(p.xml() for p in self.params.values()) + "</datasource>") if self.params else ""
        cards = ("<cards><edge name='left'><strip size='160'><card type='pages' /><card type='filters' /><card type='marks' />"
                 "</strip></edge><edge name='top'><strip size='2147483647'><card type='columns' /></strip>"
                 "<strip size='2147483647'><card type='rows' /></strip><strip size='31'><card type='title' /></strip></edge></cards>")
        win = []
        for name, _, used in self.dashboards:
            vp = "".join(f"<viewpoint name={q(u)} />" for u in used)
            win.append(f"<window class='dashboard' maximized='true' name={q(name)}><viewpoints>{vp}</viewpoints>"
                       f"<active id='-1' /><simple-id uuid={q(sid(self.title + 'win' + name))} /></window>")
        for s in self.sheets:
            win.append(f"<window class='worksheet' hidden='true' maximized='true' name={q(s.name)}>{cards}"
                       f"<simple-id uuid={q(sid(self.title + 'win' + s.name))} /></window>")
        return ("<?xml version='1.0' encoding='utf-8' ?>\n"
                "<workbook original-version='26.1' source-build='0.0.0 (0000.0.0.0)' source-platform='win' version='26.1' "
                "xmlns:user='http://www.tableausoftware.com/xml/user'>"
                "<document-format-change-manifest><ManifestByVersion /></document-format-change-manifest>"
                f"<preferences><preference name='ui.encoding.shelf.height' value='24' /><preference name='ui.shelf.height' value='26' />{pal}</preferences>"
                f"{style}<datasources>{pds}{''.join(s.xml() for s in self.sources)}</datasources>"
                f"<worksheets>{''.join(s.xml() for s in self.sheets)}</worksheets>"
                f"<dashboards>{''.join(x for _, x, _ in self.dashboards)}</dashboards>"
                f"<windows source-height='30'>{''.join(win)}</windows>"
                "<explain-data enabled-for-viewer='true' extreme-values-enabled-for-all='true'><explanation-types /></explain-data></workbook>")

    def save(self, out_twbx, images=(), xsd=None):
        from lxml import etree
        doc = etree.fromstring(self.xml().encode("utf-8"))
        twb_name = Path(out_twbx).with_suffix(".twb").name
        twb_bytes = etree.tostring(doc, pretty_print=True, xml_declaration=True, encoding="utf-8")
        # sanity: every sheet placed on a dashboard exists, every calc dependency exists
        names = {s.name for s in self.sheets}
        for _, _, used in self.dashboards:
            missing = set(used) - names
            assert not missing, f"dashboard references unknown sheets {missing}"
        for s in self.sources:
            known = {c for c, _ in s.cols} | set(s.calcs)
            for c, deps in s.calc_deps.items():
                bad = set(deps) - known
                assert not bad, f"{s.caption}.{c} depends on unknown {bad}"
        if xsd:
            schema = etree.XMLSchema(etree.parse(str(xsd)))
            ok = schema.validate(doc)
            print("XSD valid:", ok)
            for e in list(schema.error_log)[:20]:
                print(f"  line {e.line}: {e.message[:300]}")
            if not ok:
                sys.exit(1)
        with zipfile.ZipFile(out_twbx, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(twb_name, twb_bytes)
            for s in self.sources:
                z.write(self.data_dir / s.csv, f"Data/data/{s.csv}")
            for img in images:
                z.write(img, f"Image/{Path(img).name}")
        print(out_twbx, Path(out_twbx).stat().st_size // 1024, "KB;", len(self.sheets), "sheets,", len(self.dashboards), "dashboards")
        return twb_bytes
