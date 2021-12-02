package org.openforis.sigrid;

import java.io.BufferedOutputStream;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.util.ArrayList;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.opencsv.CSVWriter;

public class CSVStore extends AbstractStore{

	private CSVWriter[] writers;
	private Integer[] rowCounters;
	private ZipOutputStream[] zosForWriterOutputStreams;
	private String[] namePrefix;
	private String[] headerArray;

	private static final int FLUSH_ROWS = 250000;
	private static final int NEW_ENTRY_ROWS = 500000;

	private Logger logger = LoggerFactory.getLogger(CSVStore.class);

	private CSVWriter[] getWriters() {
		return writers;
	}

	private void setWriters(CSVWriter[] writers) {
		this.writers = writers;
	}

	private Integer[] getRowCounters() {
		return rowCounters;
	}

	private void setRowCounters(Integer[] rowCounters) {
		this.rowCounters = rowCounters;
	}

	private ZipOutputStream[] getZosForWriterOutputStreams() {
		return zosForWriterOutputStreams;
	}

	private void setZosForWriterOutputStreams(ZipOutputStream[] zosForWriterOutputStreams) {
		this.zosForWriterOutputStreams = zosForWriterOutputStreams;
	}

	private String[] getNamePrefix() {
		return namePrefix;
	}

	private void setNamePrefix(String[] namePrefix) {
		this.namePrefix = namePrefix;
	}

	private String[] getHeaderArray() {
		return headerArray;
	}

	private void setHeaderArray(String[] headerArray) {
		this.headerArray = headerArray;
	}


	public void closeStore() {
		for (CSVWriter w : getWriters()) {
			try {
				w.close();
			} catch (IOException e) {
				logger.error("error closing the file", e);
			}
		}
	}

	public void initializeStore( int distanceBetweenPlots, boolean zipOutput ) {
		initializeStore( distanceBetweenPlots, "global", zipOutput );
	}

	@Override
	public void initializeStore(int distanceBetweenPlots) throws Exception {
		initializeStore( distanceBetweenPlots, true );
	}

	public void initializeStore( int distanceBetweenPlots, String prefix, boolean zipOutput ) {

		ArrayList<String> headers = new ArrayList<>();
		headers.add("CE_ID");
		headers.add("yCoordinate");
		headers.add("xCoordinate");

		for (Integer d : getDistances()) {
			headers.add("grid_" + d + "_"+ prefix);
		}

		File outputDir = new File( "output" );
		if( !outputDir.isDirectory() )
			outputDir.mkdir();

		setHeaderArray(new String[headers.size()]);
		headers.toArray(getHeaderArray());

		setWriters(new CSVWriter[ getDistances().length ]);
		setNamePrefix(new String[ getDistances().length ]);
		setZosForWriterOutputStreams(new ZipOutputStream[ getDistances().length ]);
		setRowCounters(new Integer[ getDistances().length ]);


		try {
			int arrIdx=0;
			for (Integer d : getDistances()) {
				File fileOutput = new File(outputDir,  prefix +"_" + distanceBetweenPlots+ "m_"+ d +"_subgrid.csv" + ( zipOutput?".zip":"" ) );
				logger.info( fileOutput.getAbsolutePath() );

				Writer writer = null;
				CSVWriter w = null;
				try( FileWriter file = new FileWriter( fileOutput ) ){

					if( zipOutput ) {
						FileOutputStream fos =  new FileOutputStream( fileOutput );
						BufferedOutputStream bos = new BufferedOutputStream(fos);
						ZipOutputStream zos = new ZipOutputStream(bos);
						getNamePrefix()[arrIdx] = prefix +"_" + distanceBetweenPlots+ "m_"+ d;
						zos.putNextEntry( new ZipEntry( getNamePrefix()[arrIdx] +"_subgrid_0.csv" ) );
						getZosForWriterOutputStreams()[arrIdx] = zos;
						writer = new OutputStreamWriter( zos );
					}else {
						writer = new BufferedWriter(file);
					}

					w =  new CSVWriter(  writer );
					w.writeNext( getHeaderArray() );

					getWriters()[arrIdx] = w;
					getRowCounters()[arrIdx] = 0;

					arrIdx++;

				}catch( Exception e) {
					if( w != null )
						w.close();
				}

			}
		} catch (IOException e) {
			logger.error("Error writing to CSV", e);
		}
	}

	public void savePlot( Double latitude, Double longitude, Integer row, Integer column ) {

		String[] csvContents  = new String[ 5 + getDistances().length ];
		csvContents[0] = Integer.toString( row ) + "_" + Integer.toString( column );
		csvContents[1] = Double.toString(latitude);
		csvContents[2] = Double.toString(longitude);

		int i =0;
		Boolean[] grids = new Boolean[ getDistances().length ];
		for (Integer d : getDistances()) {
			Boolean grid = (column%d + row%d == 0);
			csvContents[ 3+i ] = grid.toString();
			grids[i] = grid;
			i++;
		}

		for (int j = 0; j < grids.length; j++) {
			if( Boolean.TRUE.equals( grids[j] ) ) {
				getWriters()[j].writeNext( csvContents );
				getRowCounters()[j] = getRowCounters()[j] + 1;
				if( getRowCounters()[j] % FLUSH_ROWS == 0 ) {
					logger.info( "Flushing! {}" , getRowCounters()[j] );
					try {
						getWriters()[j].flush();
					} catch (IOException e) {
						logger.error("Error flushing rows!!", e);
					}
				}

				if( getRowCounters()[j] % NEW_ENTRY_ROWS == 0 ) {

					try {
						getWriters()[j].flush();

						if( getZosForWriterOutputStreams()[j] != null ) {
							int fileIndex = Math.abs( getRowCounters()[j] / NEW_ENTRY_ROWS );

							String newFileName = getNamePrefix()[j] +"_subgrid_" + fileIndex + ".csv";
							logger.info( "New Zip file! {}", newFileName );
							getZosForWriterOutputStreams()[j].putNextEntry( new ZipEntry( newFileName ) );

							getWriters()[j].writeNext( getHeaderArray() );
						}

					} catch (IOException e) {
						logger.error("Error flushing rows!!", e);
					}
				}


			}
		}
	}


}
