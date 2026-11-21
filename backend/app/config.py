import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _project_path(value: str) -> str:
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else BASE_DIR / path)


class Settings:
    mongodb_uri = os.getenv("MONGODB_URI", "")
    db_name = os.getenv("DB_NAME", "astra")
    jwt_secret = os.getenv("JWT_SECRET", "dev-secret")

    model_path = _project_path(
        os.getenv("MODEL_PATH", "models/ASTRA_YOLO11s_FINAL_9833_best.pt")
    )

    admin_email = os.getenv("ADMIN_EMAIL", "admin@astra.ai")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

    results_dir = _project_path(os.getenv("RESULTS_DIR", "storage/results"))
    live_feed_urls = {
        approach: os.getenv(f"LIVE_FEED_URL_{approach.upper()}", "").strip()
        for approach in ("north", "south", "east", "west")
    }
    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]
    token_hours = 12


settings = Settings()