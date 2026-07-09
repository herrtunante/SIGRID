# CLAUDE.md — SIGRID per-country grids

Context for an AI assistant picking up this work. Read this before changing anything;
several of the decisions below look wrong until you know why they were made.

## What this repo does

Takes the global **SIGRID 1000 m sampling grid** (published as 10°×10° tiles) and, for
every country, produces a ZIP containing one CSV per sampling density (1×1 km, 2×2 km …
100×100 km), where every plot is tagged with the **province (`ADM1NM`)** and **district
(`ADM2NM`)** it falls in, taken from the UN 2023 ADM2 boundaries.

It also builds an `index.html` catalogue and a `SIGRID_country_grids.kmz` for Google Earth.

## Files

| File | Purpose |
|---|---|
| `sigrid_country.py` | Single country. `python sigrid_country.py bj --split-by-density` |
| `build_all_countries.py` | All 198 countries, tile-centric, resumable. The main script. |
| `make_kmz_html.py` | Builds `index.html` + `SIGRID_country_grids.kmz` from `countries.csv` + `manifest.csv` |
| `harvest_countries.py` | Regenerates `countries.csv` + `country_tiles.json` |
| `countries.csv` | **Committed.** 198 rows: iso2, iso3, name, n_adm1, n_adm2, clon, clat, n_tiles |
| `country_tiles.json` | **Committed.** iso2 → list of `[x0,x1,y0,y1]` tiles |

Everything else is generated and git-ignored (see `.gitignore`).

## Running it

```bash
pip install pandas geopandas pyproj
python build_all_countries.py --out ./output --cache ./sigrid_cache --jobs 2
python make_kmz_html.py --countries countries.csv --manifest output/manifest.csv \
    --boundaries sigrid_cache --out ./site
```

Resumable: finished ZIPs and finished tiles are both skipped, so interrupt freely.
Size `--jobs` to RAM (~1.5 GB per worker), not to cores.

Works on Windows too: the pool prefers `fork` (copy-on-write) and falls back to `spawn`
where fork doesn't exist, passing the districts layer to each worker via the pool
initializer. Under spawn each worker holds its own pickled copy of the layer, so the
per-worker RAM guidance above is the floor, and pool startup takes a few extra seconds.

## Data sources

- Tiles: `https://www.openforis.org/fileadmin/SIGRID_1000m_grids/SIGRID_x_{x0}_{x1}_y_{y0}_{y1}_1000m_1_subgrid.csv.zip`
  All 576 tiles (lon −180…180, lat −80…80, step 10) exist, ocean ones included. The
  server 404s on a bogus name, so a HEAD probe is meaningful.
  Each ZIP holds 3 subgrid CSVs (`_subgrid_0/1/2`), ~500k rows each.
- Boundaries: `https://firebasestorage.googleapis.com/v0/b/production-earthmap.appspot.com/o/boundaries%2FUN2023%2F{iso2}_adm2.geojson?alt=media`
  The `?alt=media` is required or you get metadata JSON instead of the file.
- Published ZIPs live at `…/SIGRID_1000m_grids/per_country/`; scripts, KMZ and
  `index.html` live one level up. `make_kmz_html.py` has `--base-url` and `--zip-url`
  for exactly this split.

## Hard-won facts — do not rediscover these

**The source CSVs are malformed.** Every data row has two extra trailing commas that the
header doesn't declare. Naive `pd.read_csv` silently shifts columns and turns
`xCoordinate` into a bool. Parse with explicit `names=header + ["_a","_b"]`,
`index_col=False`, then select `header`. See `read_sigrid_bytes()`.

**Grid columns are tile-suffixed.** `grid_1_SIGRID_x_40_50_y_10_20`. They're stripped to
`grid_1` so tiles can be concatenated. The densities present are
`1,2,3,4,5,6,8,9,10,12,15,16,20,25,30,50,100` — not consecutive.

**Bounding boxes break at the antimeridian.** A naive country bbox asks for **252 tiles for
the USA** and 180 for Russia, mostly empty ocean. Use per-polygon-part bboxes intersected
against the real geometry via the spatial index (`tiles_for_geom`). Correct answers: USA 35,
Russia 60. Globally 375 unique tiles (~3.8 GB), or 292 for countries that have districts.

**14 countries have invalid geometries** — India, Mexico, UK, Australia, Iran, Uganda,
Costa Rica, Guatemala, Ireland, Sri Lanka, Azerbaijan and others. `sjoin` and `union_all`
raise `GEOSException` on them. Always `fix_valid()` (buffer(0)) after reading a GeoJSON.

**Never call `union_all()` on a big country.** It hangs on the USA (3145 counties). Use
`sindex.query(box, predicate="intersects")` instead.

**32 of the 198 countries have no district names.** Their UN-2023 `_adm2.geojson` is a
single national outline with `ADM1NM`/`ADM2NM` = null: Chile, Malaysia, Viet Nam, Oman,
UAE, Greenland, Singapore, Antarctica, Kuwait, Croatia, Bosnia, Eritrea, Montenegro and
more. **The `_adm1.geojson` fallback does not help — it is also an outline.** I checked.
These ship as `<Country>_grids_no_districts.zip` with an explicit README note.

**The QA ratio is the single best check.** Plots sit on a 1 km lattice, so
`plots / land_area_km²` (area computed in Mollweide, `ESRI:54009`) must be ≈ 1.0. It lands
at **0.991–0.998** for every country tested. Anything outside 0.97–1.01 means something is
broken. This is in `manifest.csv` and every README.

**Border snapping over-recovers — it is off by default.** `--snap-tolerance` re-attaches
unmatched plots to the nearest district. At ~500 m (0.0045°) it fixes a ~0.6% inland loss
but drags in offshore sea points: **Belize 0.995 → 1.030, Cyprus 0.996 → 1.035**. The QA
ratio caught this. Default is `0.0`, and the join uses `predicate="intersects"` (not
`"within"`) so plots exactly on a boundary line are kept for free. The residual ~0.5%
undercount is generalized coastlines and is deliberate. **Don't "fix" it without checking
the ratio on an island country.**

**Chile is pathologically slow.** One enormous single polygon; a single tile join against it
takes >40 s. Not a bug, just budget for it.

**Coarse density files drop the `grid_*` flags.** They're strict subsets of the 1×1 km file
(verified: `CE_ID` sets are subsets at 2/5/10/100 km), so the flags are redundant and the
filename states the density. The 1×1 km file keeps them.

**Collect Earth caps out around 2,000 plots per file** (Google Earth KML limit). Files above
that are marked `(*)` in each README, which points to
`Tools → Utilities → Divide large CSV files`, whose aggregate-by-column option works
beautifully on `ADM1NM`/`ADM2NM`. Source:
<https://openforis.support/questions/3623/>

## Conventions

- Everything is EPSG:4326. Coordinates are `yCoordinate` = lat, `xCoordinate` = lon.
- `CE_ID` is the stable join key; it is identical across densities and across the global tiles.
- Country filenames come from `ROMNAM`, ASCII-slugified (`slugify()`). No collisions among
  the 198; longest is `Democratic_People_s_Republic_of_Korea`.
- Boundary-straddling plots are deduplicated with `~index.duplicated(keep="first")` so a plot
  is never counted twice.
- ZIPs are written to `.part` then `os.replace()`d. Tiles get a `_tiles_done/<tile>.ok` flag
  and, on re-run, delete their own old part files first — otherwise a crashed run
  double-counts rows on resume. Keep this invariant if you touch phase 1.

## How to verify a change

Regenerate a small mixed set and check the ratios and the subset property:

```bash
python build_all_countries.py --only bj,ye,bz,cy,sg --out ./out_test --tmp ./tmp_test --jobs 1
```

Expected, exactly (these have been stable across three independent implementations):

| Country | Plots | Ratio |
|---|---|---|
| Benin | 115,259 | 0.9936 |
| Yemen | 453,565 | 0.9942 |
| Belize | 22,145 | 0.9948 |
| Cyprus | 8,980 | 0.9959 |
| Singapore (outline only) | 594 | 0.9943 |

Then assert the coarse grids are subsets of the base grid and the counts CSV agrees:

```python
import zipfile, io, pandas as pd
z = zipfile.ZipFile('out_test/Benin_grids.zip')
base = pd.read_csv(io.BytesIO(z.read('Benin_1x1km.csv')))
for n in (2, 5, 10, 100):
    d = pd.read_csv(io.BytesIO(z.read(f'Benin_{n}x{n}km.csv')))
    assert set(d.CE_ID).issubset(set(base.CE_ID))
c = pd.read_csv(io.BytesIO(z.read('Benin_plot_counts_by_district.csv')))
assert c.plots_1x1km.sum() == len(base) == 115_259
assert base.CE_ID.duplicated().sum() == 0
```

## Open items

- Full 198-country run has not been executed end-to-end; only an 8-country pilot
  (Andorra, Belize, Benin, Cyprus, Dominica, Saint Lucia, Singapore, Yemen). Expect
  ~3 GB of tiles and several hours.
- After the full run, re-run `make_kmz_html.py --boundaries sigrid_cache` so all 198 pins
  are recomputed from the cached GeoJSONs (area-weighted centroid, circular-mean longitude,
  snapped to land). Without `--boundaries`, pins fall back to the largest polygon part,
  which puts the USA in Alaska.
- `index.html` hard-codes "14 countries have self-intersections" and the 252→35 USA figure
  in its prose. Update if the boundary vintage changes.
- Consider Parquet alongside CSV; the density files carry ~1.55× redundancy overall
  (sum of 1/N²).
