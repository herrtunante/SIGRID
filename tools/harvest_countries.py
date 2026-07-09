#!/usr/bin/env python3
"""
Build countries.csv + country_tiles.json, the inputs for build_all_countries.py
and make_kmz_html.py.

For every 2-letter ISO country code it checks whether the UN-2023 ADM2 boundary
file exists, and if so records: name, ISO3, number of provinces/districts, a map
pin, and which SIGRID 10x10-degree tiles the country actually needs.

    python harvest_countries.py                 # all countries (~2 min)
    python harvest_countries.py --codes bj,ye   # just these (for testing)
    python harvest_countries.py --jobs 8

Outputs (both are committed to the repo so nobody has to re-run this):
    countries.csv        one row per country with an ADM2 file (198 of them)
    country_tiles.json   iso2 -> list of [x0, x1, y0, y1] tiles

Requires: pandas, geopandas.  pycountry is used for the ISO2 list if present;
otherwise the codes are read from an existing countries.csv.
"""
import argparse, csv, json, math, os, sys, tempfile, urllib.request, warnings
import geopandas as gpd
from shapely.geometry import box
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings("ignore")

GEOJSON_URL = ("https://firebasestorage.googleapis.com/v0/b/"
               "production-earthmap.appspot.com/o/"
               "boundaries%2FUN2023%2F{iso2}_adm2.geojson?alt=media")


def all_iso2():
    try:
        import pycountry
        return sorted(c.alpha_2.lower() for c in pycountry.countries)
    except ImportError:
        if os.path.exists("countries.csv"):
            import pandas as pd
            print("pycountry not installed; reusing codes from countries.csv")
            return sorted(pd.read_csv("countries.csv").iso2.astype(str))
        sys.exit("Install pycountry, or provide --codes, or keep countries.csv")


def fix_valid(g):
    bad = ~g.geometry.is_valid
    if bad.any():                       # 14 countries have self-intersections
        g.loc[bad, "geometry"] = g.loc[bad, "geometry"].buffer(0)
    return g[~g.geometry.is_empty & g.geometry.notna()]


def bbox_tiles(minx, miny, maxx, maxy):
    eps = 1e-9
    xs = range(int(math.floor(minx / 10) * 10),
               int(math.floor((maxx - eps) / 10) * 10) + 10, 10)
    ys = range(int(math.floor(miny / 10) * 10),
               int(math.floor((maxy - eps) / 10) * 10) + 10, 10)
    return {(x, x + 10, y, y + 10) for x in xs for y in ys}


def tiles_for_geom(g):
    """Per-part bounding boxes (so antimeridian countries do not drag in the
    whole longitude range), then keep only tiles a district really touches."""
    cand = set()
    for geom in g.geometry.explode(index_parts=False):
        cand |= bbox_tiles(*geom.bounds)
    sidx = g.sindex
    keep = set()
    for (x0, x1, y0, y1) in cand:
        if y0 < -80 or y1 > 80:         # SIGRID latitude range
            continue
        if len(sidx.query(box(x0, y0, x1, y1), predicate="intersects")):
            keep.add((x0, x1, y0, y1))
    return sorted(keep)


def one(iso2):
    tmp = os.path.join(tempfile.gettempdir(), f"_h{iso2}.geojson")
    try:
        req = urllib.request.Request(GEOJSON_URL.format(iso2=iso2),
                                     headers={"User-Agent": "sigrid-harvest"})
        with urllib.request.urlopen(req, timeout=240) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        g = fix_valid(gpd.read_file(tmp))
        name = None
        for c in ("ROMNAM", "MAPLAB"):
            if c in g.columns and g[c].notna().any():
                name = str(g[c].dropna().iloc[0])
                break
        iso3 = (str(g["ISO3CD"].dropna().iloc[0])
                if "ISO3CD" in g.columns and g["ISO3CD"].notna().any() else "")
        ts = tiles_for_geom(g)
        parts = list(g.geometry.explode(index_parts=False))
        pt = max(parts, key=lambda p: p.area).representative_point()
        n_adm1 = int(g["ADM1NM"].nunique()) if "ADM1NM" in g.columns else 0
        return dict(iso2=iso2, iso3=iso3, name=name or iso2.upper(),
                    n_adm1=n_adm1, n_adm2=len(g),
                    clon=round(pt.x, 5), clat=round(pt.y, 5),
                    n_tiles=len(ts), status="ok"), ts
    except Exception as e:
        # a missing file (most non-countries) lands here; it is not an error
        return dict(iso2=iso2, iso3="", name=iso2.upper(), n_adm1=0, n_adm2=0,
                    clon="", clat="", n_tiles=0,
                    status=f"error: {type(e).__name__}"), []
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="", help="comma-separated ISO2 subset")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--out", default="countries.csv")
    ap.add_argument("--tiles-out", default="country_tiles.json")
    a = ap.parse_args()

    codes = ([c.strip().lower() for c in a.codes.split(",") if c.strip()]
             if a.codes else all_iso2())
    rows, tilemap = [], {}
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for i, (r, ts) in enumerate(ex.map(one, codes), 1):
            if r["status"] != "ok":
                print(f"{i}/{len(codes)} {r['iso2']}: no ADM2 file, skipped", flush=True)
                continue
            rows.append(r)
            tilemap[r["iso2"]] = [list(t) for t in ts]
            kind = "districts" if r["n_adm1"] else "OUTLINE ONLY"
            print(f"{i}/{len(codes)} {r['iso2']} {r['name']}: "
                  f"{r['n_adm2']} polys, {r['n_tiles']} tiles, {kind}", flush=True)

    if not rows:
        sys.exit("nothing harvested")
    rows.sort(key=lambda r: r["name"])
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    json.dump(tilemap, open(a.tiles_out, "w"))

    U = set()
    for v in tilemap.values():
        U |= {tuple(t) for t in v}
    outline = sum(1 for r in rows if not r["n_adm1"])
    print(f"\n{len(rows)} countries -> {a.out}")
    print(f"  with district names : {len(rows) - outline}")
    print(f"  outline only        : {outline}")
    print(f"  unique SIGRID tiles : {len(U)}")


if __name__ == "__main__":
    main()
