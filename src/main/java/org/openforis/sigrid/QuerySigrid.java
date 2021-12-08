package org.openforis.sigrid;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import freemarker.template.Configuration;
import freemarker.template.Template;
import freemarker.template.TemplateException;
import freemarker.template.Version;

public class QuerySigrid {

	JDBCStore database = new JDBCStore();
	CSVStore csv = new CSVStore();
	private static Logger logger = LoggerFactory.getLogger( QuerySigrid.class );
	private static final int OFFSET_DEGREES = 10;

	public ResultSet getSigridForShapefile(File shapefile, Integer gridDistance, Integer grid) {
		return null;
	}

	public ResultSet getSigridForBoundingBox(Double[] boundingBox, Integer gridDistance, Integer grid) {
		return database.getPlots(grid, boundingBox[0], boundingBox[1], boundingBox[2], boundingBox[3], gridDistance);
	}

	public ResultSet getSigridAll(Integer gridDistance, Integer grid) {
		return database.getAllPlots(grid, gridDistance);
	}

	// Bounding box array : Double maxX, Double maxY, Double minX, Double minY
	public void writeCsvFromBoundingBox(Double[] boundingBox, Integer gridDistance, Integer grid, String prefix,
			boolean zipOutput) {

		ResultSet results = getSigridForBoundingBox(boundingBox, gridDistance, grid);
		try {
			csv.initializeStore(gridDistance, prefix, zipOutput);

			while (results.next()) {
				csv.savePlot(results.getInt("ycoordinate") * 1d / AbstractStore.SCALING_FACTOR * 1d,
						results.getInt("xcoordinate") * 1d / AbstractStore.SCALING_FACTOR * 1d, results.getInt("row"),
						results.getInt("col"));
			}
			results.close();

		} catch (SQLException e) {
			logger.error("Error readig results from DB", e);
		} finally {
			csv.closeStore();
			database.closeStore();
		}

	}

	public void generateTiledOffsetDegreeGrids(int latitude, int longitude, Integer gridDistance, Integer grid,
			String prefix) {
		// Double maxX, Double maxY, Double minX, Double minY,
		Double[] boundingBox = { Double.valueOf(longitude + OFFSET_DEGREES), Double.valueOf(latitude + OFFSET_DEGREES),
				Double.valueOf(longitude), Double.valueOf(latitude), };
		writeCsvFromBoundingBox(boundingBox, gridDistance, grid, prefix, true);
	}

	public void generateTiledGrids(int minX, int maxX, int minY, int maxY, Integer gridDistance, Integer grid,
			String prefix) {
		for (int longitude = minX; longitude < maxX; longitude = longitude + OFFSET_DEGREES) {
			for (int latitude = minY; latitude < maxY; latitude = latitude + OFFSET_DEGREES) {
				generateTiledOffsetDegreeGrids(latitude, longitude, gridDistance, grid,
						prefix + "_x_" + longitude + "_" + ( longitude + OFFSET_DEGREES ) + "_y_"	+ latitude  + "_" + ( latitude + OFFSET_DEGREES)
				);
			}
		}
	}

	public static boolean applyTemplate(File sourceTemplate, File destinationFile, Map<?, ?> data) throws IOException, TemplateException{
		boolean success = false;

		// Console output
		try ( BufferedWriter fw = new BufferedWriter(new OutputStreamWriter(new FileOutputStream(destinationFile), StandardCharsets.UTF_8 )) ) {

			// Process the template file using the data in the "data" Map
			final Configuration cfg = new Configuration( new Version("2.3.23"));
			cfg.setDirectoryForTemplateLoading(sourceTemplate.getParentFile());

			// Load template from source folder
			final Template template = cfg.getTemplate(sourceTemplate.getName());

			template.process(data, fw);
			success = true;
		}catch (Exception e) {
			logger.error("Error reading FreeMarker template {}", e.getMessage());
		}
		return success;

	}

	public void generateKmlGrids(int minX, int maxX, int minY, int maxY, Integer gridDistance, Integer grid, String prefix) {

		final Map<String, Object> data = new HashMap<String, Object>();
		List<Tile> tiles = new ArrayList<Tile>();

		for (int longitude = minX; longitude < maxX; longitude = longitude + OFFSET_DEGREES) {
			for (int latitude = minY; latitude < maxY; latitude = latitude + OFFSET_DEGREES) {

				Tile tile = new Tile();
				tile.setId( "Lat:" + latitude + "_" + (latitude + OFFSET_DEGREES ) +  "_Long:" + longitude + "_" + (longitude + OFFSET_DEGREES )) ;
				tile.setCenterLat( (latitude + OFFSET_DEGREES) / 2 );
				tile.setCenterLong( (longitude + OFFSET_DEGREES) / 2 );
				tile.setEast( longitude + OFFSET_DEGREES  );
				tile.setWest(longitude);
				tile.setNorth(latitude);
				tile.setSouth( latitude + OFFSET_DEGREES );
				tile.setLinkUrl(
						"https://www.openforis.org/fileadmin/SIGRID_1000m_grids/" + prefix +
							"_x_" + longitude + "_" + ( longitude + OFFSET_DEGREES ) + "_y_"	+ latitude  + "_" + ( latitude + OFFSET_DEGREES) +
							"_" + gridDistance + "m_" + grid + "_subgrid.csv.zip"
						);

				tiles.add( tile );
			}
		}
		data.put("tiles", tiles);

		try {

			File templateFile = new File("resources/kml_template.fmt");
			File outputFile = new File("resources/SIGRID_Grid"+"_" + gridDistance + "m_" + grid + "_subgrid.kml" );

			applyTemplate( templateFile, outputFile, data);

			logger.warn("KML File with tiles at : {}", outputFile.getPath());

		} catch (Exception e) {
			logger.error("Error generating KML", e);
		}

	}


	public void generateTiledGridsAfrica() {

		// Double maxX, Double maxY, Double minX, Double minY,
		int minX = -30; // WEST
		int maxX = 60; // EAST
		int minY = -40; // SOUTH
		int maxY = 30; // NORTH

		generateTiledGrids(minX, maxX, minY, maxY, 1000, 1, "Africa_SIGRID");
	}

	public void generateTiledGridsAll() {

		// Double maxX, Double maxY, Double minX, Double minY,
		int minX = -180; // WEST
		int maxX = 180; // EAST
		int minY = -90; // SOUTH
		int maxY = 90; // NORTH

		//generateTiledGrids(minX, maxX, minY, maxY, 1000, 1, "SIGRID");
		generateKmlGrids(minX, maxX, minY, maxY, 1000, 1, "SIGRID");
	}

	public void writeCsvForAll(Integer gridDistance, Integer grid, String prefix, boolean zipOutput) {

		ResultSet results = getSigridAll(gridDistance, grid);
		try {
			csv.initializeStore(gridDistance, prefix, zipOutput);

			while (results.next()) {
				csv.savePlot(results.getInt("ycoordinate") * 1d / AbstractStore.SCALING_FACTOR * 1d,
						results.getInt("xcoordinate") * 1d / AbstractStore.SCALING_FACTOR * 1d, results.getInt("row"),
						results.getInt("col"));
			}

			results.close();

		} catch (SQLException e) {
			logger.error("Error readig results from DB", e);
		} finally {
			csv.closeStore();
			database.closeStore();
		}

	}

	public static void main(String[] args) {
		QuerySigrid querySigrid = new QuerySigrid();

		querySigrid.generateTiledGridsAll();
		// querySigrid.writeCsvForAll( 1000, 1, "Whole_SIGRID_", true);

		// Double East, Double North, Double West, Double South
		// querySigrid.writeCsvFromBoundingBox( new Double[] {25.5305d, -17.3103d,
		// 24.3222d, -18.1102}, 1000, 1, "Botswana_Mini");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {-56.04d, -21.75d, -70.86d,
		// -67.37d}, 1000, 10, "Argentina");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {88.21d, 30.48d, 80.05d,
		// 26.34d}, 1000, 1, "Nepal");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {38d,38d,-17d,14d}, 1000,
		// 10, "NorthAfrica");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {60d,38d,-17d,-35d}, 1000,
		// 10, "AllAfricaAfrica");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {11.7d, 37.5d, 7.2d, 30d},
		// 1000, 1, "Tunisia_1000");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {6.034, 14.862, 1.687,
		// 12.725}, 1000, 1, "FFEM_1000");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {34.434541, -7.869966,
		// 21.344595, -18.697429}, 1000, 1, "Zambia");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {30.88, -2.3, 28.98, -4.5},
		// 1000, 1, "Burundi");

		// querySigrid.writeCsvFromBoundingBox(new Double[] { 29.8, -28.5, 26.7, -30.8
		// }, 1000, 1, "Lesotho", true);

		// querySigrid.writeCsvFromBoundingBox( new Double[] {47.1, 43.7, 39.8, 40.8},
		// 1000, 1, "Georgia");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {43.6, 12.8, 41.49, 10.77},
		// 1000, 1, "Djibouti");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {4.2, 13.25, -3.88, 4.29},
		// 1000, 5, "Ghanna_5x5");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {-11.0, 17.0, -17.8,
		// 10.39}, 1000, 1, "Senegal");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {36.15d, -5.51d, 11.38d,
		// -29.09d}, 1000, 1, "Namibia_Zambia_Zimbawe_Malawi_Botswana");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {32.17d, -25.62d, 30.7d,
		// -27.5d}, 1000, 1, "Eswatini");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {30.92d, -1d, 28.78d,
		// -2.93d}, 1000, 1, "Rwanda");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {35.13d, 4.34d, 29.49d,
		// -1.56d}, 1000, 2, "Uganda");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {50.8d, 42d, 44.5d, 38.2d},
		// 1000, 1, "Azerbaijan");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {1.36d, 11.28d, -3.37d,
		// 4.64d}, 1000, 1, "Ghana");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {-60.84d, 15.67d, -61.52d,
		// 13.70d}, 1000, 1, "Caribean");

		// querySigrid.writeCsvFromBoundingBox( new Double[] {77.8d, 45.00d, 77.29d,
		// 44.58d}, 1000, 1, "Kazakhstan_CACILM");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {33.24d, 40.71d, 29.62d,
		// 38.80d}, 1000, 1, "Turkey_CACILM");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {76.68d, 42.47d, 74.65d,
		// 41.71d}, 1000, 1, "Kyrgyzstan_CACILM");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {59.84d, 42.13d, 59.37d,
		// 41.8d}, 1000, 1, "Turkmenistan_Gurbansoltaneje_CACILM");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {70.5d, 38.71d, 69.8d,
		// 38.31d}, 1000, 1, "Tajikistan_CACILM");
		// querySigrid.writeCsvFromBoundingBox( new Double[] {65.42d, 41.45d, 62.08d,
		// 38.9d}, 1000, 1, "Uzbekistan_CACILM");
		System.exit(0);
	}
}
