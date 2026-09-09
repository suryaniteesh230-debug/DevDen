from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
ML_DIR = BACKEND_DIR / "ml"
CLINICAL_KNOWLEDGE_DIR = BACKEND_DIR / "clinical_knowledge"


class Settings(BaseSettings):
    app_name: str = "NextCare Clinical API"
    environment: str = "development"
    database_url: str = Field(
        default=f"sqlite:///{BACKEND_DIR / 'neurobots.db'}",
        validation_alias=AliasChoices("NEUROBOTS_DATABASE_URL", "DATABASE_URL"),
    )
    auth_secret_key: SecretStr = SecretStr("")
    auth_access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    heart_attack_model_path: str = str(
        ML_DIR / "artifacts" / "cardiac_risk_random_forest_v1.0.0.joblib"
    )
    cardiac_feature_schema_path: str = str(ML_DIR / "feature_schema.json")
    gemini_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    gemini_model: str = Field(
        default="gemini-3.6-flash", validation_alias="GEMINI_MODEL"
    )
    gemini_max_retries: int = Field(
        default=2, ge=0, le=5, validation_alias="GEMINI_MAX_RETRIES"
    )
    gemini_max_output_tokens: int = Field(
        default=4096,
        ge=512,
        le=65_536,
        validation_alias="GEMINI_MAX_OUTPUT_TOKENS",
    )
    gemini_thinking_budget: int = Field(
        default=0, ge=-1, le=32_768, validation_alias="GEMINI_THINKING_BUDGET"
    )
    clinical_corpus_path: str = str(CLINICAL_KNOWLEDGE_DIR / "corpus.json")
    clinical_vector_index_path: str = str(
        CLINICAL_KNOWLEDGE_DIR / "index" / "clinical_hashing_v1.npz"
    )
    medical_knowledge_graph_path: str = str(
        CLINICAL_KNOWLEDGE_DIR / "medical_knowledge_graph.json"
    )
    clinical_reasoning_max_steps: int = 6
    clinical_reasoning_max_tool_calls: int = 5
    clinical_reasoning_timeout_seconds: float = 45.0
    document_upload_max_bytes: int = 10 * 1024 * 1024
    ocr_timeout_seconds: float = 30.0
    ocr_max_pdf_pages: int = 5
    tesseract_command: str = "tesseract"
    pdftoppm_command: str = "pdftoppm"
    speech_upload_max_bytes: int = 20 * 1024 * 1024
    speech_timeout_seconds: float = 45.0
    gemini_speech_model: str = Field(
        default="gemini-3.6-flash", validation_alias="GEMINI_SPEECH_MODEL"
    )
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_prefix="NEUROBOTS_",
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def select_psycopg_driver(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @model_validator(mode="after")
    def require_hosted_database_in_production(self) -> "Settings":
        if self.environment.casefold() == "production" and self.database_url.startswith(
            "sqlite"
        ):
            raise ValueError(
                "production deployments must set NEUROBOTS_DATABASE_URL to a hosted Postgres URL"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
