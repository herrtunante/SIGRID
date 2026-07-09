# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SIGRID (Systematic Iterative GRID) generates a global systematic sampling grid of points at 1×1 km spacing with nested sub-grids at wider spacings (2, 3, 4 … 100 km), built for FAO's Open Foris Collect Earth. Unlike naive lat/lon grids, plot-to-plot distance stays ~1000 m at any latitude: plots are laid row by row from 85°N down to 85°S, and the degrees-per-1000 m offset is recomputed for each row. The grid is published as 10°×10° tile CSV ZIPs at https://www.openforis.org/fileadmin/SIGRID_1000m_grids/.

## Repo layout: two independent parts

1. **Java/Maven grid generator** (committed) — `src/main/java/org/openforis/sigrid/`. Generates the grid and exports it as tiled CSVs and a browse KML.
2. **Python post-processing pipeline** (untracked) — `tools/`. Downloads the *published* tile ZIPs, spatially joins them with UN-2023 ADM2 boundaries, and produces per-country grid ZIPs plus an HTML/KMZ catalogue. It never runs the Java code.

**Before touching anything in `tools/`, read `tools/CLAUDE.md`.** It documents hard-won gotchas: the published CSVs are malformed (two extra trailing commas per row — naive `pd.read_csv` silently shifts columns; the `CSVStore` bug causing this is fixed, but already-published tiles still carry it), antimeridian countries break bbox tiling, 14 countries have invalid geometries requiring `buffer(0)`, and QA plot/area ratios must fall in 0.97–1.01.

## Commands

```
mvn clean package        # build the Java project (needs the OSGeo repo, declared in pom.xml)
```

There is **no test suite** (no `src/test`, no JUnit) and no CI.

There is **no CLI**. The Java entry points are `main()` methods configured by editing constants in the source, and must run with the **repo root as working directory** (they read `resources/*.sql` by relative path and write to `output/`):

- `GenerateSigrid.main()` — generates the grid (whole globe, or uncomment the `generate(east, north, west, south)` bounding-box call). Output backend is the `STORE` constant: `CSVStore` by default, switch to `JDBCStore` for SQLite/PostgreSQL.
- `QuerySigrid.main()` — reads an already-populated DB and exports 10° CSV tiles or the browse KML. Contains many commented example bounding boxes to uncomment for regional exports.

Python pipeline (from `tools/`; details in `tools/CLAUDE.md`):

```
pip install pandas geopandas pyproj
python sigrid_country.py bj --split-by-density                                # one country
python build_all_countries.py --out ./output --cache ./sigrid_cache --jobs 2  # all countries, resumable
```

## Architecture (Java)

**Generation flow:** `GenerateSigrid.generate()` walks the globe row by row (85°N → 85°S), column by column eastward from 169°W. Each step calls `CoordinateUtils.getPointWithOffset()` — the geodesic heart of the project, using GeoTools' `GeodeticCalculator` on WGS84 to move exactly N meters — then hands the point to `STORE.savePlot(lat, lon, row, col)`.

**Store abstraction:** `AbstractStore` defines `initializeStore / savePlot / closeStore`, the canonical density list `{1,2,3,4,5,6,8,9,10,12,15,16,20,25,30,50,100}`, and `SCALING_FACTOR = 10_000_000`. Implementations:

- `CSVStore` — one CSV per density in `output/`, optionally zipped; rotates to a new ZIP entry every 500k rows, flushes every 250k.
- `JDBCStore` — inserts into a `plot` table (SQLite by default via `USE_SQLITE`; PostgreSQL creds are placeholders). Coordinates are stored as integers scaled by `SCALING_FACTOR`; sub-grid membership is packed into one `gridflags` bitmask integer where the bit position is the density's **index** in the distances array (0–16), not the density value itself — shifting by the value would overflow for the 50 and 100 km sub-grids. Queried with `gridflags & ? = ?`. DDL lives in `resources/createTable.sql` / `createTableSqlite.sql`; a DB populated by the pre-2026 code (bit = density value) can be converted in place with `resources/migrateGridflags.sql`.

**Export flow:** `QuerySigrid` queries the JDBC store to write 10°-step CSV tiles (`generateTiledGrids`) or renders the tile-browser KML into `output/` from the FreeMarker template `resources/kml_template.fmt`, where each `Tile`'s `linkUrl` points at the hosted ZIPs.

## Grid conventions

- **CE_ID = `row_col`** (e.g. `2000_3300`): km south of the 85°N start row, km west of the 169°W start. Stable across all densities and tiles — the universal join key.
- A plot belongs to the d-km sub-grid when `column % d + row % d == 0` (i.e. both divisible by d). In the published CSVs this appears as one boolean column per density, tile-suffixed (`grid_2_SIGRID_x_20_30_y_50_60`); combine columns to derive other spacings (18 km = member of both 9 and 6).
- Everything is WGS84 / EPSG:4326; **`yCoordinate` = latitude, `xCoordinate` = longitude**. Bounding boxes throughout the Java code are ordered (east, north, west, south).
