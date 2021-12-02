package org.openforis.sigrid;

public class Tile {

	private String id;

	private Integer south;
	private Integer north;
	private Integer east;
	private Integer west;

	private Integer centerLong;
	private Integer centerLat;
	private String linkUrl;

	public Integer getSouth() {
		return south;
	}
	public void setSouth(Integer south) {
		this.south = south;
	}
	public Integer getNorth() {
		return north;
	}
	public void setNorth(Integer north) {
		this.north = north;
	}
	public Integer getEast() {
		return east;
	}
	public void setEast(Integer east) {
		this.east = east;
	}
	public Integer getWest() {
		return west;
	}
	public void setWest(Integer west) {
		this.west = west;
	}
	public Integer getCenterLong() {
		return centerLong;
	}
	public void setCenterLong(Integer centerLong) {
		this.centerLong = centerLong;
	}
	public Integer getCenterLat() {
		return centerLat;
	}
	public void setCenterLat(Integer centerLat) {
		this.centerLat = centerLat;
	}
	public String getLinkUrl() {
		return linkUrl;
	}
	public void setLinkUrl(String linkUrl) {
		this.linkUrl = linkUrl;
	}
	public String getId() {
		return id;
	}
	public void setId(String id) {
		this.id = id;
	}
}
