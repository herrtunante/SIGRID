package org.openforis.sigrid;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class GenerateSystematicGlobalGrid{

	public static void main(String[] args)  {
		GenerateSystematicGlobalGrid globalGrid = new GenerateSystematicGlobalGrid();
		globalGrid.generate();

	}

	private static final Integer DISTANCE_BETWEEN_PLOTS_IN_METERS = 1000;	// 1x1 km global grid

	private static final Double STARTING_LONGITUDE = -169d;					// starting in this longitude so that there are no landmasses affected

	private static final Double STARTING_LATITUDE = 85d;					// From 85 degrees North

	private static final Double ENDING_LATITUDE = -85d;						// To 85 degrees South

	private Logger logger = LoggerFactory.getLogger(this.getClass());

	private AbstractStore store = new CSVStore();

	public void generate(){
		long startTime = System.currentTimeMillis();
		try {


			store.initializeStore( DISTANCE_BETWEEN_PLOTS_IN_METERS );

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
					store.savePlot( latitude, longitude, row,  column);

					pointWithOffset = CoordinateUtils.getPointWithOffset( new double[]{ latitude, longitude}, DISTANCE_BETWEEN_PLOTS_IN_METERS*-1, 0); // Move DISTANCE Westwards
					longitude = pointWithOffset[1];

					if( firstPass ) {
						firstPass = longitude <= STARTING_LONGITUDE;
					}
					moveToNextRow = !firstPass && (  STARTING_LONGITUDE > longitude );
					column ++;
				}
				logger.info( "Finished row - {}", row);
				row++;
				column = 0;

				pointWithOffset = CoordinateUtils.getPointWithOffset( new double[]{ latitude, STARTING_LONGITUDE},  0, DISTANCE_BETWEEN_PLOTS_IN_METERS*-1); // Move DISTANCE Southwards
				longitude = STARTING_LONGITUDE;
				latitude = pointWithOffset[0];
			}

		}  catch (Exception e) {
			logger.error(" Error transforming the point coordinates ", e );
		} finally {
			logger.info( "Total time millis {}", System.currentTimeMillis() - startTime );
			store.closeStore();
		}

	}
}
