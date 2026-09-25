import { Link } from "react-router-dom";

function Navbar() {
  return (
    <nav
      style={{
        background: "#111827",
        padding: "15px 30px",
        borderBottom: "1px solid #374151",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <h2
        style={{
          color: "white",
          margin: 0,
        }}
      >
        HeritageQuest AI
      </h2>

      <div
        style={{
          display: "flex",
          gap: "20px",
        }}
      >
        <Link
          to="/"
          style={{
            color: "white",
            textDecoration: "none",
          }}
        >
          Home
        </Link>

        <Link
          to="/monument"
          style={{
            color: "white",
            textDecoration: "none",
          }}
        >
          Monument
        </Link>

        <Link
          to="/trip-planner"
          style={{
            color: "white",
            textDecoration: "none",
          }}
        >
          Trip Planner
        </Link>

        <Link
          to="/food"
          style={{
            color: "white",
            textDecoration: "none",
          }}
        >
          Food Explorer
        </Link>

        <Link
          to="/language"
          style={{
            color: "white",
            textDecoration: "none",
          }}
        >
          Language Learning
        </Link>
      </div>
    </nav>
  );
}

export default Navbar;