# SIGRID
Systematic Iterative GRID - Global Systematic Grid of points at 1x1 km with sub-nested grids at any spacing

# What is it?
SIGRID was designed in order to be a Global grid where the distance between plots is homogeneous for any latitude.
The plots in SIGRID are designed row by row ( East to West), moving North to South, in such a way that the latitude for each row of plots is constant and the distance in degrees that equates to 1.000 meters at that latitude is calculated and applied sequentially to each plot. This guarantees that the distance is very close to 1000 meters at any latitude.

The structure of the CSV files with SIGRID plots allows to easily choose different plot distances based on the original 1.000 meters grid. I.e. one could generate an 8km, 4km or 2km grid, maintaining ID consistency, allowing to perform nested spatial surveys for instance.

This image represents the SIGRID plots when stratified to 200km distance ( you can [download the KMZ file here](https://raw.githubusercontent.com/herrtunante/SIGRID/main/resources/SIGRID%20-%20Example%20at%20200km%20distance.kmz) )
![googleearth_2022-04-15_11-07-21](https://user-images.githubusercontent.com/4435566/163554788-8a4431d0-6141-4584-95ce-fc62ba64c444.jpg)


This is the detail of the SIGRID plots at 1000 m distance in an area in northern Europe where other grid types generate distortions on the spacing due to the high latitude:

![googleearth_2022-04-15_11-32-50](https://user-images.githubusercontent.com/4435566/163554751-255a1a9a-9db4-4a20-bd1f-40e7c815fdd3.jpg)




## How to download SIGRID
To explore the grid, as it is very large, we have created a KML file that allows for download of the grid in tiles of 10 by 10 degrees.

You can access it through this [Google Earth file (KMZ)](https://raw.githubusercontent.com/herrtunante/SIGRID/main/resources/SIGRID_Grid_1000m_1_subgrid.kmz)

Locate the area for which you need the grid points and then click on the tile. There will be a popup with a link to download the ZIP file containing the plots for that tile.

![image](https://user-images.githubusercontent.com/4435566/144460400-d8d98726-8c89-489c-9cb8-6fecbac349a1.png)

### Data format

The CSVs that can be downloaded from the links provided in [the KMZ file](https://raw.githubusercontent.com/herrtunante/SIGRID/main/resources/SIGRID_Grid_1000m_1_subgrid.kmz) (that can be opened through Google Earth Pro ) have a format like this:

|CE_ID    |yCoordinate|xCoordinate|grid_1_SIGRID_x_20_30_y_50_60|grid_2_SIGRID_x_20_30_y_50_60|grid_3_SIGRID_x_20_30_y_50_60|grid_4_SIGRID_x_20_30_y_50_60|grid_5_SIGRID_x_20_30_y_50_60|grid_6_SIGRID_x_20_30_y_50_60|grid_8_SIGRID_x_20_30_y_50_60|grid_9_SIGRID_x_20_30_y_50_60|grid_10_SIGRID_x_20_30_y_50_60|grid_12_SIGRID_x_20_30_y_50_60|grid_15_SIGRID_x_20_30_y_50_60|grid_16_SIGRID_x_20_30_y_50_60|grid_20_SIGRID_x_20_30_y_50_60|grid_25_SIGRID_x_20_30_y_50_60|grid_30_SIGRID_x_20_30_y_50_60|grid_50_SIGRID_x_20_30_y_50_60|grid_100_SIGRID_x_20_30_y_50_60|
|---------|-----------|-----------|-----------------------------|-----------------------------|-----------------------------|-----------------------------|-----------------------------|-----------------------------|-----------------------------|-----------------------------|------------------------------|------------------------------|------------------------------|------------------------------|------------------------------|------------------------------|------------------------------|------------------------------|-------------------------------|
|2790_8986|59.9949504 |29.9851232 |true                         |true                         |false                        |false                        |false                        |false                        |false                        |false                        |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                          |
|2790_8987|59.9949504 |29.9672064 |true                         |false                        |false                        |false                        |false                        |false                        |false                        |false                        |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                          |
|2790_8988|59.9949504 |29.9492864 |true                         |true                         |true                         |false                        |false                        |true                         |false                        |false                        |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                          |
|2790_8989|59.9949504 |29.9313664 |true                         |false                        |false                        |false                        |false                        |false                        |false                        |false                        |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                          |
|2790_8990|59.9949504 |29.9134496 |true                         |true                         |false                        |false                        |true                         |false                        |false                        |false                        |true                          |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                          |
|2790_8991|59.9949504 |29.8955296 |true                         |false                        |true                         |false                        |false                        |false                        |false                        |true                         |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                         |false                          |


## How to reproduce the grid

In order to reproduce the grid you need to clone this repository and execute the main class of `GenerateSigrid.java` [(code)](https://github.com/herrtunante/SIGRID/blob/main/src/main/java/org/openforis/sigrid/GenerateSigrid.java)

There is an option in the code to limit the plots to those within a bounding box, specifying North, South, East, West coordinates.
This is handy as generating all of the plots worldwide can take up to one day on a standard computer.
