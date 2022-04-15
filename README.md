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


The column **CE_ID** is the unique ID of the plot, composed of two number **Y_X**. The **Y** represents the row from the starting point of the grid generation 85 degrees North, 169 degrees East (i.e. 2000_3300 means 2.000 km south of the starting latitude of the grid - which is 85 degrees North - and 3.300 km West of the starting longitude - which is 169 degrees East ). 

This is followed by the Latitude (**yCoordinate**) and Longitude (**xCoordinate**) of the center of the plot. 

The columns that follow indicate to which subgrid the plot belongs to . All the plots belong to the subgrid 1 (1000 m distance) while 1/4 of the plots belong to the 2x2 km subgrid, 1/9 of th plots belong to the 3x3km subgrid, 1/16 of the plots belong to the 4x4 km subgrid, 1/25 of the plots belong to the 5x5 km grid and so on. The information of the subgrid columns can be combined to filter the plots into any desired subgrid. I.e. the subgrid of plots for 18 x18 km can be obtained combining plots that belong to both the 9x9 km subgrid and the 6x6km subgrid ( using the filters in tools like Excel). 

Having a homogeneus grid like SIGRID allows to generate Collect Earth assessments that can be easily intensified. You could start with an 8x8 km grid and depending on your resources or accuracy goals on the assessment easily move on to the remaining plots in the 4x4 km grid that were not assessed already. Again, you could move to the 2x2km grid following the same logic and even to a 1x1 km grid to achieve maximum accuracy.

## How to reproduce the grid

In order to reproduce the grid you need to clone this repository and execute the main class of `GenerateSigrid.java` [(code)](https://github.com/herrtunante/SIGRID/blob/main/src/main/java/org/openforis/sigrid/GenerateSigrid.java)

There is an option in the code to limit the plots to those within a bounding box, specifying North, South, East, West coordinates.
This is handy as generating all of the plots worldwide can take up to one day on a standard computer.
