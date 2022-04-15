# SIGRID
Systematic Iterative GRID - Global Systematic Grid of points at 1x1 km with sub-nested grids at any spacing

# What is it?
SIGRID was designed in order to be a Global grid where the distance between plots is homogeneus for any latitude.
The plots in SIGRID are designed row by row ( East to West), moving North to South, in such a way that the latitude for each row of plots is constant and the distance in degrees that equates to 1.000 meters at that latitude is calculated and applied sequentially to each plot. This guarantees that the distance is very close to 1000 meters at any latitude.



## How to download SIGRID
To explore the grid, as it is very large, we have created a KML file that allows for download of the grid in tiles of 10 by 10 degrees.

You can access it through this [Google Earth file (KMZ)](https://raw.githubusercontent.com/herrtunante/SIGRID/main/resources/SIGRID_Grid_1000m_1_subgrid.kmz)

Locate the area for which you need the grid points and then click on the tile. There will be a popup with a link to download the ZIP file containing the plots for that tile.

![image](https://user-images.githubusercontent.com/4435566/144460400-d8d98726-8c89-489c-9cb8-6fecbac349a1.png)


## How to reproduce the grid

In order to reproduce the grid you need to clone this repository and execute the main class of `GenerateSigrid.java`
There is an option in the code to limit the plots to those within a bounding bos, specifying Nort, South, East, West coordinates.
This is handy as generating all of the plots worldwide can take up to one day on a normal computer.
