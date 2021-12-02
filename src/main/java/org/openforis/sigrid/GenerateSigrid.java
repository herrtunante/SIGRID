package org.openforis.sigrid;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.sqlite.SQLiteException;

public class GenerateSigrid{

	public static void main(String[] args)  {
		GenerateSigrid globalGrid = new GenerateSigrid();
		// globalGrid.generate(); // Generates ALL of the plots of the SIGRID grid and stores them into a DB
		globalGrid.generate( -160d, -70d, -170d, -80d); // Generates plots for quadrant EAST (maxX), NORTH (maxY), WEST (minX), SOUTH (minY)

	}

	private static final Integer DISTANCE_BETWEEN_PLOTS_IN_METERS = 1000;	// 1x1 km global grid

	private static final Double STARTING_LONGITUDE = -169d;					// starting in this longitude so that there are no landmasses affected

	private static final Double STARTING_LATITUDE = 85d;					// From 85 degrees North

	private static final Double ENDING_LATITUDE = -85d;						// To 85 degrees South

	private Logger logger = LoggerFactory.getLogger(this.getClass());

	private static final AbstractStore STORE = new CSVStore();


	public void generate(){
		generate( null, null, null, null  ); // Generate and save to store ALL of the SIGRID plots
	}

	/**
	 * @param withinBoundingBox BoundingBox for which to generate the plots! The rest of the globe will be ignored. Bounding box array : EAST (maxX), NORTH (maxY), WEST (minX), SOUTH (minY)
	 */
	public void generate( Double east, Double north, Double west, Double south  ){
		long startTime = System.currentTimeMillis();
		try {


			STORE.initializeStore( DISTANCE_BETWEEN_PLOTS_IN_METERS );

			Double latitude = STARTING_LATITUDE;
			Double longitude = STARTING_LONGITUDE;

			double[] pointWithOffset = new double[]{ latitude, longitude};
			boolean firstPass;
			boolean moveToNextRow;
			Integer row = 0;
			Integer column = 0;


			while( ( latitude > ENDING_LATITUDE ) ){
				firstPass = true;
				moveToNextRow = false;


				while( !moveToNextRow ){
					if(
							east == null										// No bounding parameters set! then we save ALL the plots
							||
							(
									latitude <= north &&  latitude >= south
												&&								// Bounding parameters set AND point inside the bounds, then we save the plot!
									longitude <= east && longitude >= west
							)
					) {
						STORE.savePlot( latitude, longitude, row,  column);
					}

					if(
						( north != null && latitude>north )
					){
						moveToNextRow = true;
						continue;
					}

					pointWithOffset = CoordinateUtils.getPointWithOffset( new double[]{ latitude.doubleValue(), longitude.doubleValue()}, DISTANCE_BETWEEN_PLOTS_IN_METERS*-1, 0); // Move DISTANCE Westwards
					longitude = pointWithOffset[1];


					if( firstPass ) {
						firstPass = longitude <= STARTING_LONGITUDE;
					}
					moveToNextRow = !firstPass && (  STARTING_LONGITUDE > longitude );
					column ++;
				}
				row++;
				column = 0;
				pointWithOffset = CoordinateUtils.getPointWithOffset( new double[]{ latitude.doubleValue(), STARTING_LONGITUDE.doubleValue()},  0, DISTANCE_BETWEEN_PLOTS_IN_METERS*-1); // Move DISTANCE Southwards
				longitude = STARTING_LONGITUDE;
				latitude = pointWithOffset[0];

				if( south != null && latitude<south ) {
					break;
				}
			}


		}  catch (SQLiteException e) {
			logger.error(" Error with SQL query ", e );
		}catch (Exception e) {
			logger.error(" Error transforming the point coordinates ", e );
		} finally {
			logger.info( "Total time millis {}",System.currentTimeMillis() - startTime);
			STORE.closeStore();
		}

	}
}
