import { useState } from "react";
import axios from "axios";
import Navbar from "../components/Navbar";
import {
  FaMapMarkerAlt,
  FaGlobe,
  FaLanguage,
  FaLandmark,
  FaCalendarAlt,
  FaInfoCircle,
  FaLightbulb,
  FaVolumeUp,
  FaUniversity,
} from "react-icons/fa";

function App() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [monumentData, setMonumentData] = useState(null);
  const [error, setError] = useState("");

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];

    if (!selectedFile) return;

    setFile(selectedFile);
    setPreview(URL.createObjectURL(selectedFile));
    setMonumentData(null);
    setError("");
  };

  const handleUpload = async () => {
    if (!file) {
      alert("Please select an image first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setLoading(true);
      setError("");

      const response = await axios.post(
        "https://heritagequestai.onrender.com/upload",
        formData
      );

      if (response.data.error) {
        setError(response.data.error);
        return;
      }

      setMonumentData(response.data);
    } catch (err) {
      console.error(err);
      setError("Failed to analyze monument.");
    } finally {
      setLoading(false);
    }
  };

  const speakEnglish = () => {
    if (!monumentData) return;

    const text = `
      Historical Significance:
      ${monumentData.historical_significance}

      Interesting Fact:
      ${monumentData.interesting_fact}
    `;

    const utterance = new SpeechSynthesisUtterance(text);

    utterance.lang = "en-US";
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;

    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  };

  const speakLocalLanguage = () => {
    if (!monumentData) return;

    const text = `
      Historical Significance:
      ${monumentData.historical_significance}

      Interesting Fact:
      ${monumentData.interesting_fact}
    `;

    const utterance = new SpeechSynthesisUtterance(text);

    switch (monumentData.local_language?.toLowerCase()) {
      case "telugu":
        utterance.lang = "te-IN";
        break;

      case "hindi":
        utterance.lang = "hi-IN";
        break;

      case "tamil":
        utterance.lang = "ta-IN";
        break;

      case "kannada":
        utterance.lang = "kn-IN";
        break;

      case "malayalam":
        utterance.lang = "ml-IN";
        break;

      case "marathi":
        utterance.lang = "mr-IN";
        break;

      case "bengali":
        utterance.lang = "bn-IN";
        break;

      default:
        utterance.lang = "en-US";
    }

    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;

    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  };

  return (
    <>
      <Navbar />

      <div
        style={{
          maxWidth: "1200px",
          margin: "40px auto",
          padding: "20px",
          fontFamily: "Arial, sans-serif",
          color: "white",
        }}
      >
        <h1
          style={{
            textAlign: "center",
            marginBottom: "10px",
          }}
        >
          <FaUniversity
            style={{
              marginRight: "10px",
              verticalAlign: "middle",
            }}
          />
          HeritageQuest AI
        </h1>

        <p
          style={{
            textAlign: "center",
            color: "#9ca3af",
          }}
        >
          Upload a monument image and discover its heritage.
        </p>

        <div
          style={{
            marginTop: "20px",
            textAlign: "center",
          }}
        >
          <input
            type="file"
            accept="image/*"
            onChange={handleFileChange}
          />
        </div>

        <div
          style={{
            marginTop: "20px",
            textAlign: "center",
          }}
        >
          <button
            onClick={handleUpload}
            disabled={loading}
            style={{
              padding: "12px 24px",
              borderRadius: "10px",
              border: "none",
              backgroundColor: "#2563eb",
              color: "white",
              cursor: "pointer",
              fontSize: "16px",
            }}
          >
            {loading ? "Analyzing..." : "Identify Monument"}
          </button>
        </div>

        {error && (
          <div
            style={{
              marginTop: "20px",
              textAlign: "center",
              color: "#ef4444",
            }}
          >
            {error}
          </div>
        )}

        {monumentData && (
          <div
            style={{
              marginTop: "40px",
              display: "flex",
              flexDirection: "column",
              gap: "20px",
            }}
          >
            {/* TOP CARD */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "320px 1fr",
                gap: "20px",
              }}
            >
              {/* IMAGE CARD */}
              <div
                style={{
                  background: "#111827",
                  border: "1px solid #374151",
                  borderRadius: "16px",
                  padding: "15px",
                  minHeight: "350px",
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                }}
              >
                <img
                  src={preview}
                  alt="Monument"
                  style={{
                    width: "100%",
                    height: "300px",
                    objectFit: "contain",
                    borderRadius: "12px",
                  }}
                />
              </div>

              {/* DETAILS CARD */}
              <div
                style={{
                  background: "#111827",
                  border: "1px solid #374151",
                  borderRadius: "16px",
                  padding: "24px",
                }}
              >
                <h2
                  style={{
                    marginBottom: "25px",
                    fontSize: "28px",
                  }}
                >
                  {monumentData.monument}
                </h2>

                <div
                  style={{
                    display: "grid",
                    gap: "15px",
                  }}
                >
                  <div>
                    <FaMapMarkerAlt
                      style={{
                        marginRight: "10px",
                        color: "#ef4444",
                      }}
                    />
                    {monumentData.location}
                  </div>

                  <div>
                    <FaGlobe
                      style={{
                        marginRight: "10px",
                        color: "#3b82f6",
                      }}
                    />
                    {monumentData.country}
                  </div>

                  <div>
                    <FaLanguage
                      style={{
                        marginRight: "10px",
                        color: "#10b981",
                      }}
                    />
                    {monumentData.local_language}
                  </div>

                  <hr
                    style={{
                      borderColor: "#374151",
                    }}
                  />

                  <div>
                    <FaLandmark
                      style={{
                        marginRight: "10px",
                        color: "#f59e0b",
                      }}
                    />
                    {monumentData.architecture_style}
                  </div>

                  <div>
                    <FaCalendarAlt
                      style={{
                        marginRight: "10px",
                        color: "#8b5cf6",
                      }}
                    />
                    {monumentData.construction_year}
                  </div>
                </div>
              </div>
            </div>

            {/* HISTORICAL SIGNIFICANCE */}
            <div
              style={{
                background: "#111827",
                border: "1px solid #374151",
                borderRadius: "16px",
                padding: "24px",
              }}
            >
              <h3
                style={{
                  marginBottom: "15px",
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                }}
              >
                <FaInfoCircle />
                Historical Significance
              </h3>

              <p
                style={{
                  lineHeight: "1.8",
                  color: "#d1d5db",
                }}
              >
                {monumentData.historical_significance}
              </p>
            </div>

            {/* INTERESTING FACT */}
            <div
              style={{
                background: "#111827",
                border: "1px solid #374151",
                borderRadius: "16px",
                padding: "24px",
              }}
            >
              <h3
                style={{
                  marginBottom: "15px",
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                }}
              >
                <FaLightbulb />
                Interesting Fact
              </h3>

              <p
                style={{
                  lineHeight: "1.8",
                  color: "#d1d5db",
                }}
              >
                {monumentData.interesting_fact}
              </p>
            </div>

            {/* AUDIO GUIDE */}
            <div
              style={{
                background: "#111827",
                border: "1px solid #374151",
                borderRadius: "16px",
                padding: "24px",
              }}
            >
              <h3
                style={{
                  marginBottom: "20px",
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                }}
              >
                <FaVolumeUp />
                Audio Guide
              </h3>

              <div
                style={{
                  display: "flex",
                  gap: "15px",
                  flexWrap: "wrap",
                }}
              >
                <button
                  onClick={speakEnglish}
                  style={{
                    padding: "12px 20px",
                    borderRadius: "10px",
                    border: "none",
                    backgroundColor: "#2563eb",
                    color: "white",
                    cursor: "pointer",
                  }}
                >
                  <FaVolumeUp
                    style={{
                      marginRight: "8px",
                    }}
                  />
                  Listen in English
                </button>

                <button
                  onClick={speakLocalLanguage}
                  style={{
                    padding: "12px 20px",
                    borderRadius: "10px",
                    border: "none",
                    backgroundColor: "#10b981",
                    color: "white",
                    cursor: "pointer",
                  }}
                >
                  <FaVolumeUp
                    style={{
                      marginRight: "8px",
                    }}
                  />
                  Listen in {monumentData.local_language}
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </>
  );
}

export default App;