package org.openforis.sigrid;

import java.util.Arrays;

import org.geotools.referencing.GeodeticCalculator;
import org.geotools.referencing.crs.DefaultGeographicCRS;
import org.opengis.referencing.operation.TransformException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CoordinateUtils {

	private CoordinateUtils() {}

	private static GeodeticCalculator calc = new GeodeticCalculator(DefaultGeographicCRS.WGS84);

	private static final Logger logger = LoggerFactory.getLogger(CoordinateUtils.class);

	/**
	 * Returns the GWS84 coordinated as an array containing [latitude, longitude] after having translocated the point using the offset.
	 *
	 * @param originalLatLong
	 *            The original point as a WGS84 coordinate duple. latitude, longitude
	 * @param offsetLongitudeMeters
	 *            The amount of meters to displace the original point in the X axis. 0 does nothing, negative values move it WEST and positive values
	 *            move it EAST
	 * @param offsetLatitudeMeters
	 *            The amount of meters to displace the original point in the Y axis. 0 does nothing, negative values move it SOUTH and positive values
	 *            move it NORTH
	 * @return The coordinates of the original point after being displaced using theprovided offsets as longitude, latitude.
	 * @throws TransformException
	 */
	public static synchronized double[] getPointWithOffset(double[] originalLatLong, double offsetLongitudeMeters, double offsetLatitudeMeters)
			throws TransformException {
		double[] movedPointLatLong = null;
		try {

			if (offsetLatitudeMeters == 0 && offsetLongitudeMeters == 0) {
				return movedPointLatLong;
			} else {

				double longitudeDirection = 90; // EAST
				if (offsetLongitudeMeters < 0) {
					longitudeDirection = -90; // WEST
				}

				double latitudeDirection = 0; // NORTH
				if (offsetLatitudeMeters < 0) {
					latitudeDirection = 180; // SOUTH
				}

				calc.setStartingGeographicPoint( originalLatLong[1], originalLatLong[0]);

				boolean longitudeChanged = false;
				if (offsetLongitudeMeters != 0) {
					calc.setDirection(longitudeDirection, Math.abs( offsetLongitudeMeters ) );
					longitudeChanged = true;
				}

				if (offsetLatitudeMeters != 0) {
					if (longitudeChanged) {
						// Move the point in the horizontal axis first, afterwards reset the point and move vertically
						final double[] firstMove = calc.getDestinationPosition().getCoordinate();
						calc.setStartingGeographicPoint(firstMove[0], firstMove[1]);
					}
					calc.setDirection(latitudeDirection, Math.abs( offsetLatitudeMeters ) );
				}

				movedPointLatLong = calc.getDestinationPosition().getCoordinate();
			}
		} catch (final Exception e) {
			logger.error(
					"Exception when moving point {} with offset longitude {} and latitude {}", Arrays.toString(originalLatLong), offsetLongitudeMeters, offsetLatitudeMeters, e);
		}

		return( movedPointLatLong!= null ? new double[]{ movedPointLatLong[1], movedPointLatLong[0]}:null);

	}

}
