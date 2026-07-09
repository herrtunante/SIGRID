package org.openforis.sigrid;

import java.io.File;
import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import org.apache.commons.io.FileUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class JDBCStore extends AbstractStore {

	private int count = 0;
	private int distanceBetweenPlots;
	Connection connection = null;
	private PreparedStatement insertStatement;
	private PreparedStatement selectStatement;
	private PreparedStatement selectAllStatement;
	private Logger logger = LoggerFactory.getLogger(JDBCStore.class);

	private static final Boolean USE_SQLITE = Boolean.TRUE; // FLAG to use SQLite or PostgreSQL for the database

	private static final String SQLITE_URL = "jdbc:sqlite:";
	private static final String SQLITE_FILENAME = "sigrid.db";
	private static final String POSTGRESQL_URL = "jdbc:postgresql://localhost/sigrid"; // Address od the PostgreSQL
	private static final String DB_USERNAME = "SET_YOUR_POSTGRESQL_USERNAME"; // Necessary when using PostgreSQL
	private static final String DB_PASSWORD = "SET_YOUR_POSTGRESQL_PASSWORD"; // Necessary when using PostgreSQL

	private Connection getConnection() throws SQLException {
		if (connection == null || connection.isClosed() ) {
			try {
				Class.forName("org.sqlite.JDBC");
				File sigridDBFile = new File(SQLITE_FILENAME);
				connection = DriverManager.getConnection(
						Boolean.TRUE.equals(USE_SQLITE) ?
								SQLITE_URL + sigridDBFile.getAbsolutePath()
								:
								POSTGRESQL_URL
						,
						DB_USERNAME, DB_PASSWORD);
			} catch (Exception e) {
				logger.error("Error loading JDBC driver", e);
			}
		}
		return connection;
	}

	@Override
	public void initializeStore(int distanceBetweenPlots) throws Exception {
		this.distanceBetweenPlots = distanceBetweenPlots;
		createTable();
	}

	private void createTable() throws IOException, SQLException, URISyntaxException {
		String createTable = FileUtils.readFileToString(
				new File( Boolean.TRUE.equals(USE_SQLITE) ? "resources/createTableSqlite.sql" : "resources/createTable.sql" ),
				StandardCharsets.UTF_8);
		try (Statement createStatement = getConnection().createStatement();) {
			createStatement.executeUpdate(createTable);
		}
	}

	private PreparedStatement getInsertStatement() throws SQLException {
		if (insertStatement == null) {
			String sql = "INSERT INTO plot( griddistance, row, col, gridflags, xcoordinate, ycoordinate ) "
					+ "VALUES(?,?,?,?,?,?)";
			insertStatement = getConnection().prepareStatement(sql);
		}
		return insertStatement;
	}

	private PreparedStatement getSelectStatement() throws SQLException {
		if (selectStatement == null) {
			String sql = "SELECT * FROM plot" + " WHERE " + " xcoordinate<? and ycoordinate<? " + " AND "
					+ " xcoordinate>=? and ycoordinate>=?" + " AND " + " griddistance = ? " + " AND "
					+ " gridflags & ? = ?"
			// + " LIMIT ? OFFSET ?"
			;
			selectStatement = getConnection().prepareStatement(sql);
		}
		return selectStatement;
	}

	private PreparedStatement getAllStatement() throws SQLException {
		if (selectAllStatement == null) {
			String sql = "SELECT * FROM plot" + " WHERE " + " griddistance = ? " + " AND " + " gridflags & ? = ?"
			// + " LIMIT ? OFFSET ?"
			;
			selectAllStatement = getConnection().prepareStatement(sql);
		}
		return selectAllStatement;
	}

	/**
	 * Returns the bitmask flag for a subgrid distance. The bit position is the index of the distance
	 * in the distances array (17 densities, bits 0-16), NOT the distance value itself: shifting by the
	 * distance overflows the int for the 50 and 100 km subgrids (Java shifts modulo 32).
	 */
	private int getGridFlag(Integer gridDistance) {
		Integer[] distances = getDistances();
		for (int i = 0; i < distances.length; i++) {
			if (distances[i].equals(gridDistance)) {
				return 1 << i;
			}
		}
		throw new IllegalArgumentException("Unknown subgrid distance: " + gridDistance);
	}

	@Override
	public void savePlot(Double latitude, Double longitude, Integer row, Integer column) {

		int gridFlags = 0;
		for (Integer d : getDistances()) {
			if (belongsToGrid(row, column, d)) {
				gridFlags = gridFlags | getGridFlag(d);
			}
		}

		try {

			getInsertStatement().setInt(1, distanceBetweenPlots);
			getInsertStatement().setInt(2, row);
			getInsertStatement().setInt(3, column);
			getInsertStatement().setInt(4, gridFlags);
			getInsertStatement().setInt(5, (int) Math.round(longitude * SCALING_FACTOR));
			getInsertStatement().setInt(6, (int) Math.round(latitude * SCALING_FACTOR));

			getInsertStatement().addBatch();
			count++;
			// execute the batch every 50000 rows
			if (count % 50000 == 0) {
				logger.info("Flushing to DB {}", count);
				getInsertStatement().executeBatch();

			}
		} catch (SQLException e) {
			logger.error("Error inserting data", e);
		}

	}

	public ResultSet getPlots(Integer grid, Double maxX, Double maxY, Double minX, Double minY, Integer distance) {

		int gridFlags = getGridFlag(grid);
		ResultSet results = null;

		try {

			getSelectStatement().setInt(1, (int) Math.round(maxX * SCALING_FACTOR));
			getSelectStatement().setInt(2, (int) Math.round(maxY * SCALING_FACTOR));
			getSelectStatement().setInt(3, (int) Math.round(minX * SCALING_FACTOR));
			getSelectStatement().setInt(4, (int) Math.round(minY * SCALING_FACTOR));
			getSelectStatement().setInt(5, Math.round(distance.floatValue()));
			getSelectStatement().setInt(6, gridFlags);
			getSelectStatement().setInt(7, gridFlags);

			logger.info(getSelectStatement().toString());
			results = getSelectStatement().executeQuery();

		} catch (SQLException e) {
			logger.error("Error querying the DB data", e);
		}

		return results;
	}

	public ResultSet getAllPlots(Integer grid, Integer distance) {

		int gridFlags = getGridFlag(grid);
		ResultSet results = null;

		try {

			getAllStatement().setInt(1, Math.round(distance.floatValue()));
			getAllStatement().setInt(2, gridFlags);
			getAllStatement().setInt(3, gridFlags);

			logger.info(getAllStatement().toString());
			results = getAllStatement().executeQuery();

		} catch (SQLException e) {
			logger.error("Error querying the DB data", e);
		}

		return results;
	}

	@Override
	public void closeStore() {
		try {
			if (getInsertStatement() != null) {
				getInsertStatement().executeBatch();
			}

			if (getConnection() != null) {
				getConnection().close();
				selectStatement = null;
				selectAllStatement = null;
				insertStatement = null;
			}
		} catch (SQLException e) {
			logger.error("Error closing connection", e);
		}
	}

}
