import { FaLanguage } from "react-icons/fa";

function LanguageLearning() {
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
        <FaLanguage
          size={70}
          color="#2563eb"
        />

        <h1
          style={{
            marginTop: "20px",
            fontSize: "3rem",
          }}
        >
          Heritage Language Learning
        </h1>

        <p
          style={{
            color: "#9ca3af",
            fontSize: "18px",
            marginTop: "10px",
          }}
        >
          Learn local phrases and cultural expressions
          before visiting heritage destinations.
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
          <h2>🚧 Coming Soon</h2>

          <p
            style={{
              marginTop: "20px",
              color: "#d1d5db",
              lineHeight: "1.8",
            }}
          >
            This feature will help travelers learn
            essential local phrases, greetings,
            and cultural expressions specific to
            the heritage destination they are visiting.
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
              lineHeight: "1.8",
            }}
          >
            <li>
              Local greetings and introductions
            </li>

            <li>
              Essential travel phrases
            </li>

            <li>
              AI-powered pronunciation assistance
            </li>

            <li>
              Cultural etiquette tips
            </li>

            <li>
              Audio learning modules
            </li>

            <li>
              Heritage-specific vocabulary
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default LanguageLearning;