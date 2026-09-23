import os
from pydantic import BaseModel, Field
from typing import Optional

class Settings(BaseModel):
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    secret_key: str = Field(default_factory=lambda: os.getenv("SECRET_KEY", "relay-insecure-dev-secret-change-in-prod"))
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./relay.db"))
    model_provider: str = Field(default_factory=lambda: os.getenv("MODEL_PROVIDER", "deterministic_fake"))
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    enable_demo_mode: bool = Field(default_factory=lambda: os.getenv("ENABLE_DEMO_MODE", "true").lower() == "true")
    session_cookie_name: str = "relay_session"
    session_expire_hours: int = 24
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    def validate_security(self):
        if self.app_env == "production":
            if self.secret_key == "relay-insecure-dev-secret-change-in-prod" or len(self.secret_key) < 32:
                raise ValueError("In production, SECRET_KEY must be a secure random string of at least 32 characters.")
            if self.enable_demo_mode:
                raise ValueError("ENABLE_DEMO_MODE must be false in production.")

settings = Settings()
settings.validate_security()
