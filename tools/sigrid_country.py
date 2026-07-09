#!/usr/bin/env python3
"""
SIGRID -> country plots with district names (fully automated).

Given a 2-letter ISO country code, this script:
  1. Downloads that country's UN-2023 ADM2 boundaries (GeoJSON).
  2. Works out which SIGRID 1000 m 10x10-degree tiles overlap the country.
  3. Downloads those tile ZIPs from openforis.org (cached; skipped if present).
  4. Reads each subgrid CSV, keeps plots inside the country, and tags every
     plot with its province (ADM1NM) and district (ADM2NM) via a
     point-in-polygon spatial join.
  5. Writes ONE combined CSV: <iso2>_plots_with_districts.csv

Optional: --split-by-density
  Also writes one CSV per SIGRID density grid, containing only the plots
  flagged for that grid. Files go into <Country>_by_density/ and are named
  <Country>_1x1km.csv, <Country>_2x2km.csv, <Country>_3x3km.csv, ...
  (grid_N -> NxN km). All columns are kept.

Usage:
    python sigrid_country.py bj                          # Benin, combined only
    python sigrid_country.py bj --split-by-density       # + per-density files
    python sigrid_country.py ke --out ./results          # custom output dir

Requires: pandas, geopandas  (pip install pandas geopandas)
Everything is cached under ./sigrid_cache so re-runs are fast.
"""
import argparse, math, os, re, sys, zipfile, io, time, unicodedata
import urllib.request
import pandas as pd
import geopandas as gpd

GEOJSON_URL = ("https://firebasestorage.googleapis.com/v0/b/"
               "production-earthmap.appspot.com/o/"
               "boundaries%2FUN2023%2F{iso2}_adm2.geojson?alt=media")
TILE_BASE = "https://www.openforis.org/fileadmin/SIGRID_1000m_grids"
TILE_NAME = "SIGRID_x_{x0}_{x1}_y_{y0}_{y1}_1000m_1_subgrid.csv.zip"
ADM = ["ADM1NM", "ADM2NM"]


def slugify(s, fallback):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s or fallback


def download(url, dest, tries=3):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"  cached: {os.path.basename(dest)}", flush=True)
        return dest
    for k in range(1, tries + 1):
        try:
            print(f"  downloading {os.path.basename(dest)} (try {k}) ...", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "sigrid-auto"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            return dest
        except Exception as e:
            print(f"    failed: {e}", flush=True)
            if os.path.exists(dest):
                os.remove(dest)
            time.sleep(3 * k)
    raise RuntimeError(f"could not download {url}")


def tiles_for_bounds(minx, miny, maxx, maxy):
    eps = 1e-9
    xs = range(int(math.floor(minx / 10) * 10),
               int(math.floor((maxx - eps) / 10) * 10) + 10, 10)
    ys = range(int(math.floor(miny / 10) * 10),
               int(math.floor((maxy - eps) / 10) * 10) + 10, 10)
    return [(x, x + 10, y, y + 10) for x in xs for y in ys]


def read_sigrid_bytes(raw, header):
    """Parse a SIGRID subgrid CSV (two junk trailing fields) from bytes."""
    df = pd.read_csv(io.BytesIO(raw), skiprows=1,
                     names=header + ["_a", "_b"], index_col=False)
    return df[header]


def split_by_density(combined_csv, out_dir, country):
    """Write one CSV per grid_N density: rows where that grid flag is True."""
    header = pd.read_csv(combined_csv, nrows=0).columns.tolist()
    grid_cols = [c for c in header if re.match(r"^grid_\d+$", c)]
    grid_cols.sort(key=lambda c: int(c.split("_")[1]))
    dens_dir = os.path.join(out_dir, f"{country}_by_density")
    os.makedirs(dens_dir, exist_ok=True)
    paths, written, counts = {}, {}, {}
    for c in grid_cols:
        n = int(c.split("_")[1])
        paths[c] = os.path.join(dens_dir, f"{country}_{n}x{n}km.csv")
        written[c] = False
        counts[c] = 0
    for chunk in pd.read_csv(combined_csv, chunksize=250000):
        for c in grid_cols:
            col = chunk[c]
            if col.dtype != bool:                 # be robust to text True/False
                col = col.astype(str).str.lower().eq("true")
            sub = chunk[col.values]
            if len(sub):
                sub.to_csv(paths[c], mode="a", index=False, header=not written[c])
                written[c] = True
                counts[c] += len(sub)
    return dens_dir, grid_cols, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("iso2", help="2-letter ISO country code, e.g. bj")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--cache", default="sigrid_cache", help="download cache dir")
    ap.add_argument("--split-by-density", action="store_true",
                    help="also write one CSV per density grid (NxN km)")
    args = ap.parse_args()
    iso2 = args.iso2.lower()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.cache, exist_ok=True)

    # 1. boundaries
    print(f"[{iso2}] fetching ADM2 boundaries ...", flush=True)
    gj = os.path.join(args.cache, f"{iso2}_adm2.geojson")
    download(GEOJSON_URL.format(iso2=iso2), gj)
    d = fix_valid(gpd.read_file(gj))
    if not set(ADM).issubset(d.columns):
        sys.exit(f"GeoJSON for '{iso2}' lacks {ADM}; found {list(d.columns)}")
    # country name for filenames (ROMNAM/MAPLAB fall back to ISO2)
    country = iso2
    for col in ("ROMNAM", "MAPLAB"):
        if col in d.columns and d[col].notna().any():
            country = slugify(d[col].dropna().iloc[0], iso2)
            break
    d = d[ADM + ["geometry"]]
    d = d.set_crs("EPSG:4326") if d.crs is None else d.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = d.total_bounds
    print(f"  {len(d)} districts | country '{country}' | "
          f"bbox lon {minx:.2f}..{maxx:.2f} lat {miny:.2f}..{maxy:.2f}", flush=True)

    # 2 + 3. tiles
    tiles = tiles_for_bounds(minx, miny, maxx, maxy)
    print(f"[{iso2}] {len(tiles)} SIGRID tile(s) overlap this country", flush=True)
    zips = []
    for x0, x1, y0, y1 in tiles:
        name = TILE_NAME.format(x0=x0, x1=x1, y0=y0, y1=y1)
        try:
            zips.append(download(f"{TILE_BASE}/{name}",
                                 os.path.join(args.cache, name)))
        except RuntimeError:
            print(f"  tile not available (skipped): {name}", flush=True)

    # 4 + 5. join, streamed to one CSV
    out_path = os.path.join(args.out, f"{iso2}_plots_with_districts.csv")
    total = 0
    wrote_header = False
    prov_counts = {}
    with open(out_path, "w", newline="") as out_f:
        for zpath in zips:
            with zipfile.ZipFile(zpath) as zf:
                for member in sorted(zf.namelist()):
                    if not member.endswith(".csv"):
                        continue
                    raw = zf.read(member)
                    header = raw[:raw.index(b"\n")].decode().replace('"', "").split(",")
                    df = read_sigrid_bytes(raw, header)
                    del raw
                    # strip tile-specific suffix so merged tiles share
                    # identical column names (grid_1 .. grid_100).
                    df.columns = [re.sub(r'^(grid_\d+)_SIGRID.*$', r'\1', c)
                                  for c in df.columns]
                    x, y = df.xCoordinate, df.yCoordinate
                    df = df[(x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)]
                    if df.empty:
                        print(f"    {member}: 0 in bbox", flush=True)
                        continue
                    pts = gpd.GeoDataFrame(
                        df, geometry=gpd.points_from_xy(df.xCoordinate, df.yCoordinate),
                        crs="EPSG:4326")
                    j = gpd.sjoin(pts, d, how="inner", predicate="intersects")
                    j = j[~j.index.duplicated(keep="first")].drop(
                        columns=["geometry", "index_right"])
                    if len(j):
                        cols = list(df.columns)
                        ins = cols.index("xCoordinate") + 1
                        ordered = cols[:ins] + ADM + cols[ins:]
                        j[ordered].to_csv(out_f, index=False, header=not wrote_header)
                        wrote_header = True
                        total += len(j)
                        for a, c in j["ADM1NM"].value_counts().items():
                            prov_counts[a] = prov_counts.get(a, 0) + int(c)
                    print(f"    {member}: {len(j)} in-country", flush=True)
                    del df, pts, j

    print(f"\n[{iso2}] DONE -> {out_path}", flush=True)
    print(f"  total plots: {total}", flush=True)
    print("  provinces (ADM1NM):", flush=True)
    for a, c in sorted(prov_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {a}: {c}", flush=True)
    if total == 0:
        print("  (no plots matched - check the ISO2 code / data availability)")
        return

    # 6. optional per-density split
    if args.split_by_density:
        print(f"\n[{iso2}] splitting by density grid ...", flush=True)
        dens_dir, grid_cols, counts = split_by_density(out_path, args.out, country)
        for c in grid_cols:
            n = int(c.split("_")[1])
            print(f"    {country}_{n}x{n}km.csv: {counts[c]} plots", flush=True)
        print(f"  density files -> {dens_dir}", flush=True)


if __name__ == "__main__":
    main()
