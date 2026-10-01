"""
Configuration management for the Face Recognition Attendance System.
Supports environment-based configuration (development, testing, production).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory
BASE_DIR = Path(__file__).parent.resolve()

# Supported environments
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()


class Config:
    """Base configuration - shared across all environments."""

    # Flask settings
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = False
    TESTING = False

    # Database settings
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # Session settings
    PERMANENT_SESSION_LIFETIME = 7 * 24 * 60 * 60  # 7 days
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Face recognition settings
    RECOGNITION_THRESHOLD = 0.55  # Cosine similarity threshold
    COOLDOWN_SECONDS = 10  # Prevent duplicate attendance within session
    FACES_DATA_DIR = str(BASE_DIR / "ImagesAttendance")
    MAX_UPLOAD_SIZE_MB = 5  # Max size for face image upload

    # Attendance settings
    ATTENDANCE_ALERT_THRESHOLD = 75  # Percentage below which alerts are sent

    # File upload settings
    ALLOWED_FACE_EXTENSIONS = {"jpg", "jpeg", "png"}

    # AI Chatbot settings
    AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
    AI_MODEL = os.getenv("AI_MODEL", "gemini-1.5-flash").strip()
    AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip()
    AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    CHAT_RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT", "30"))  # Max requests per minute


class DevelopmentConfig(Config):
    """Development environment configuration."""

    DEBUG = True
    SQLALCHEMY_ECHO = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR}/attendance_system.db"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 30}
    }
    SESSION_COOKIE_SECURE = False


class TestingConfig(Config):
    """Testing environment configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"  # In-memory database for testing
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing


class ProductionConfig(Config):
    """Production environment configuration."""

    DEBUG = False
    SQLALCHEMY_ECHO = False

    # In production, DATABASE_URL must be set via environment variable
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost/attendance_system",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_timeout": 30,
    }

    # Enforce HTTPS and secure cookies
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True


# Configuration dictionary
config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

# Get the appropriate configuration
config = config_map.get(ENVIRONMENT, DevelopmentConfig)
