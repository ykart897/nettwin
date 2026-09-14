import L from "leaflet";
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";

function stationTone(metric, station, alerts) {
  const hasCritical = alerts.some(
    (alert) =>
      (alert.asset_id === station.id || alert.base_station_id === station.id) &&
      ["Critical", "High"].includes(alert.severity)
  );
  if (hasCritical || metric?.is_anomaly) return "#ff5a5f";
  if (metric && station.max_capacity && metric.connected_users > station.max_capacity * 0.8) return "#f4b942";
  if (metric && metric.signal_strength_dbm < -90) return "#ff8b3d";
  return "#39d98a";
}

export default function NetworkMap({ stations, latestByStation, alerts, topology = [] }) {
  const locatedStations = stations.filter(
    (station) => {
      const metric = latestByStation[station.id];
      return (metric?.latitude ?? station.latitude) != null && (metric?.longitude ?? station.longitude) != null;
    }
  );
  if (locatedStations.length === 0) {
    return <section className="loading-panel">No located network assets are available for the map.</section>;
  }
  const stationById = Object.fromEntries(stations.map((station) => [station.id, station]));
  return (
    <section className="map-section">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Istanbul radio mesh</p>
          <h2>Base stations and coverage health</h2>
        </div>
      </div>
      {topology.length === 0 && (
        <p className="empty-state">
          No inferred topology links are available. Located assets are shown independently.
        </p>
      )}
      <div className="map-wrap">
        <MapContainer center={[41.05, 29.04]} zoom={10} scrollWheelZoom className="network-map">
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {topology.map((relation) => {
            const source = stationById[relation.source_asset_id];
            const target = stationById[relation.target_asset_id];
            if (
              source?.latitude == null ||
              source?.longitude == null ||
              target?.latitude == null ||
              target?.longitude == null
            ) return null;
            return (
              <Polyline
                key={relation.id}
                positions={[
                  [source.latitude, source.longitude],
                  [target.latitude, target.longitude]
                ]}
                pathOptions={{
                  color: relation.relation_type === "MEASURED_BY" ? "#5cc8ff" : "#59635f",
                  weight: 1,
                  opacity: 0.5
                }}
              />
            );
          })}
          {stations.map((station) => {
            const metric = latestByStation[station.id];
            const latitude = metric?.latitude ?? station.latitude;
            const longitude = metric?.longitude ?? station.longitude;
            const color = stationTone(metric, station, alerts);
            const isAsset = Boolean(station.asset_type);
            const marker = isAsset
              ? L.divIcon({
                  className: "asset-marker-wrap",
                  html: `<span class="asset-marker ${station.asset_type}" title="${station.asset_type}"></span>`,
                  iconSize: [22, 22],
                  iconAnchor: [11, 11]
                })
              : null;
            if (latitude == null || longitude == null) return null;
            const popup = (
              <Popup>
                <strong>{station.name}</strong>
                <dl className="popup-grid">
                  <dt>{isAsset ? "Type" : "Region"}</dt>
                  <dd>{isAsset ? station.asset_type.replaceAll("_", " ") : station.region}</dd>
                  {isAsset && (
                    <>
                      <dt>Source</dt>
                      <dd>{station.source.replaceAll("_", " ")}</dd>
                      <dt>Technology</dt>
                      <dd>{station.technology || "-"}</dd>
                      <dt>Load index</dt>
                      <dd>{metric?.load_index ?? "-"}</dd>
                    </>
                  )}
                  {!isAsset && (
                    <>
                      <dt>Users</dt>
                      <dd>{metric?.connected_users ?? "-"}</dd>
                    </>
                  )}
                  <dt>Latency</dt>
                  <dd>{metric?.latency_ms ?? "-"} ms</dd>
                  <dt>Signal</dt>
                  <dd>{metric?.signal_strength_dbm ?? "-"} dBm</dd>
                </dl>
              </Popup>
            );
            if (isAsset) {
              return (
                <Marker
                  key={`${station.source}-${station.external_id}`}
                  position={[latitude, longitude]}
                  icon={marker}
                >
                  {popup}
                </Marker>
              );
            }
            return (
              <CircleMarker
                key={station.id}
                center={[latitude, longitude]}
                radius={metric ? Math.max(8, Math.min(24, metric.connected_users / 8)) : 10}
                pathOptions={{ color, fillColor: color, fillOpacity: 0.42, weight: 2 }}
              >
                {popup}
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>
    </section>
  );
}
