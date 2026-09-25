import { useState, useEffect } from "react";
import axios from "axios";
import RouteMap from "../components/RouteMap";


import {
  FaMapMarkerAlt,
  FaSun,
  FaCloudSun,
  FaMoon,
  FaRoute,
} from "react-icons/fa";

/* ─── Inject responsive CSS once ──────────────────────────────────────────── */
const RESPONSIVE_CSS = `
  .tp-split-screen {
    display: flex;
    gap: 16px;
    align-items: flex-start;
  }
  .tp-timeline-panel {
    width: 35%;
    flex-shrink: 0;
    max-height: 85vh;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #374151 transparent;
  }
  .tp-map-panel {
    flex: 1;
    position: sticky;
    top: 20px;
    height: 85vh;
    border-radius: 16px;
    overflow: hidden;
    border: 1px solid #374151;
  }
  @media (max-width: 768px) {
    .tp-split-screen {
      flex-direction: column;
    }
    .tp-timeline-panel {
      width: 100%;
      max-height: none;
    }
    .tp-map-panel {
      position: static;
      width: 100%;
      height: 60vw;
      min-height: 300px;
    }
  }
`;

function injectStyles() {
  if (document.getElementById("tp-responsive-styles")) return;
  const tag = document.createElement("style");
  tag.id = "tp-responsive-styles";
  tag.textContent = RESPONSIVE_CSS;
  document.head.appendChild(tag);
}

/* ─── Component ────────────────────────────────────────────────────────────── */
function TripPlanner() {
  useEffect(() => { injectStyles(); }, []);

  const [locations, setLocations] = useState(["", "", "", "", ""]);
  const [itinerary, setItinerary] = useState(null);
  const [segments, setSegments]   = useState([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");

  const handleChange = (index, value) => {
    const updated = [...locations];
    updated[index] = value;
    setLocations(updated);
  };

  const optimizeJourney = async () => {
    const validLocations = locations.filter((loc) => loc.trim() !== "");

    if (validLocations.length < 5) {
      setError("Please enter all 5 locations.");
      return;
    }

    try {
      setLoading(true);
      setError("");
      setItinerary(null);
      setSegments([]);

      const response = await axios.post("https://heritagequestai.onrender.com/plan-trip", {
        locations: validLocations,
      });

      if (response.data.error) {
        setError(response.data.error);
        return;
      }

      setItinerary(response.data.optimized_route);
      localStorage.setItem(
        "heritageRoute",
        JSON.stringify(
          response.data.optimized_route
        )
      );
      setSegments(response.data.segments || []);
    } catch (err) {
      console.error(err);
      setError("Failed to generate itinerary.");
    } finally {
      setLoading(false);
    }
  };

  const getSlotIcon = (slot) => {
    switch (slot?.toLowerCase()) {
      case "morning":   return <FaSun color="#f59e0b" />;
      case "afternoon": return <FaCloudSun color="#3b82f6" />;
      case "evening":   return <FaMoon color="#8b5cf6" />;
      default:          return <FaRoute />;
    }
  };

  return (
    <div style={s.pageWrapper}>

        {/* ── INPUT SECTION ────────────────────────────────── */}
        <div style={s.inputCard}>
          <h1 style={s.pageTitle}>
            <FaRoute style={{ marginRight: "10px" }} />
            Heritage Trip Planner
          </h1>
          <p style={s.subtitle}>
            Enter five heritage locations and generate an optimized heritage journey.
          </p>

          <h2 style={s.sectionHeading}>Locations</h2>

          <div style={s.inputGrid}>
            {locations.map((location, index) => (
              <input
                key={index}
                type="text"
                placeholder={`Location ${index + 1}`}
                value={location}
                onChange={(e) => handleChange(index, e.target.value)}
                style={s.input}
              />
            ))}
          </div>

          <button
            onClick={optimizeJourney}
            disabled={loading}
            style={{ ...s.button, opacity: loading ? 0.7 : 1, cursor: loading ? "not-allowed" : "pointer" }}
          >
            {loading ? "Optimizing…" : "Optimize Journey"}
          </button>
        </div>

        {/* ── ERROR ────────────────────────────────────────── */}
        {error && <div style={s.errorMsg}>{error}</div>}

        {/* ── SPLIT-SCREEN RESULTS ─────────────────────────── */}
        {itinerary && (
          <div className="tp-split-screen">

            {/* LEFT: Timeline panel */}
            <div className="tp-timeline-panel">
              <div style={s.timelineHeader}>
                <h2 style={s.timelineTitle}>Your Heritage Journey</h2>
                <span style={s.stopsBadge}>{itinerary.length} stops</span>
              </div>

              <div style={s.cardStack}>
                {itinerary.map((item, index) => (
                  <div key={index} style={s.stopCard}>

                    {/* Header row */}
                    <div style={s.cardHeader}>
                      <div style={s.stopNumber}>Stop {index + 1}</div>
                      <div style={s.slotBadge}>
                        {getSlotIcon(item.slot)}
                        <span style={s.slotLabel}>{item.slot}</span>
                      </div>
                    </div>

                    {/* Location */}
                    <div style={s.locationRow}>
                      <FaMapMarkerAlt color="#ef4444" size={13} />
                      <span style={s.locationText}>{item.location}</span>
                    </div>

                    {/* Coordinates */}
                    {item.lat && item.lng && (
                      <div style={s.coordText}>
                        {item.lat}, {item.lng}
                      </div>
                    )}

                    {/* Reason */}
                    {item.reason && (
                      <p style={s.reasonText}>{item.reason}</p>
                    )}

                    {/* Travel time to next stop */}
                    {item.next_stop_minutes && (
                      <div style={s.travelTime}>
                        🚗 {item.next_stop_minutes} mins to next stop
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* RIGHT: Map panel */}
            <div className="tp-map-panel">
              <RouteMap
                itinerary={itinerary}
                segments={segments}
              />
            </div>

          </div>
        )}

    </div>
  );
}

/* ─── Inline styles ────────────────────────────────────────────────────────── */
const s = {
  pageWrapper: {
    maxWidth: "1400px",
    margin: "40px auto",
    padding: "20px",
    color: "white",
    fontFamily: "Arial, sans-serif",
  },
  inputCard: {
    background: "#111827",
    border: "1px solid #374151",
    borderRadius: "16px",
    padding: "24px",
    marginBottom: "20px",
  },
  pageTitle: {
    textAlign: "center",
    marginTop: 0,
    marginBottom: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  subtitle: {
    textAlign: "center",
    color: "#9ca3af",
    marginTop: 0,
    marginBottom: "30px",
  },
  sectionHeading: {
    marginBottom: "20px",
  },
  inputGrid: {
    display: "grid",
    gap: "15px",
  },
  input: {
    padding: "14px",
    borderRadius: "10px",
    border: "1px solid #374151",
    background: "#1f2937",
    color: "white",
    fontSize: "15px",
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
  },
  button: {
    marginTop: "20px",
    padding: "14px 24px",
    borderRadius: "10px",
    border: "none",
    backgroundColor: "#2563eb",
    color: "white",
    fontSize: "16px",
  },
  errorMsg: {
    marginBottom: "16px",
    color: "#ef4444",
  },

  /* Timeline */
  timelineHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: "16px",
  },
  timelineTitle: {
    margin: 0,
    fontSize: "20px",
  },
  stopsBadge: {
    background: "#1f2937",
    border: "1px solid #374151",
    borderRadius: "20px",
    padding: "4px 12px",
    fontSize: "13px",
    color: "#9ca3af",
  },
  cardStack: {
    display: "flex",
    flexDirection: "column",
    gap: "14px",
  },

  /* Stop card */
  stopCard: {
    background: "#111827",
    border: "1px solid #374151",
    borderRadius: "14px",
    padding: "16px",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "10px",
  },
  stopNumber: {
    fontWeight: "bold",
    fontSize: "15px",
  },
  slotBadge: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    background: "#1f2937",
    borderRadius: "20px",
    padding: "4px 10px",
    fontSize: "13px",
  },
  slotLabel: {
    color: "#d1d5db",
  },
  locationRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginBottom: "6px",
  },
  locationText: {
    fontSize: "14px",
    fontWeight: "600",
  },
  coordText: {
    color: "#9ca3af",
    fontSize: "11px",
    marginBottom: "8px",
  },
  reasonText: {
    color: "#d1d5db",
    fontSize: "13px",
    lineHeight: "1.6",
    margin: "0 0 10px 0",
  },
  travelTime: {
    color: "#60a5fa",
    fontWeight: "bold",
    fontSize: "13px",
    marginTop: "6px",
  },
};

export default TripPlanner;