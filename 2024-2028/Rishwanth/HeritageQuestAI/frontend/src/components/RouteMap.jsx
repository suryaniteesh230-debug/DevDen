import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  Tooltip,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

import L from "leaflet";
import iconUrl from "leaflet/dist/images/marker-icon.png";
import iconShadowUrl from "leaflet/dist/images/marker-shadow.png";

const DefaultIcon = L.icon({
  iconUrl,
  shadowUrl: iconShadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});
L.Marker.prototype.options.icon = DefaultIcon;

const SEGMENT_COLORS = [
  "#ef4444",
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
];

function getMidpoint(coords) {
  if (!coords || coords.length === 0) return null;
  const midIndex = Math.floor(coords.length / 2);
  return coords[midIndex];
}

function RouteMap({ itinerary, segments }) {
  if (!itinerary || itinerary.length === 0) {
    return (
      <div style={s.fallback}>No route data available.</div>
    );
  }

  const validPlaces = itinerary.filter(
    (place) =>
      place.lat !== null &&
      place.lng !== null &&
      !isNaN(place.lat) &&
      !isNaN(place.lng)
  );

  if (validPlaces.length === 0) {
    return (
      <div style={s.fallback}>No valid coordinates found.</div>
    );
  }

  const center = [validPlaces[0].lat, validPlaces[0].lng];

  return (
    <MapContainer
      center={center}
      zoom={12}
      style={s.mapContainer}
    >
      <TileLayer
        attribution="© OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {/* Markers */}
      {validPlaces.map((place, index) => (
        <Marker key={index} position={[place.lat, place.lng]}>
          <Popup>
            <strong>Stop {index + 1}</strong>
            <br />
            {place.location}
            {place.slot && (
              <>
                <br />
                <span style={{ color: "#6b7280", fontSize: "12px" }}>
                  {place.slot}
                </span>
              </>
            )}
          </Popup>
        </Marker>
      ))}

      {/* Road-following route segments */}
      {segments &&
        segments.map((segment, index) => {
          if (!segment.geometry || segment.geometry.length === 0) return null;

          // OSRM returns [lng, lat]; Leaflet needs [lat, lng]
          const positions = segment.geometry.map(
            ([lng, lat]) => [lat, lng]
          );

          const color = SEGMENT_COLORS[index % SEGMENT_COLORS.length];

          const midpoint = getMidpoint(positions);

          return (
            <Polyline
              key={index}
              positions={positions}
              pathOptions={{
                color: color,
                weight: 5,
                opacity: 0.9,
              }}
            >
              {midpoint && (
                <Tooltip
                  permanent
                  direction="center"
                  position={midpoint}
                >
                  🚗 {segment.duration} mins
                  <br />
                  {segment.distance} km
                </Tooltip>
              )}
            </Polyline>
          );
        })}
    </MapContainer>
  );
}

const s = {
  mapContainer: {
    height: "100%",
    width: "100%",
  },
  fallback: {
    height: "100%",
    width: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#9ca3af",
    background: "#111827",
    fontSize: "14px",
  },
};

export default RouteMap;