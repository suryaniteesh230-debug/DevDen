import Navbar from "../components/Navbar";
import { FaUtensils } from "react-icons/fa";

function FoodExplorer() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0f172a",
        color: "white",
        padding: "40px",
      }}
    >
      <div
        style={{
          maxWidth: "900px",
          margin: "0 auto",
          textAlign: "center",
        }}
      >
        <FaUtensils
          size={70}
          color="#2563eb"
        />

        <h1
          style={{
            marginTop: "20px",
            fontSize: "3rem",
          }}
        >
          Heritage Food Explorer
        </h1>

        <p
          style={{
            color: "#9ca3af",
            fontSize: "18px",
            marginTop: "10px",
          }}
        >
          Discover authentic local food experiences
          near heritage destinations.
        </p>

        <div
          style={{
            marginTop: "60px",
            padding: "40px",
            background: "#111827",
            border: "1px solid #374151",
            borderRadius: "20px",
          }}
        >
          <h2>
            🚧 Coming Soon
          </h2>

          <p
            style={{
              marginTop: "20px",
              color: "#d1d5db",
              lineHeight: "1.8",
            }}
          >
            This feature will recommend authentic
            local restaurants, cafes, and food
            experiences around the heritage sites
            selected in your trip itinerary.
          </p>

          <p
            style={{
              marginTop: "15px",
              color: "#9ca3af",
            }}
          >
            Planned Features:
          </p>

          <ul
            style={{
              textAlign: "left",
              maxWidth: "500px",
              margin: "20px auto",
              color: "#d1d5db",
            }}
          >
            <li>
              Nearby local food recommendations
            </li>

            <li>
              Heritage cuisine discovery
            </li>

            <li>
              Google Maps navigation
            </li>

            <li>
              Restaurant ratings and reviews
            </li>

            <li>
              Integration with Trip Planner
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default FoodExplorer;