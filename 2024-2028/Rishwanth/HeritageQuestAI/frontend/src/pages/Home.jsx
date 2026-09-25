import { Link } from "react-router-dom";
import {
  FaLandmark,
  FaRoute,
  FaMapMarkedAlt,
  FaUtensils,
  FaLanguage,
  FaCamera,
  FaBrain,
  FaCompass,
  FaStar,
  FaRocket,
  FaGlobe,
  FaCheckCircle,
} from "react-icons/fa";
import {
  SiReact,
  SiFastapi,
  SiGooglegemini,
  SiOpenstreetmap,
} from "react-icons/si";

const NAV_LINKS = [
  { label: "Home", to: "/" },
  { label: "Monument Recognition", to: "/monument" },
  { label: "Trip Planner", to: "/trip-planner" },
  { label: "Food Explorer", to: "/food" },
  { label: "Language Learning", to: "/language" },
];

const FEATURES = [
  {
    icon: <FaCamera size={28} />,
    title: "AI Monument Recognition",
    description:
      "Upload a monument image and instantly receive heritage information, architecture details, historical significance, and local insights.",
    accent: "#2563eb",
  },
  {
    icon: <FaRoute size={28} />,
    title: "Smart Trip Planner",
    description:
      "Generate optimized heritage itineraries using AI-based time-of-day recommendations and route planning.",
    accent: "#7c3aed",
  },
  {
    icon: <FaMapMarkedAlt size={28} />,
    title: "Route Optimization & Mapping",
    description:
      "Visualize optimized travel routes on an interactive map with travel-time estimates and road-based navigation.",
    accent: "#0891b2",
  },
  {
    icon: <FaUtensils size={28} />,
    title: "Local Food Explorer",
    description:
      "Discover authentic local food experiences near heritage destinations.",
    accent: "#d97706",
  },
  {
    icon: <FaLanguage size={28} />,
    title: "Language Learning Assistant",
    description:
      "Learn essential local phrases and cultural expressions to improve communication while traveling.",
    accent: "#059669",
  },
];

const STEPS = [
  { icon: <FaCamera size={22} />, label: "Upload Monument", step: "01" },
  { icon: <FaBrain size={22} />, label: "Understand Heritage", step: "02" },
  { icon: <FaCompass size={22} />, label: "Plan Journey", step: "03" },
  { icon: <FaUtensils size={22} />, label: "Explore Local Food", step: "04" },
  { icon: <FaLanguage size={22} />, label: "Learn Local Language", step: "05" },
];

const USPS = [
  {
    icon: <FaBrain size={32} />,
    title: "AI Powered Heritage Discovery",
    description:
      "Leverage the latest generative AI to surface deep cultural context, architectural detail, and historical narratives for any monument worldwide — instantly.",
    color: "#2563eb",
  },
  {
    icon: <FaRoute size={32} />,
    title: "Smart Route Optimization",
    description:
      "OSRM-powered routing combined with AI scheduling recommendations ensures you visit the right places at the right time, minimizing travel and maximizing experience.",
    color: "#7c3aed",
  },
  {
    icon: <FaGlobe size={32} />,
    title: "Complete Cultural Travel Experience",
    description:
      "From monument identification to curated local food trails and language learning — HeritageQuest is the only companion you need for authentic cultural travel.",
    color: "#059669",
  },
];

const TECH_STACK = [
  { icon: <SiReact size={18} />, label: "React" },
  { icon: <SiFastapi size={18} />, label: "FastAPI" },
  { icon: <SiGooglegemini size={18} />, label: "Gemini AI" },
  { icon: <SiOpenstreetmap size={18} />, label: "OpenStreetMap" },
  { icon: <FaRoute size={18} />, label: "OSRM" },
];

export default function HomePage() {
  return (
    <div style={{ background: "#0f172a", minHeight: "100vh", color: "#fff", fontFamily: "'Inter', 'Segoe UI', sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        * { box-sizing: border-box; margin: 0; padding: 0; }

        .hq-nav-link {
          color: #9ca3af;
          text-decoration: none;
          font-size: 14px;
          font-weight: 500;
          padding: 6px 4px;
          transition: color 0.2s;
          white-space: nowrap;
        }
        .hq-nav-link:hover { color: #fff; }

        .hq-btn-primary {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: #2563eb;
          color: #fff;
          border: none;
          border-radius: 10px;
          padding: 14px 28px;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          text-decoration: none;
          transition: background 0.2s, transform 0.15s;
        }
        .hq-btn-primary:hover { background: #1d4ed8; transform: translateY(-1px); }

        .hq-btn-outline {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: transparent;
          color: #fff;
          border: 1.5px solid #374151;
          border-radius: 10px;
          padding: 14px 28px;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          text-decoration: none;
          transition: border-color 0.2s, background 0.2s, transform 0.15s;
        }
        .hq-btn-outline:hover { border-color: #6b7280; background: rgba(255,255,255,0.04); transform: translateY(-1px); }

        .hq-feature-card {
          background: #111827;
          border: 1px solid #374151;
          border-radius: 16px;
          padding: 28px 24px;
          transition: transform 0.25s, border-color 0.25s, box-shadow 0.25s;
          cursor: default;
        }
        .hq-feature-card:hover {
          transform: translateY(-6px);
          border-color: #4b5563;
          box-shadow: 0 16px 40px rgba(0,0,0,0.4);
        }

        .hq-step-card {
          background: #111827;
          border: 1px solid #374151;
          border-radius: 16px;
          padding: 24px 16px;
          text-align: center;
          flex: 1;
          min-width: 120px;
          transition: transform 0.22s, border-color 0.22s;
        }
        .hq-step-card:hover {
          transform: translateY(-4px);
          border-color: #2563eb;
        }

        .hq-usp-card {
          background: #111827;
          border: 1px solid #374151;
          border-radius: 16px;
          padding: 32px 28px;
          transition: transform 0.25s, border-color 0.25s, box-shadow 0.25s;
        }
        .hq-usp-card:hover {
          transform: translateY(-5px);
          border-color: #4b5563;
          box-shadow: 0 12px 32px rgba(0,0,0,0.35);
        }

        .hq-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: rgba(37, 99, 235, 0.12);
          border: 1px solid rgba(37, 99, 235, 0.35);
          color: #60a5fa;
          border-radius: 999px;
          padding: 6px 14px;
          font-size: 13px;
          font-weight: 500;
          margin-bottom: 24px;
        }

        .hq-step-connector {
          flex-shrink: 0;
          width: 36px;
          height: 2px;
          background: linear-gradient(90deg, #2563eb44, #374151);
          align-self: center;
          margin-top: -24px;
        }

        @media (max-width: 768px) {
          .hq-nav-desktop { display: none !important; }
          .hq-steps-row { flex-direction: column !important; align-items: center; }
          .hq-step-connector { width: 2px; height: 24px; margin-top: 0; background: linear-gradient(180deg, #2563eb44, #374151); }
          .hq-hero-title { font-size: 36px !important; }
          .hq-section-title { font-size: 26px !important; }
          .hq-features-grid { grid-template-columns: 1fr !important; }
          .hq-usps-grid { grid-template-columns: 1fr !important; }
          .hq-footer-inner { flex-direction: column !important; gap: 24px !important; align-items: center; text-align: center; }
          .hq-hero-btns { flex-direction: column; align-items: center; }
        }

        @media (max-width: 480px) {
          .hq-hero-title { font-size: 28px !important; }
        }
      `}</style>

      {/* ── Navbar ── */}
      <nav style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        background: "rgba(15, 23, 42, 0.85)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid #1e293b",
        padding: "0 24px",
        height: "64px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
      }}>
        <Link to="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
          <span style={{ fontSize: 22 }}>🏛</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: "#fff", letterSpacing: "-0.3px" }}>
            HeritageQuest AI
          </span>
        </Link>
        <div className="hq-nav-desktop" style={{ display: "flex", alignItems: "center", gap: 24 }}>
          {NAV_LINKS.map((l) => (
            <Link key={l.to} to={l.to} className="hq-nav-link">{l.label}</Link>
          ))}
        </div>
      </nav>

      {/* ── Hero ── */}
      <section style={{
        paddingTop: "140px",
        paddingBottom: "100px",
        paddingLeft: "24px",
        paddingRight: "24px",
        textAlign: "center",
        maxWidth: 780,
        margin: "0 auto",
      }}>
        <div className="hq-badge">
          <FaStar size={12} />
          AI-Powered Cultural Travel Companion
        </div>

        <h1
          className="hq-hero-title"
          style={{
            fontSize: 56,
            fontWeight: 800,
            lineHeight: 1.1,
            letterSpacing: "-1.5px",
            marginBottom: 20,
            background: "linear-gradient(135deg, #fff 40%, #60a5fa 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          HeritageQuest AI
        </h1>

        <p style={{ fontSize: 22, fontWeight: 600, color: "#60a5fa", marginBottom: 18, letterSpacing: "-0.3px" }}>
          Discover Heritage. Plan Smart. Travel Local.
        </p>

        <p style={{ fontSize: 16, color: "#9ca3af", lineHeight: 1.75, marginBottom: 40, maxWidth: 600, margin: "0 auto 40px" }}>
          An AI-powered cultural travel companion that helps travelers identify monuments, optimize heritage routes, discover local food experiences, and learn regional languages.
        </p>

        <div className="hq-hero-btns" style={{ display: "flex", gap: 16, justifyContent: "center", flexWrap: "wrap" }}>
          <Link to="/monument" className="hq-btn-primary">
            <FaRocket size={15} /> Get Started
          </Link>
          <a href="#features" className="hq-btn-outline">
            <FaCompass size={15} /> Explore Features
          </a>
        </div>

        {/* Stat pills */}
        <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap", marginTop: 52 }}>
          {["5 AI Features", "Real-time Routes", "50+ Languages", "Local Food Discovery"].map((s) => (
            <span key={s} style={{
              background: "#111827",
              border: "1px solid #374151",
              borderRadius: 999,
              padding: "7px 16px",
              fontSize: 13,
              color: "#9ca3af",
            }}>
              <FaCheckCircle size={11} style={{ color: "#2563eb", marginRight: 6, verticalAlign: "middle" }} />
              {s}
            </span>
          ))}
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" style={{ padding: "80px 24px", maxWidth: 1120, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 52 }}>
          <p style={{ color: "#2563eb", fontSize: 13, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12 }}>
            Platform Features
          </p>
          <h2 className="hq-section-title" style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.8px", marginBottom: 14 }}>
            Everything You Need to Travel Smarter
          </h2>
          <p style={{ color: "#9ca3af", fontSize: 16, maxWidth: 520, margin: "0 auto" }}>
            Five powerful AI capabilities, unified in a single travel platform.
          </p>
        </div>

        <div
          className="hq-features-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            gap: 20,
          }}
        >
          {FEATURES.map((f) => (
            <div key={f.title} className="hq-feature-card">
              <div style={{
                width: 52,
                height: 52,
                borderRadius: 12,
                background: `${f.accent}18`,
                border: `1px solid ${f.accent}33`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: f.accent,
                marginBottom: 18,
              }}>
                {f.icon}
              </div>
              <h3 style={{ fontSize: 17, fontWeight: 700, marginBottom: 10, color: "#fff" }}>{f.title}</h3>
              <p style={{ fontSize: 14, color: "#9ca3af", lineHeight: 1.7 }}>{f.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How It Works ── */}
      <section style={{ padding: "80px 24px", background: "#080f1e" }}>
        <div style={{ maxWidth: 1120, margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: 52 }}>
            <p style={{ color: "#2563eb", fontSize: 13, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12 }}>
              How It Works
            </p>
            <h2 className="hq-section-title" style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.8px", marginBottom: 14 }}>
              Your Journey in Five Steps
            </h2>
            <p style={{ color: "#9ca3af", fontSize: 16 }}>
              From monument to memory — the complete cultural travel loop.
            </p>
          </div>

          <div
            className="hq-steps-row"
            style={{ display: "flex", alignItems: "stretch", gap: 0 }}
          >
            {STEPS.map((s, i) => (
              <>
                <div key={s.step} className="hq-step-card">
                  <div style={{
                    width: 48,
                    height: 48,
                    borderRadius: "50%",
                    background: "rgba(37,99,235,0.15)",
                    border: "1px solid rgba(37,99,235,0.35)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#60a5fa",
                    margin: "0 auto 14px",
                  }}>
                    {s.icon}
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#2563eb", letterSpacing: "0.1em", marginBottom: 6 }}>
                    STEP {s.step}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", lineHeight: 1.4 }}>{s.label}</div>
                </div>
                {i < STEPS.length - 1 && (
                  <div key={`conn-${i}`} className="hq-step-connector" />
                )}
              </>
            ))}
          </div>
        </div>
      </section>

      {/* ── Why HeritageQuest ── */}
      <section style={{ padding: "80px 24px", maxWidth: 1120, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 52 }}>
          <p style={{ color: "#2563eb", fontSize: 13, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12 }}>
            Why HeritageQuest AI
          </p>
          <h2 className="hq-section-title" style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.8px", marginBottom: 14 }}>
            Built for the Curious Traveler
          </h2>
          <p style={{ color: "#9ca3af", fontSize: 16, maxWidth: 500, margin: "0 auto" }}>
            Three pillars that set HeritageQuest apart from every other travel app.
          </p>
        </div>

        <div
          className="hq-usps-grid"
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 24 }}
        >
          {USPS.map((u) => (
            <div key={u.title} className="hq-usp-card">
              <div style={{
                width: 60,
                height: 60,
                borderRadius: 14,
                background: `${u.color}14`,
                border: `1px solid ${u.color}30`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: u.color,
                marginBottom: 22,
              }}>
                {u.icon}
              </div>
              <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: "#fff" }}>{u.title}</h3>
              <p style={{ fontSize: 14, color: "#9ca3af", lineHeight: 1.75 }}>{u.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA Banner ── */}
      <section style={{ padding: "0 24px 80px", maxWidth: 1120, margin: "0 auto" }}>
        <div style={{
          background: "linear-gradient(135deg, #1e3a8a 0%, #1e1b4b 100%)",
          border: "1px solid #3730a3",
          borderRadius: 20,
          padding: "52px 40px",
          textAlign: "center",
        }}>
          <h2 style={{ fontSize: 32, fontWeight: 800, marginBottom: 14, letterSpacing: "-0.5px" }}>
            Ready to Explore Heritage?
          </h2>
          <p style={{ color: "#a5b4fc", fontSize: 16, marginBottom: 32, maxWidth: 440, margin: "0 auto 32px" }}>
            Start your AI-powered cultural journey today — upload a monument photo and let HeritageQuest do the rest.
          </p>
          <Link to="/monument" className="hq-btn-primary" style={{ background: "#fff", color: "#1e1b4b" }}>
            <FaCamera size={15} /> Try Monument Recognition
          </Link>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer style={{
        background: "#080f1e",
        borderTop: "1px solid #1e293b",
        padding: "40px 24px",
      }}>
        <div
          className="hq-footer-inner"
          style={{
            maxWidth: 1120,
            margin: "0 auto",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: 32,
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 22 }}>🏛</span>
              <span style={{ fontSize: 17, fontWeight: 700 }}>HeritageQuest AI</span>
            </div>
            <p style={{ color: "#6b7280", fontSize: 13 }}>Hackathon Project 2026</p>
          </div>

          <div>
            <p style={{ color: "#6b7280", fontSize: 12, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 14 }}>
              Powered By
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
              {TECH_STACK.map((t) => (
                <span key={t.label} style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  background: "#111827",
                  border: "1px solid #374151",
                  borderRadius: 8,
                  padding: "6px 12px",
                  fontSize: 13,
                  color: "#9ca3af",
                }}>
                  {t.icon} {t.label}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div style={{
          maxWidth: 1120,
          margin: "28px auto 0",
          paddingTop: 20,
          borderTop: "1px solid #1e293b",
          textAlign: "center",
          color: "#4b5563",
          fontSize: 13,
        }}>
          © 2026 HeritageQuest AI · Built with ❤️ for cultural discovery
        </div>
      </footer>
    </div>
  );
}