#!/usr/bin/env python3
"""
Build the browse artefacts for the pre-generated SIGRID country grids:

  SIGRID_country_grids.kmz  one placemark per country, popup links to its ZIP
  index.html                all countries + methodology + QA + checksums

Pins are the area-weighted centroid of each country's districts, using a circular
mean for longitude so antimeridian countries (Fiji, Kiribati, NZ, Russia) do not
land in the wrong ocean, then snapped onto the nearest polygon so the pin is
always on that country's land.

Usage:
    python make_kmz_html.py --countries countries.csv --manifest output/manifest.csv \
        --boundaries sigrid_cache --out ./site \
        --base-url https://www.openforis.org/fileadmin/SIGRID_1000m_grids \
        --zip-url  https://www.openforis.org/fileadmin/SIGRID_1000m_grids/per_country

Scripts, index.html and the KMZ are expected at --base-url; the per-country ZIPs
and manifest.csv at --zip-url (default <base-url>/per_country).
"""
import argparse, os, math, html, json, zipfile, re, unicodedata, warnings
import datetime as dt
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

warnings.filterwarnings("ignore")
DENSITIES = [1, 2, 3, 4, 5, 6, 8, 9, 10, 12, 15, 16, 20, 25, 30, 50, 100]


def slugify(s, fallback=""):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s or fallback


def fix_valid(g):
    bad = ~g.geometry.is_valid
    if bad.any():
        g.loc[bad, "geometry"] = g.loc[bad, "geometry"].buffer(0)
    return g[~g.geometry.is_empty & g.geometry.notna()]


def better_pin(iso2, boundaries_dir):
    """Area-weighted centroid, circular mean in longitude, snapped to land."""
    p = os.path.join(boundaries_dir, f"{iso2}_adm2.geojson")
    if not os.path.exists(p):
        return None
    try:
        g = fix_valid(gpd.read_file(p))
        c = g.geometry.centroid
        w = g.geometry.area.values
        if w.sum() <= 0:
            w = None
        lat = float((c.y.values * w).sum() / w.sum()) if w is not None else float(c.y.mean())
        rad = [math.radians(v) for v in c.x.values]
        ws = w if w is not None else [1.0] * len(rad)
        sx = sum(wi * math.cos(a) for wi, a in zip(ws, rad))
        sy = sum(wi * math.sin(a) for wi, a in zip(ws, rad))
        lon = math.degrees(math.atan2(sy, sx))
        pt = Point(lon, lat)
        if not g.contains(pt).any():                 # snap onto land
            rp = g.loc[g.distance(pt).idxmin(), "geometry"].representative_point()
            lon, lat = rp.x, rp.y
        return round(lon, 5), round(lat, 5)
    except Exception:
        return None


def zip_name(row):
    c = slugify(row["name"], row["iso2"])
    return f"{c}_grids.zip" if row["has_adm"] else f"{c}_grids_no_districts.zip"


ICON_BASE = "https://maps.google.com/mapfiles/kml/paddle"


def _style(sid, icon, scale, label):
    """One <Style>. hotSpot puts the paddle's tip on the coordinate."""
    return (f'<Style id="{sid}">'
            f'<IconStyle><scale>{scale}</scale>'
            f'<Icon><href>{ICON_BASE}/{icon}.png</href></Icon>'
            f'<hotSpot x="0.5" y="0" xunits="fraction" yunits="fraction"/>'
            f'</IconStyle>'
            f'<LabelStyle><scale>{label}</scale></LabelStyle>'
            f'</Style>')


def _stylemap(sid):
    """Normal + highlight pair, so the pin grows on hover."""
    return (f'<StyleMap id="{sid}">'
            f'<Pair><key>normal</key><styleUrl>#{sid}_n</styleUrl></Pair>'
            f'<Pair><key>highlight</key><styleUrl>#{sid}_h</styleUrl></Pair>'
            f'</StyleMap>')


def kml_doc(df, zip_url, stamp):
    P = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         '<name>SIGRID 1 km country grids</name>',
         f'<description><![CDATA[Pre-generated SIGRID 1000 m sampling grids, clipped '
         f'per country and tagged with UN 2023 province (ADM1NM) and district (ADM2NM) '
         f'names. Click a placemark to download that country\'s ZIP.<br/>'
         f'Generated {stamp}.]]></description>',
         # Paddle icons are drawn pointing down, so hotSpot pins the tip to the
         # actual coordinate. Without it the marker floats above the country.
         _style("has_n", "red-circle", 1.5, 0.9),
         _style("has_h", "red-circle", 1.9, 1.1),
         _style("none_n", "ylw-circle", 1.2, 0.8),
         _style("none_h", "ylw-circle", 1.6, 1.0),
         _stylemap("has"),
         _stylemap("none"),
         '<Folder><name>With district names</name>']
    for group, folder in ((True, "With district names"), (False, "Outline only (no districts)")):
        if not group:
            P += ['</Folder>', f'<Folder><name>{folder}</name>']
        for r in df[df.has_adm == group].itertuples():
            if pd.isna(r.clon) or pd.isna(r.clat):
                continue
            zn = f"{slugify(r.name, r.iso2)}_grids{'' if group else '_no_districts'}.zip"
            url = f"{zip_url}/{zn}"
            adm = (f"{int(r.n_adm1)} provinces / {int(r.n_adm2)} districts" if group
                   else "no district names in UN 2023 (country outline only)")
            plots = f"{int(r.plots):,} plots (1&#215;1 km)" if r.plots else "not generated yet"
            desc = ("<![CDATA[<b>" + html.escape(str(r.name)) + f"</b> ({r.iso2.upper()})<br/>"
                    f"{adm}<br/>{plots}<br/><br/>"
                    f'<a href="{url}">Download {zn}</a><br/>'
                    "<small>One CSV per sampling density, 1&#215;1 km to 100&#215;100 km</small>]]>")
            P += ['<Placemark>', f'<name>{html.escape(str(r.name))}</name>',
                  f"<styleUrl>#{'has' if group else 'none'}</styleUrl>",
                  f'<description>{desc}</description>',
                  f'<Point><coordinates>{r.clon},{r.clat},0</coordinates></Point>',
                  '</Placemark>']
    P += ['</Folder>', '</Document></kml>']
    return "\n".join(P)


def build_html(df, base_url, zip_url, stats, stamp):
    rows = []
    for r in df.itertuples():
        zn = f"{slugify(r.name, r.iso2)}_grids{'' if r.has_adm else '_no_districts'}.zip"
        badge = ('<span class="ok">yes</span>' if r.has_adm
                 else '<span class="no">outline only</span>')
        a1 = int(r.n_adm1) if r.has_adm else "&ndash;"
        a2 = int(r.n_adm2) if r.has_adm else "&ndash;"
        pl = f"{int(r.plots):,}" if r.plots else "&ndash;"
        ra = f"{r.ratio:.3f}" if r.ratio == r.ratio and r.ratio else "&ndash;"
        m5 = f'<code class="md5">{r.md5[:10]}&hellip;</code>' if isinstance(r.md5, str) and r.md5 else "&ndash;"
        rows.append(f"<tr><td>{html.escape(str(r.name))}</td><td>{r.iso2.upper()}</td>"
                    f"<td class='n'>{a1}</td><td class='n'>{a2}</td><td class='n'>{pl}</td>"
                    f"<td class='n'>{ra}</td><td>{badge}</td>"
                    f"<td><a href='{zip_url}/{zn}'>{zn}</a></td><td>{m5}</td></tr>")
    table = "\n".join(rows)
    dens = ", ".join(f"{d}&times;{d}&nbsp;km" for d in DENSITIES)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SIGRID 1 km country grids &ndash; with province &amp; district names</title>
<style>
 body{{font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#1c2321;background:#fff}}
 .wrap{{max-width:1120px;margin:0 auto;padding:32px 20px 80px}}
 h1{{font-size:1.9rem;margin:.2em 0 .1em}} h2{{font-size:1.25rem;margin:2em 0 .5em;border-bottom:2px solid #e6ebe8;padding-bottom:.3em}}
 .sub{{color:#5b6b63;margin-top:0}}
 .cards{{display:flex;gap:14px;flex-wrap:wrap;margin:24px 0}}
 .card{{flex:1 1 140px;background:#f4f8f5;border:1px solid #dbe6de;border-radius:10px;padding:14px}}
 .card b{{display:block;font-size:1.45rem;color:#1f7a4d}} .card span{{font-size:.85rem;color:#5b6b63}}
 table{{border-collapse:collapse;width:100%;font-size:.9rem;margin-top:12px}}
 th,td{{border-bottom:1px solid #e6ebe8;padding:7px 9px;text-align:left}}
 th{{background:#f4f8f5;position:sticky;top:0;cursor:pointer}}
 td.n{{text-align:right;font-variant-numeric:tabular-nums}}
 .ok{{color:#1f7a4d;font-weight:600}} .no{{color:#a8730d}}
 code{{background:#f2f4f3;padding:1px 5px;border-radius:4px;font-size:.9em}} .md5{{font-size:.8em;color:#5b6b63}}
 pre{{background:#f7f9f8;border:1px solid #e6ebe8;border-radius:8px;padding:12px;overflow:auto}}
 .note{{background:#fff8e9;border-left:4px solid #e0a92a;padding:10px 14px;border-radius:0 6px 6px 0;margin:16px 0}}
 .disc{{font-size:.85rem;color:#5b6b63;border-top:1px solid #e6ebe8;margin-top:40px;padding-top:14px}}
 input[type=search]{{width:100%;padding:9px 12px;border:1px solid #ccd6d0;border-radius:8px;margin-top:14px;font-size:1rem}}
</style></head><body><div class="wrap">

<h1>SIGRID 1&nbsp;km country grids</h1>
<p class="sub">Every SIGRID 1000&nbsp;m sampling plot, clipped to its country and tagged with the
UN&nbsp;2023 province (<code>ADM1NM</code>) and district (<code>ADM2NM</code>) it falls in &ndash;
pre-generated and split by sampling density. Generated {stamp}.</p>

<div class="cards">
  <div class="card"><b>{stats['countries']}</b><span>countries</span></div>
  <div class="card"><b>{stats['with_adm']}</b><span>with district names</span></div>
  <div class="card"><b>{stats['districts']:,}</b><span>ADM2 districts</span></div>
  <div class="card"><b>{len(DENSITIES)}</b><span>densities per country</span></div>
  <div class="card"><b>{stats['tiles']}</b><span>SIGRID tiles used</span></div>
</div>

<p>Prefer a map? Open <a href="{base_url}/SIGRID_country_grids.kmz">SIGRID_country_grids.kmz</a>
in Google Earth and click any country to download its grids.</p>
<p class="sub">All per-country ZIPs and <a href="{zip_url}/manifest.csv">manifest.csv</a> live in
<code>{zip_url}/</code>; the scripts and this page sit one level up in
<code>{base_url}/</code>.</p>

<h2>What is in each ZIP</h2>
<p>Each <code>&lt;Country&gt;_grids.zip</code> holds one CSV per sampling density &ndash; {dens} &ndash;
named like <code>Benin_1x1km.csv</code>, <code>Benin_2x2km.csv</code>, plus a README with the
provenance and QA figures for that country.</p>
<pre>Benin_1x1km.csv    CE_ID, yCoordinate, xCoordinate, ADM1NM, ADM2NM, grid_1 &hellip; grid_100
Benin_2x2km.csv    CE_ID, yCoordinate, xCoordinate, ADM1NM, ADM2NM</pre>
<p>The 1&times;1&nbsp;km file is the full base grid and keeps the <code>grid_*</code> membership
flags. The coarser files are strict subsets of it, so their flag columns are dropped &ndash; the
filename already tells you the density. Coordinates are latitude/longitude in WGS&nbsp;84
(EPSG:4326). Plot counts fall off roughly as 1/N&sup2;.</p>

<h2>How these were generated</h2>
<p>One script, <a href="{base_url}/build_all_countries.py">build_all_countries.py</a>
(single-country version: <a href="{base_url}/sigrid_country.py">sigrid_country.py</a>), does the whole job.</p>

<p><b>1. Boundaries.</b> The UN&nbsp;2023 ADM2 boundaries are downloaded per country from the
EarthMap public store and stacked into one districts layer. Invalid geometries &ndash; 14 countries
have self-intersections, including India, Mexico and Australia &ndash; are repaired first.</p>

<p><b>2. Tile selection.</b> SIGRID publishes 10&deg;&nbsp;&times;&nbsp;10&deg; tiles. Instead of a
country's overall bounding box, the script takes the bounding box of <em>each polygon part</em> and
keeps only tiles that genuinely intersect a district, tested with a spatial index. This matters at
the antimeridian: a naive bounding box asks for 252 tiles for the United States; the real answer
is 35.</p>

<p><b>3. One pass per tile.</b> Processing is tile-centric: each of the {stats['tiles']} tiles is
downloaded and parsed exactly once, then joined against only the districts inside it, and matched
plots are appended to per-country parts. Looping country-by-country instead would re-parse shared
tiles roughly 2.4&times; over.</p>

<p><b>4. Clip and tag.</b> Plots are joined to districts with a point-in-polygon test
(<code>predicate="intersects"</code>, so a plot sitting exactly on a boundary line is kept rather
than dropped). Plots outside every district are discarded; the rest gain <code>ADM1NM</code> and
<code>ADM2NM</code>. A plot on a shared border is assigned to one district only, never duplicated.</p>

<p><b>5. QA.</b> On a 1&nbsp;km grid the plot count should equal the country's land area in km&sup2;.
Every country's area is computed in an equal-area projection (Mollweide) and the ratio
<code>plots / km&sup2;</code> is recorded &ndash; it lands at 0.99&ndash;1.00 throughout. Anything
outside 0.97&ndash;1.01 is flagged in <a href="{zip_url}/manifest.csv">manifest.csv</a> rather than
shipped silently.</p>

<p><b>6. Split and package.</b> Tagged plots are split on the <code>grid_N</code> flags into one CSV
per density and packed into the country ZIP, written atomically so an interrupted run never
publishes a truncated file. An MD5 for every ZIP is listed below.</p>

<div class="note"><b>Two caveats worth knowing.</b>
{stats['countries'] - stats['with_adm']} of the {stats['countries']} countries ship a UN&nbsp;2023
ADM2 file that is only a national outline, with empty <code>ADM1NM</code>/<code>ADM2NM</code>.
Their grids are still clipped correctly to the national border, but the district columns are blank;
they are marked <span class="no">outline only</span> and named
<code>&lt;Country&gt;_grids_no_districts.zip</code> so nobody downloads one by mistake.
Separately, because national boundaries are generalized, a small number of genuinely coastal plots
can fall just outside the polygon and are not included &ndash; this is the ~0.5&#37; the QA ratio
shows. Widening the tolerance to recover them pulls in offshore sea points instead (Cyprus goes from
0.996 to 1.035), so we prefer the small, honest undercount.</div>

<h2>Reproducing this</h2>
<pre>pip install pandas geopandas
python sigrid_country.py bj --split-by-density      # one country
python build_all_countries.py --out ./output --jobs 2   # everything</pre>
<p>The batch script is resumable: finished countries and finished tiles are both skipped, so you can
interrupt and restart freely. Budget ~3&nbsp;GB for the tile cache and about 1.5&nbsp;GB of RAM per
worker.</p>

<h2>All countries</h2>
<input type="search" id="q" placeholder="Filter by country or ISO code&hellip;">
<table id="t"><thead><tr><th>Country</th><th>ISO2</th><th>Prov.</th><th>Districts</th>
<th>Plots (1&times;1&nbsp;km)</th><th>QA ratio</th><th>District names</th><th>Download</th><th>MD5</th>
</tr></thead><tbody>
{table}
</tbody></table>

<p class="disc">Administrative boundaries: United Nations 2023 (UN Geospatial, ADM2), obtained via
the EarthMap public boundary store. The designations employed and the presentation of material on
this product do not imply the expression of any opinion whatsoever on the part of the United Nations
or FAO concerning the legal status of any country, territory, city or area or of its authorities, or
concerning the delimitation of its frontiers or boundaries. Plot grid: SIGRID 1000&nbsp;m,
Open&nbsp;Foris.</p>

<script>
const q=document.getElementById('q'),rows=[...document.querySelectorAll('#t tbody tr')];
q.addEventListener('input',()=>{{const v=q.value.toLowerCase();
 rows.forEach(r=>{{r.style.display=r.textContent.toLowerCase().includes(v)?'':'none';}});}});
document.querySelectorAll('#t th').forEach((th,i)=>th.addEventListener('click',()=>{{
 const tb=document.querySelector('#t tbody');const asc=!(th.dataset.asc==='1');th.dataset.asc=asc?'1':'0';
 const num=v=>{{const n=parseFloat(v.replace(/[^0-9.\\-]/g,''));return isNaN(n)?null:n;}};
 [...tb.rows].sort((a,b)=>{{const x=a.cells[i].textContent.trim(),y=b.cells[i].textContent.trim();
  const nx=num(x),ny=num(y); if(nx!==null&&ny!==null)return asc?nx-ny:ny-nx;
  return asc?x.localeCompare(y):y.localeCompare(x);}}).forEach(r=>tb.appendChild(r));}}));
</script>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="countries.csv")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--boundaries", default="", help="dir with <iso2>_adm2.geojson for good pins")
    ap.add_argument("--out", default="./site")
    ap.add_argument("--base-url", default="https://www.openforis.org/fileadmin/SIGRID_1000m_grids",
                    help="where the scripts, KMZ and index.html live")
    ap.add_argument("--zip-url", default="",
                    help="where the per-country ZIPs live "
                         "(default: <base-url>/per_country)")
    a = ap.parse_args()
    a.base_url = a.base_url.rstrip("/")
    a.zip_url = (a.zip_url or f"{a.base_url}/per_country").rstrip("/")
    os.makedirs(a.out, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    df = pd.read_csv(a.countries)
    if "status" in df.columns:
        df = df[df.status == "ok"].copy()
    df["has_adm"] = df.n_adm1 > 0
    for col in ("plots", "ratio", "md5"):
        if col not in df.columns:
            df[col] = 0 if col != "md5" else ""
    if a.manifest and os.path.exists(a.manifest):
        m = pd.read_csv(a.manifest)
        keep = [c for c in ("iso2", "plots", "ratio", "md5", "has_adm_names") if c in m.columns]
        df = df.drop(columns=["plots", "ratio", "md5"]).merge(m[keep], on="iso2", how="left")
        if "has_adm_names" in df.columns:
            df["has_adm"] = df["has_adm_names"].fillna(df["has_adm"]).astype(bool)
        df["plots"] = df["plots"].fillna(0)

    # better pins where boundaries are available
    if a.boundaries:
        fixed = 0
        for i, r in df.iterrows():
            p = better_pin(r.iso2, a.boundaries)
            if p:
                df.at[i, "clon"], df.at[i, "clat"] = p
                fixed += 1
        print(f"recomputed {fixed} pins from boundaries")

    df = df.sort_values("name")
    tiles = 0
    tj = os.path.join(os.path.dirname(a.countries) or ".", "country_tiles.json")
    if os.path.exists(tj):
        U = set()
        for v in json.load(open(tj)).values():
            U |= {tuple(t) for t in v}
        tiles = len(U)
    stats = dict(countries=len(df), with_adm=int(df.has_adm.sum()),
                 districts=int(df.loc[df.has_adm, "n_adm2"].sum()), tiles=tiles)

    kmz = os.path.join(a.out, "SIGRID_country_grids.kmz")
    with zipfile.ZipFile(kmz, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml_doc(df, a.zip_url, stamp))
    hp = os.path.join(a.out, "index.html")
    open(hp, "w", encoding="utf-8").write(build_html(df, a.base_url, a.zip_url, stats, stamp))
    print(f"KMZ  -> {kmz} ({os.path.getsize(kmz)/1024:.1f} KB)")
    print(f"HTML -> {hp} ({os.path.getsize(hp)/1024:.1f} KB)")
    print("stats:", stats)
    print("zip links ->", a.zip_url)


if __name__ == "__main__":
    main()
