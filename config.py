import os
from pathlib import Path
from dotenv import load_dotenv

basedir = Path(__file__).parent.resolve()
load_dotenv(basedir / ".env")
database_url = os.environ.get("DATABASE_URL", f"sqlite:///{basedir / 'database' / 'processpulse.db'}")
if database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url[len("postgres://"):]


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "dev-agent-token-change-in-production")
    DEVICE_REGISTRATION_TOKEN = os.environ.get(
        "DEVICE_REGISTRATION_TOKEN", "dev-registration-token-change-in-production"
    )
    DEVICE_ADMIN_TOKEN = os.environ.get(
        "DEVICE_ADMIN_TOKEN", "dev-admin-token-change-in-production"
    )
    ALLOW_LEGACY_AGENT_TOKEN = os.environ.get(
        "ALLOW_LEGACY_AGENT_TOKEN", "1" if os.environ.get("FLASK_ENV", "development") != "production" else "0"
    ) == "1"
    HEARTBEAT_TIMEOUT_SECONDS = int(os.environ.get("HEARTBEAT_TIMEOUT_SECONDS", "30"))
    AGENT_INTERVAL = int(os.environ.get("AGENT_INTERVAL", "5"))
    API_ENDPOINT = os.environ.get("API_ENDPOINT", "http://localhost:5000")

    ML_MODEL_PATH = os.environ.get("ML_MODEL_PATH", str(basedir / "backend" / "ml" / "models" / "anomaly_detector.joblib"))
    ML_CONTAMINATION = float(os.environ.get("ML_CONTAMINATION", "0.1"))
    ML_N_ESTIMATORS = int(os.environ.get("ML_N_ESTIMATORS", "100"))

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE", str(basedir / "logs" / "processpulse.log"))

    RATE_LIMIT_DEFAULT = os.environ.get("RATE_LIMIT_DEFAULT", "200 per minute")
    RATE_LIMIT_AGENT = os.environ.get("RATE_LIMIT_AGENT", "60 per minute")

    DATA_RETENTION_DAYS = int(os.environ.get("DATA_RETENTION_DAYS", "30"))

    CORS_ORIGINS = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000").split(",")]

    BACKEND_HOST = os.environ.get("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "5000"))

    CRITICAL_PROCESSES = {
        "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
        "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
        "dwm.exe", "taskhostw.exe", "explorer.exe", "winlogon.exe",
        "spoolsv.exe", "searchindexer.exe", "sihost.exe", "taskhost.exe"
    }


class DevelopmentConfig(Config):
    FLASK_DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    FLASK_DEBUG = False
    SQLALCHEMY_ECHO = False
    DEVICE_ADMIN_TOKEN = os.environ.get("DEVICE_ADMIN_TOKEN", "")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    FLASK_DEBUG = True
    DEVICE_REGISTRATION_TOKEN = "test-registration-token"
    DEVICE_ADMIN_TOKEN = "test-admin-token"


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}