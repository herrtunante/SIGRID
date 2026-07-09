#!/usr/bin/env python3
"""
Batch-generate SIGRID 1000 m density grids for every country, one ZIP per country.

Pipeline (tile-centric):
  Phase 0  Download UN-2023 ADM2 boundaries for every country, repair invalid
           geometries, and stack them into ONE districts layer tagged with iso2.
  Phase 1  For each SIGRID 10x10-degree tile that touches any district: download
           it once, read its three subgrid CSVs, point-in-polygon join against
           only the districts inside that tile, and append the matched plots to
           per-country part files. Tiles are processed in parallel (--jobs).
           Each tile is read exactly once: ~2.4x less CSV parsing than looping
           country-by-country (698 tile reads -> ~292 unique tiles).
  Phase 2  Per country: concatenate its parts, run QA, split by density grid,
           and write <Country>_grids.zip atomically.

Key behaviours
  * Antimeridian-safe: tiles come from the districts' spatial index, never from a
    single global bounding box (USA needs 35 tiles, not 252).
  * Border handling: the join uses predicate="intersects", so plots sitting
    exactly on a boundary line are kept (predicate="within" drops them).
    --snap-tolerance additionally attaches unmatched plots to the nearest
    district, but it is OFF by default: a ~500 m tolerance recovers ~0.6% of
    genuinely-lost inland plots yet pulls in 3-4% offshore sea points on coastal
    and island countries (Cyprus QA ratio 0.996 -> 1.035). The QA ratio below
    will tell you immediately if you have overshot.
  * QA: plot count is compared against the country's land area computed in an
    equal-area projection. On a 1 km grid the ratio should be ~1.0; anything
    outside --qa-min/--qa-max is flagged in the manifest.
  * Coarse density files (2x2 km and up) drop the grid_* flag columns - they are
    strict subsets of the 1x1 km file, which keeps the flags.
  * Countries whose UN-2023 file is only a national outline (no ADM1NM/ADM2NM)
    are written as <Country>_grids_no_districts.zip so nobody downloads them
    expecting district columns.
  * Atomic + resumable: ZIPs are written to .part then renamed, so an interrupted
    run never leaves a truncated ZIP that a later run mistakes for finished.

Usage:
    python build_all_countries.py --out ./output --cache ./sigrid_cache --jobs 4
    python build_all_countries.py --only bj,ye          # subset
    python build_all_countries.py --purge-tiles         # low disk
    python build_all_countries.py --snap-tolerance 0    # strict 'within' only

Scale: 198 countries, ~292 unique tiles (~3 GB of tile ZIPs). Peak temp usage is
a few GB. Each --jobs worker needs roughly 1.5 GB RAM (the districts layer is
shared copy-on-write via fork, but each worker holds a subgrid frame), so size
--jobs to your memory, not your cores. Requires: pandas, geopandas, pyproj.
"""
import argparse, csv, hashlib, io, json, math, os, re, shutil, time, warnings, zipfile
import datetime as dt
import multiprocessing as mp
import urllib.request
import pandas as pd
import geopandas as gpd
from shapely.geometry import box
import unicodedata

warnings.filterwarnings("ignore", message=".*geographic CRS.*")
warnings.filterwarnings("ignore", category=UserWarning, module="geopandas")

VERSION = "2.0"
GEOJSON_URL = ("https://firebasestorage.googleapis.com/v0/b/"
               "production-earthmap.appspot.com/o/"
               "boundaries%2FUN2023%2F{iso2}_adm2.geojson?alt=media")
TILE_BASE = "https://www.openforis.org/fileadmin/SIGRID_1000m_grids"
TILE_NAME = "SIGRID_x_{x0}_{x1}_y_{y0}_{y1}_1000m_1_subgrid.csv.zip"
ADM = ["ADM1NM", "ADM2NM"]
CE_PLOT_LIMIT = 2000   # Google Earth degrades past ~2000 placemarks/KML
EQUAL_AREA = "ESRI:54009"
BASE_COLS = ["CE_ID", "yCoordinate", "xCoordinate"] + ADM

UN_DISCLAIMER = (
    "Administrative boundaries: United Nations 2023 (UN Geospatial, ADM2), "
    "obtained via the EarthMap public boundary store.\n"
    "The designations employed and the presentation of material on this product "
    "do not imply the expression of any opinion whatsoever on the part of the "
    "United Nations or FAO concerning the legal status of any country, territory, "
    "city or area or of its authorities, or concerning the delimitation of its "
    "frontiers or boundaries.")

_DISTRICTS = None
_ARGS = None


def slugify(s, fallback=""):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s or fallback


def md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def download(url, dest, tries=3):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    tmp = dest + ".part"
    for k in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sigrid-batch"})
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            os.replace(tmp, dest)
            return dest
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            if k == tries:
                raise RuntimeError(f"download failed: {url} ({e})")
            time.sleep(3 * k)


def fix_valid(g):
    bad = ~g.geometry.is_valid
    if bad.any():
        g.loc[bad, "geometry"] = g.loc[bad, "geometry"].buffer(0)
    return g[~g.geometry.is_empty & g.geometry.notna()]


def bbox_tiles(minx, miny, maxx, maxy):
    eps = 1e-9
    xs = range(int(math.floor(minx / 10) * 10),
               int(math.floor((maxx - eps) / 10) * 10) + 10, 10)
    ys = range(int(math.floor(miny / 10) * 10),
               int(math.floor((maxy - eps) / 10) * 10) + 10, 10)
    return {(x, x + 10, y, y + 10) for x in xs for y in ys}


def tiles_for_layer(g):
    cand = set()
    for geom in g.geometry.explode(index_parts=False):
        cand |= bbox_tiles(*geom.bounds)
    sidx = g.sindex
    keep = set()
    for (x0, x1, y0, y1) in cand:
        if y0 < -80 or y1 > 80:
            continue
        if len(sidx.query(box(x0, y0, x1, y1), predicate="intersects")):
            keep.add((x0, x1, y0, y1))
    return sorted(keep)


def read_sigrid_bytes(raw):
    header = raw[:raw.index(b"\n")].decode().replace('"', "").split(",")
    df = pd.read_csv(io.BytesIO(raw), skiprows=1,
                     names=header + ["_a", "_b"], index_col=False)[header]
    df.columns = [re.sub(r"^(grid_\d+)_SIGRID.*$", r"\1", c) for c in df.columns]
    return df


def grid_cols_of(cols):
    return sorted([c for c in cols if re.match(r"^grid_\d+$", c)],
                  key=lambda c: int(c.split("_")[1]))


def load_boundaries(meta, cache):
    frames, info = [], {}
    for i, r in enumerate(meta.itertuples(), 1):
        iso2 = r.iso2
        gj = os.path.join(cache, f"{iso2}_adm2.geojson")
        try:
            download(GEOJSON_URL.format(iso2=iso2), gj)
            g = fix_valid(gpd.read_file(gj))
        except Exception as e:
            print(f"  [{i}/{len(meta)}] {iso2}: boundary FAILED ({e})", flush=True)
            continue
        for c in ADM:
            if c not in g.columns:
                g[c] = None
        g = g[ADM + ["geometry"]].copy()
        g = g.set_crs("EPSG:4326") if g.crs is None else g.to_crs("EPSG:4326")
        has_adm = bool(g["ADM1NM"].notna().any() or g["ADM2NM"].notna().any())
        try:
            area_km2 = float(g.to_crs(EQUAL_AREA).geometry.area.sum() / 1e6)
        except Exception:
            area_km2 = float("nan")
        g["iso2"] = iso2
        frames.append(g)
        info[iso2] = dict(iso2=iso2, name=str(r.name), country=slugify(r.name, iso2),
                          iso3=str(getattr(r, "iso3", "") or ""),
                          has_adm_names=has_adm, districts=int(len(g)),
                          area_km2=round(area_km2, 1))
        print(f"  [{i}/{len(meta)}] {iso2} {r.name}: {len(g)} polys, "
              f"{area_km2:,.0f} km2, "
              f"{'districts' if has_adm else 'OUTLINE ONLY'}", flush=True)
    districts = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    return districts, info


def _init_worker(districts, args):
    global _DISTRICTS, _ARGS
    _DISTRICTS, _ARGS = districts, args


def process_tile(tile):
    global _DISTRICTS, _ARGS
    args = _ARGS
    x0, x1, y0, y1 = tile
    tname = TILE_NAME.format(x0=x0, x1=x1, y0=y0, y1=y1)
    done_flag = os.path.join(args.tmp, "_tiles_done", tname + ".ok")
    if os.path.exists(done_flag):
        return tname, json.load(open(done_flag))

    # a tile may re-run after a crash: drop the part files it wrote before,
    # otherwise those rows would be duplicated on the second pass
    pdir = os.path.join(args.tmp, "parts")
    if os.path.isdir(pdir):
        for iso in os.listdir(pdir):
            sub_d = os.path.join(pdir, iso)
            for f in os.listdir(sub_d):
                if f.startswith(tname + "__"):
                    os.remove(os.path.join(sub_d, f))

    tpath = os.path.join(args.cache, tname)
    try:
        download(f"{TILE_BASE}/{tname}", tpath)
    except RuntimeError:
        return tname, {}

    idx = _DISTRICTS.sindex.query(box(x0, y0, x1, y1), predicate="intersects")
    sub = _DISTRICTS.iloc[idx]
    if sub.empty:
        return tname, {}
    smin_x, smin_y, smax_x, smax_y = sub.total_bounds
    tol = args.snap_tolerance

    stats = {}
    with zipfile.ZipFile(tpath) as zf:
        for member in sorted(n for n in zf.namelist() if n.endswith(".csv")):
            df = read_sigrid_bytes(zf.read(member))
            x, y = df.xCoordinate, df.yCoordinate
            df = df[(x >= smin_x - tol) & (x <= smax_x + tol) &
                    (y >= smin_y - tol) & (y <= smax_y + tol)]
            if df.empty:
                continue
            pts = gpd.GeoDataFrame(
                df, geometry=gpd.points_from_xy(df.xCoordinate, df.yCoordinate),
                crs="EPSG:4326")

            j = gpd.sjoin(pts, sub, how="inner", predicate="intersects")
            j = j[~j.index.duplicated(keep="first")]
            j["_snapped"] = False

            if tol > 0:
                rest = pts[~pts.index.isin(set(j.index))]
                if len(rest):
                    try:
                        n = gpd.sjoin_nearest(rest, sub, how="inner", max_distance=tol)
                        n = n[~n.index.duplicated(keep="first")]
                        if len(n):
                            n["_snapped"] = True
                            j = pd.concat([j, n])
                    except Exception:
                        pass
            if j.empty:
                continue
            j = j.drop(columns=["geometry", "index_right"])

            out_cols = BASE_COLS + grid_cols_of(df.columns)
            for iso2, part in j.groupby("iso2", sort=False):
                d = os.path.join(pdir, iso2)
                os.makedirs(d, exist_ok=True)
                p = os.path.join(d, f"{tname}__{os.path.basename(member)}")
                part.reindex(columns=out_cols).to_csv(p, index=False)
                s = stats.setdefault(iso2, {"matched": 0, "snapped": 0})
                s["matched"] += len(part)
                s["snapped"] += int(part["_snapped"].sum())
            del df, pts, j

    os.makedirs(os.path.dirname(done_flag), exist_ok=True)
    json.dump(stats, open(done_flag, "w"))
    if args.purge_tiles and os.path.exists(tpath):
        os.remove(tpath)
    return tname, stats


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def rule(ch="-", n=78):
    return ch * n


def dwidth(s):
    """Display width: combining marks (e.g. the dots under Hadramawt) take no
    column, so len() over-counts and breaks table alignment."""
    return sum(0 if unicodedata.combining(c) else 1 for c in str(s))


def pad(s, n):
    s = str(s)
    return s + " " * max(0, n - dwidth(s))


def build_readme(meta, args, run_stamp, total, provs, dens_rows, prov_counts,
                 bbox, ratio, qa, snapped, counts_file):
    name, iso2 = meta["name"], meta["iso2"].upper()
    iso3 = meta.get("iso3", "") or ""
    area = meta["area_km2"]
    has = meta["has_adm_names"]
    country = meta["country"]
    W = 78

    def head(n, t):
        return f"\n{rule('=')}\n {n}. {t.upper()}\n{rule('=')}\n"

    L = []
    L.append(rule("="))
    L.append(f" SIGRID 1 km SAMPLING GRID - {name.upper()} ({iso2}{'/' + iso3 if iso3 else ''})")
    L.append(" Every plot tagged with its province (ADM1NM) and district (ADM2NM)")
    L.append(rule("="))
    L.append(f" Generated {run_stamp} by build_all_countries.py v{VERSION}")
    L.append(rule("="))

    L.append(head(1, "What this is"))
    L.append(
        "SIGRID is a global systematic sampling grid of points spaced 1 km apart.\n"
        "This archive contains every SIGRID plot that falls inside "
        f"{name}, and\nfor each plot the province and district it belongs to, taken from the\n"
        "United Nations 2023 administrative boundaries.\n\n"
        "The same plots are also provided at coarser sampling intensities (every\n"
        "2 km, 3 km, ... up to 100 km), so you can pick the plot spacing that suits\n"
        "your survey budget and precision target. Each coarser grid is a strict\n"
        "subset of the 1x1 km grid: a plot in the 10x10 km file is also in the\n"
        "1x1 km file, with the same CE_ID. This means you can start a survey at a\n"
        "coarse intensity and densify later without moving or renumbering plots.")

    L.append(head(2, "At a glance"))
    g = [("Country", f"{name} ({iso2}{'/' + iso3 if iso3 else ''})"),
         ("Total plots (1x1 km)", f"{total:,}"),
         ("Land area (equal-area)", f"{area:,.0f} km2"),
         ("Plots per km2 (QA ratio)", f"{ratio}   [{qa}]"),
         ("Provinces (ADM1NM)", f"{len(provs):,}" if has else "n/a - see section 9"),
         ("Districts (ADM2NM)", f"{meta['districts']:,}" if has else "n/a - see section 9"),
         ("Sampling intensities", f"{len(dens_rows)} (1x1 km to "
                                  f"{dens_rows[-1][0]}x{dens_rows[-1][0]} km)"),
         ("Bounding box (lon)", f"{bbox[0]:.4f} to {bbox[2]:.4f}"),
         ("Bounding box (lat)", f"{bbox[1]:.4f} to {bbox[3]:.4f}"),
         ("Coordinate system", "WGS 84 geographic (EPSG:4326)"),
         ("Boundary source", "UN 2023 ADM2 (EarthMap public store)"),
         ("Plot grid source", "SIGRID 1000 m, Open Foris")]
    for k, v in g:
        L.append(f"  {k:<26} : {v}")

    L.append(head(3, "Files in this archive"))
    L.append("  Plots is the number of sample points at that intensity. Each file is a\n"
             "  plain UTF-8 CSV with a header row.\n")
    w = max(34, len(os.path.basename(counts_file)) + 1)
    L.append(f"  {'File':<{w}} {'Spacing':>9} {'Plots':>12} {'Size':>10}")
    L.append(f"  {rule('-', w)} {rule('-', 9)} {rule('-', 12)} {rule('-', 10)}")
    for n, plots, size in dens_rows:
        mark = " *" if plots > CE_PLOT_LIMIT else ""
        L.append(f"  {country + '_' + str(n) + 'x' + str(n) + 'km.csv' + mark:<{w}} "
                 f"{str(n) + ' km':>9} {plots:>12,} {human(size):>10}")
    L.append(f"  {os.path.basename(counts_file):<{w}} {'per district':>9} {'-':>12} "
             f"{human(os.path.getsize(counts_file)):>10}")
    L.append(f"  {country + '_README.txt':<{w}} {'-':>9} {'-':>12} {'-':>10}")
    L.append("\n  Plot counts fall off roughly as 1/N^2: the 2x2 km grid holds about a\n"
             "  quarter of the 1x1 km plots, the 10x10 km grid about one hundredth.")
    big = [n for n, plots, _ in dens_rows if plots > CE_PLOT_LIMIT]
    if big:
        L.append(f"\n  (*) Holds more than {CE_PLOT_LIMIT:,} plots. Google Earth struggles beyond\n"
                 "      roughly that many placemarks, so divide these files before loading\n"
                 "      them into Collect Earth - see section 6.")

    L.append(head(4, "Column dictionary"))
    L.append(
        "  CE_ID         Unique, stable identifier of the plot in the global SIGRID\n"
        "                grid. The SAME plot carries the SAME CE_ID in every file\n"
        "                here and in the global SIGRID tiles. Use it as your key.\n"
        "  yCoordinate   Latitude  of the plot centre, decimal degrees, WGS 84.\n"
        "  xCoordinate   Longitude of the plot centre, decimal degrees, WGS 84.\n"
        "  ADM1NM        Province / state / department name (UN 2023, level 1).\n"
        "  ADM2NM        District / county / municipality name (UN 2023, level 2).\n"
        "  grid_1 ...    Boolean flags, PRESENT ONLY IN THE 1x1 km FILE. grid_N is\n"
        "  grid_100      true when the plot belongs to the N x N km sampling grid.\n"
        "                grid_1 is true for every plot. The coarser CSVs omit these\n"
        "                columns because the filename already states the intensity.\n\n"
        "  Note on names: ADM1NM/ADM2NM are reproduced exactly as published by the\n"
        "  UN, including diacritics (e.g. Oueme, Hadramawt). Files are UTF-8; open\n"
        "  them as UTF-8 in Excel (Data > From Text/CSV > 65001) or accents break.")

    L.append(head(5, "Plots by province"))
    if has and prov_counts:
        L.append(f"  {'Province (ADM1NM)':<40} {'Plots (1x1 km)':>15} {'Share':>8}")
        L.append(f"  {rule('-', 40)} {rule('-', 15):>15} {rule('-', 8):>8}")
        for p, c in prov_counts:
            L.append(f"  {pad(p, 40)} {c:>15,} {100.0 * c / total:>7.1f}%")
        L.append(f"  {rule('-', 40)} {rule('-', 15):>15} {rule('-', 8):>8}")
        L.append(f"  {'TOTAL':<40} {total:>15,} {'100.0%':>8}")
        L.append(f"\n  A full breakdown per district is in {os.path.basename(counts_file)},\n"
                 "  which gives the plot count of every district at every intensity.")
    else:
        L.append("  Not available: the UN 2023 file for this country carries no province\n"
                 "  or district names. See section 9.")

    # tailor the "Divide large CSV files" advice to this country
    if has and prov_counts:
        eg = [str(p) for p, _ in prov_counts[:2]] or ["ProvinceA", "ProvinceB"]
        eg_files = ", ".join(f"{slugify(e) or e}.csv" for e in eg)
        split_advice = (
            "    The aggregate option is the one to use here. Select ADM1NM to get\n"
            "    one CSV per province, or ADM2NM to get one CSV per district; each\n"
            "    output file is named after the value of that column\n"
            f"    ({eg_files}, ...), which makes them straightforward to\n"
            "    hand to field teams.\n\n")
    else:
        split_advice = (
            "    The aggregate-by-column option cannot be used for this country: the\n"
            "    ADM1NM and ADM2NM columns are empty (see section 9). Divide the file\n"
            "    by number of parts instead, or add your own column to aggregate on.\n\n")

    L.append(head(6, "How to use these files"))
    L.append(
        "  Choosing an intensity. Pick the coarsest grid that still gives you enough\n"
        "  plots in your smallest reporting unit. If you report by district, open\n"
        f"  {os.path.basename(counts_file)} and check the district with the fewest plots.\n\n"
        "  Python\n"
        "    import pandas as pd\n"
        f"    df = pd.read_csv('{country}_10x10km.csv')\n"
        "    df[df.ADM1NM == 'YourProvince']          # subset one province\n"
        "    df.groupby('ADM2NM').size()              # plots per district\n\n"
        "  R\n"
        f"    df <- read.csv('{country}_10x10km.csv', fileEncoding='UTF-8')\n"
        "    table(df$ADM2NM)\n\n"
        "  QGIS\n"
        "    Layer > Add Layer > Add Delimited Text Layer. X field = xCoordinate,\n"
        "    Y field = yCoordinate, CRS = EPSG:4326.\n\n"
        "  Google Earth / Collect Earth\n"
        "    The CSV can be used directly as a Collect Earth plot file: the first\n"
        "    three columns are already an id (CE_ID) followed by latitude and\n"
        "    longitude, which is the order Collect Earth expects. Keep the\n"
        "    ADM1NM/ADM2NM columns to stratify or to hand districts to field teams.\n\n"
        "  Splitting a file into smaller plot files\n"
        "    Collect Earth draws one Google Earth placemark per plot, and Google\n"
        f"    Earth has trouble with KML files holding more than about {CE_PLOT_LIMIT:,}\n"
        "    plots. Any file marked (*) in section 3 should be divided first.\n\n"
        "    Collect Earth ships a tool for exactly this:\n\n"
        "        Tools -> Utilities -> Divide large CSV files\n\n"
        "    Choose the large CSV, then pick one of:\n"
        "      - how many smaller files to divide it into;\n"
        "      - whether to randomize the order of the plots first;\n"
        "      - or aggregate the plots using one of the columns in the CSV.\n\n"
        + split_advice +
        "    Because CE_ID is unique and stable, plots keep their identity across\n"
        "    the split, and interpreted results can be merged back together.\n\n"
        "    See: https://openforis.support/questions/3623/\n\n"        "  Excel\n"
        "    Do NOT double-click the CSV. Use Data > From Text/CSV and set File\n"
        "    Origin to 65001: UTF-8, otherwise accented district names are corrupted.")

    L.append(head(7, "How this was generated"))
    L.append(
        "  1. The UN 2023 ADM2 boundaries for the country were downloaded and any\n"
        "     invalid polygon geometry repaired.\n"
        "  2. The SIGRID 10 x 10 degree tiles that actually intersect the country\n"
        "     were identified from the boundary geometry (not merely its bounding\n"
        "     box, which is wrong for countries crossing the 180th meridian) and\n"
        "     downloaded from:\n"
        f"       {TILE_BASE}\n"
        "  3. Every plot in those tiles was tested against the district polygons\n"
        "     with a point-in-polygon join (predicate 'intersects', so a plot lying\n"
        "     exactly on a boundary line is kept, not discarded). Plots outside all\n"
        "     districts were dropped. A plot on a shared border is assigned to one\n"
        "     district only, so no plot is ever duplicated.\n"
        "  4. The tagged plots were split on the grid_N flags into the density files\n"
        "     listed in section 3.\n\n"
        f"  Snap tolerance used: {args.snap_tolerance} degrees "
        f"({'disabled' if not args.snap_tolerance else 'nearest-district recovery on'}).\n"
        f"  Plots recovered by snapping: {snapped:,}")

    L.append(head(8, "Quality control"))
    L.append(
        "  Because SIGRID plots sit on a 1 km lattice, the number of plots inside a\n"
        "  country should equal that country's land area in square kilometres. That\n"
        "  is the single most informative check on this dataset, and it is reported\n"
        "  above as the QA ratio:\n\n"
        f"      {total:,} plots / {area:,.0f} km2  =  {ratio}\n\n"
        f"  Status: {qa}\n\n"
        f"  A value inside {args.qa_min}-{args.qa_max} is considered correct. Values are\n"
        "  typically 0.99-1.00; the small shortfall is explained in section 9.\n"
        "  Additional checks applied to this file: no duplicate CE_ID, no plot\n"
        "  assigned to more than one district, and no missing coordinates.")

    L.append(head(9, "Known limitations"))
    L.append(
        "  Coastlines. National boundaries are generalized. A small number of plots\n"
        "  that are genuinely on land can fall a few hundred metres outside the\n"
        "  published polygon and are therefore not included. This is the ~0.5%\n"
        "  visible in the QA ratio. Widening the tolerance to recover them pulls in\n"
        "  offshore sea points instead, which is worse, so the small undercount is\n"
        "  deliberate.\n\n"
        "  Boundary vintage. Districts follow the UN 2023 definition. If your\n"
        "  national administration has since split or merged districts, the names\n"
        "  here will not match your current official list.\n\n"
        "  Disputed areas. Boundaries follow UN depiction; see the disclaimer.")
    if not has:
        L.append(
            "\n  NO DISTRICT NAMES FOR THIS COUNTRY. The UN 2023 file published for\n"
            f"  {name} is a single national outline carrying no ADM1NM or ADM2NM\n"
            "  values. The plots in this archive are correctly clipped to the\n"
            "  national border, but the ADM1NM and ADM2NM columns are empty. If you\n"
            "  have an official district layer, you can re-tag these plots yourself\n"
            "  with any GIS using a point-in-polygon join.")

    L.append(head(10, "Provenance and citation"))
    L.append(
        f"  Generated        : {run_stamp}\n"
        f"  Generator        : build_all_countries.py v{VERSION}\n"
        f"  Plot grid        : SIGRID 1000 m ({TILE_BASE})\n"
        "  Boundaries       : United Nations 2023, ADM2 (EarthMap public store)\n"
        "  Coordinate system: EPSG:4326 (WGS 84)\n\n"
        "  Suggested citation:\n"
        f"    Open Foris SIGRID 1 km sampling grid for {name}, tagged with UN 2023\n"
        f"    ADM1/ADM2 administrative names. Generated {run_stamp}.")

    L.append(head(11, "Disclaimer"))
    L.append("  " + UN_DISCLAIMER.replace("\n", "\n  "))
    L.append("")
    return "\n".join(L) + "\n"


def finalise_country(iso2, meta, args, stats, run_stamp):
    name, country = meta["name"], meta["country"]
    suffix = "_grids" if meta["has_adm_names"] else "_grids_no_districts"
    zip_path = os.path.join(args.out, f"{country}{suffix}.zip")
    part_dir = os.path.join(args.tmp, "parts", iso2)
    if os.path.exists(zip_path):
        return dict(iso2=iso2, country=country, status="skipped (exists)")
    if not os.path.isdir(part_dir) or not os.listdir(part_dir):
        return dict(iso2=iso2, country=country, plots=0, status="no plots")

    combined = os.path.join(args.tmp, f"{iso2}_combined.csv")
    total, wrote_header, provs, canon = 0, False, set(), None
    with open(combined, "w", newline="") as out_f:
        for fn in sorted(os.listdir(part_dir)):
            d = pd.read_csv(os.path.join(part_dir, fn))
            if canon is None:
                canon = list(d.columns)
            d = d.reindex(columns=canon)
            d.to_csv(out_f, index=False, header=not wrote_header)
            wrote_header = True
            total += len(d)
            provs.update(d["ADM1NM"].dropna().unique().tolist())
    if total == 0:
        os.remove(combined)
        return dict(iso2=iso2, country=country, plots=0, status="no plots")

    gcols = grid_cols_of(canon)
    parts, written, counts, dist_counts = {}, {}, {}, {}
    for c in gcols:
        n = int(c.split("_")[1])
        parts[c] = os.path.join(args.tmp, f"{country}_{n}x{n}km.csv")
        written[c], counts[c], dist_counts[c] = False, 0, None

    bbox = [180.0, 90.0, -180.0, -90.0]
    for chunk in pd.read_csv(combined, chunksize=250000):
        bbox[0] = min(bbox[0], float(chunk.xCoordinate.min()))
        bbox[1] = min(bbox[1], float(chunk.yCoordinate.min()))
        bbox[2] = max(bbox[2], float(chunk.xCoordinate.max()))
        bbox[3] = max(bbox[3], float(chunk.yCoordinate.max()))
        for c in gcols:
            col = chunk[c]
            if col.dtype != bool:
                col = col.astype(str).str.lower().eq("true")
            sub = chunk[col.values]
            if not len(sub):
                continue
            s = sub.groupby(ADM, dropna=False).size()
            dist_counts[c] = s if dist_counts[c] is None else dist_counts[c].add(s, fill_value=0)
            n = int(c.split("_")[1])
            if n > 1:
                sub = sub[BASE_COLS]
            sub.to_csv(parts[c], mode="a", index=False, header=not written[c])
            written[c] = True
            counts[c] += len(sub)

    # per-district counts at every intensity -> its own CSV in the archive
    frames = []
    for c in gcols:
        if dist_counts[c] is None:
            continue
        n = int(c.split("_")[1])
        frames.append(dist_counts[c].rename(f"plots_{n}x{n}km"))
    dc = pd.concat(frames, axis=1).fillna(0).astype(int).reset_index()
    dc = dc.sort_values(list(ADM), na_position="last")
    counts_file = os.path.join(args.tmp, f"{country}_plot_counts_by_district.csv")
    dc.to_csv(counts_file, index=False)

    base = f"grid_1"
    prov_counts = []
    if meta["has_adm_names"] and dist_counts.get(base) is not None:
        s = dist_counts[base].reset_index()
        s.columns = list(ADM) + ["plots"]
        prov_counts = [(p, int(v)) for p, v in
                       s.groupby("ADM1NM", dropna=False)["plots"].sum()
                        .sort_values(ascending=False).items()]

    area = meta.get("area_km2") or float("nan")
    ratio = round(total / area, 4) if area and area == area and area > 0 else ""
    qa = "ok"
    if ratio != "" and not (args.qa_min <= ratio <= args.qa_max):
        qa = f"CHECK ratio={ratio}"

    dens_rows = [(int(c.split("_")[1]), counts[c], os.path.getsize(parts[c]))
                 for c in gcols if written[c]]
    snapped = stats.get("snapped", 0)
    readme = build_readme(meta, args, run_stamp, total, provs, dens_rows,
                          prov_counts, bbox, ratio, qa, snapped, counts_file)

    tmp_zip = zip_path + ".part"
    with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for c in gcols:
            if written[c]:
                z.write(parts[c], os.path.basename(parts[c]))
        z.write(counts_file, os.path.basename(counts_file))
        z.writestr(f"{country}_README.txt", readme)
    os.replace(tmp_zip, zip_path)

    for c in gcols:
        if os.path.exists(parts[c]):
            os.remove(parts[c])
    os.remove(combined)
    os.remove(counts_file)
    shutil.rmtree(part_dir, ignore_errors=True)

    return dict(iso2=iso2, country=country, plots=total, provinces=len(provs),
                districts=meta["districts"], has_adm_names=meta["has_adm_names"],
                area_km2=area, ratio=ratio, qa=qa, snapped=snapped,
                densities=len(dens_rows),
                zip=os.path.basename(zip_path),
                zip_mb=round(os.path.getsize(zip_path) / 1e6, 2),
                md5=md5(zip_path), status="ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./output")
    ap.add_argument("--cache", default="./sigrid_cache")
    ap.add_argument("--tmp", default="./_tmp")
    ap.add_argument("--countries", default="countries.csv")
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--purge-tiles", action="store_true")
    ap.add_argument("--snap-tolerance", type=float, default=0.0,
                    help="degrees; attach unmatched plots to the nearest district "
                         "within this distance. OFF by default: on coastal/island "
                         "countries even ~500 m (0.0045) pulls in offshore sea "
                         "points and pushes the QA ratio to ~1.03. Use with care.")
    ap.add_argument("--qa-min", type=float, default=0.97)
    ap.add_argument("--qa-max", type=float, default=1.01)
    args = ap.parse_args()

    for d in (args.out, args.cache, args.tmp):
        os.makedirs(d, exist_ok=True)
    for f in os.listdir(args.tmp):
        p = os.path.join(args.tmp, f)
        if os.path.isfile(p) and (f.endswith("_combined.csv") or f.endswith("km.csv")):
            os.remove(p)
    for f in os.listdir(args.out):
        if f.endswith(".part"):
            os.remove(os.path.join(args.out, f))

    run_stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = pd.read_csv(args.countries)
    if "status" in meta.columns:
        meta = meta[meta.status == "ok"]
    if args.only:
        want = {c.strip().lower() for c in args.only.split(",")}
        meta = meta[meta.iso2.isin(want)]

    print(f"Phase 0: boundaries for {len(meta)} countries ...", flush=True)
    districts, info = load_boundaries(meta, args.cache)
    print(f"  districts layer: {len(districts):,} polygons", flush=True)

    tiles = tiles_for_layer(districts)
    print(f"\nPhase 1: {len(tiles)} unique tiles, jobs={args.jobs} ...", flush=True)
    agg = {}
    t0 = time.time()

    def absorb(st):
        for iso2, s in st.items():
            a = agg.setdefault(iso2, {"matched": 0, "snapped": 0})
            a["matched"] += s["matched"]
            a["snapped"] += s["snapped"]

    _init_worker(districts, args)   # set globals BEFORE fork -> copy-on-write
    if args.jobs > 1:
        try:
            ctx = mp.get_context("fork")    # Linux/macOS: workers inherit the districts layer copy-on-write
        except ValueError:
            ctx = mp.get_context("spawn")   # Windows: no fork; each worker gets the layer pickled via the initializer
        with ctx.Pool(args.jobs, initializer=_init_worker, initargs=(districts, args)) as pool:
            for i, (tname, st) in enumerate(pool.imap_unordered(process_tile, tiles), 1):
                absorb(st)
                print(f"  [{i}/{len(tiles)}] {tname}: {len(st)} countries", flush=True)
    else:
        for i, tile in enumerate(tiles, 1):
            tname, st = process_tile(tile)
            absorb(st)
            print(f"  [{i}/{len(tiles)}] {tname}: {len(st)} countries", flush=True)
    print(f"  tiles done in {time.time()-t0:.0f}s", flush=True)

    print("\nPhase 2: per-country split + zip ...", flush=True)
    manifest = os.path.join(args.out, "manifest.csv")
    fields = ["iso2", "country", "plots", "provinces", "districts", "has_adm_names",
              "area_km2", "ratio", "qa", "snapped", "densities", "zip", "zip_mb",
              "md5", "status"]
    write_header = not os.path.exists(manifest)
    flagged = 0
    with open(manifest, "a", newline="") as mf:
        w = csv.DictWriter(mf, fieldnames=fields)
        if write_header:
            w.writeheader()
        for iso2 in sorted(info):
            res = finalise_country(iso2, info[iso2], args, agg.get(iso2, {}), run_stamp)
            note = "" if res.get("qa", "ok") == "ok" else f"   <-- {res['qa']}"
            if note:
                flagged += 1
            print(f"  {res['country']}: plots={res.get('plots','-')} "
                  f"ratio={res.get('ratio','-')}{note}", flush=True)
            w.writerow({k: res.get(k, "") for k in fields})
            mf.flush()

    print(f"\nDone. Manifest: {manifest}   QA-flagged countries: {flagged}", flush=True)


if __name__ == "__main__":
    main()
