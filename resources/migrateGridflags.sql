-- Migrates the gridflags column of a plot table populated by the OLD JDBCStore code
-- to the NEW bitmask scheme, without regenerating the grid.
--
-- Old scheme: bit position = density value (1 << d). Java shifts modulo 32, so the
-- 50 km flag landed on bit 18 and the 100 km flag collided with the 4 km flag on
-- bit 4; both were unqueryable.
-- New scheme: bit position = index of the density in the distances array
-- {1,2,3,4,5,6,8,9,10,12,15,16,20,25,30,50,100}, i.e. bits 0-16.
--
-- gridflags is fully derived from row and col, so this recomputes it from scratch.
-- Works on both SQLite and PostgreSQL. Note: coordinates written by the old code
-- carry ~1 m of float-rounding noise that this migration cannot fix; only
-- regenerating the grid recomputes them at full double precision.

UPDATE plot SET gridflags =
    (CASE WHEN row % 1   = 0 AND col % 1   = 0 THEN 1     ELSE 0 END)
  + (CASE WHEN row % 2   = 0 AND col % 2   = 0 THEN 2     ELSE 0 END)
  + (CASE WHEN row % 3   = 0 AND col % 3   = 0 THEN 4     ELSE 0 END)
  + (CASE WHEN row % 4   = 0 AND col % 4   = 0 THEN 8     ELSE 0 END)
  + (CASE WHEN row % 5   = 0 AND col % 5   = 0 THEN 16    ELSE 0 END)
  + (CASE WHEN row % 6   = 0 AND col % 6   = 0 THEN 32    ELSE 0 END)
  + (CASE WHEN row % 8   = 0 AND col % 8   = 0 THEN 64    ELSE 0 END)
  + (CASE WHEN row % 9   = 0 AND col % 9   = 0 THEN 128   ELSE 0 END)
  + (CASE WHEN row % 10  = 0 AND col % 10  = 0 THEN 256   ELSE 0 END)
  + (CASE WHEN row % 12  = 0 AND col % 12  = 0 THEN 512   ELSE 0 END)
  + (CASE WHEN row % 15  = 0 AND col % 15  = 0 THEN 1024  ELSE 0 END)
  + (CASE WHEN row % 16  = 0 AND col % 16  = 0 THEN 2048  ELSE 0 END)
  + (CASE WHEN row % 20  = 0 AND col % 20  = 0 THEN 4096  ELSE 0 END)
  + (CASE WHEN row % 25  = 0 AND col % 25  = 0 THEN 8192  ELSE 0 END)
  + (CASE WHEN row % 30  = 0 AND col % 30  = 0 THEN 16384 ELSE 0 END)
  + (CASE WHEN row % 50  = 0 AND col % 50  = 0 THEN 32768 ELSE 0 END)
  + (CASE WHEN row % 100 = 0 AND col % 100 = 0 THEN 65536 ELSE 0 END);
