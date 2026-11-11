"""Configuracion segura por defecto. La tabla del proceso vive en SQL Server externo."""
from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def csv_env(name: str) -> list[str]:
    return [p.strip() for p in os.getenv(name, "").split(",") if p.strip()]


DEBUG = flag("DJANGO_DEBUG", False)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "solo-desarrollo-no-usar-en-produccion"
    else:
        raise ImproperlyConfigured("Definir DJANGO_SECRET_KEY en .env")

ALLOWED_HOSTS = csv_env("DJANGO_ALLOWED_HOSTS") or ["localhost", "127.0.0.1"]
CORS_ALLOWED_ORIGINS = csv_env("CORS_ALLOWED_ORIGINS")
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "America/Mexico_City")
USE_TZ = True
LANGUAGE_CODE = "es-mx"

INSTALLED_APPS = [
    "rest_framework",
    "corsheaders",
    "vibraciones",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
# La API no crea tablas Django; consulta SQL Server existente mediante pyodbc.
# No ejecutar 'manage.py migrate': la DDL del proyecto fue aplicada desde SSMS.
DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["vibraciones.permissions.ApiKeyPermission"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
}

VIBRATIONS_API_KEY = os.getenv("VIBRATIONS_API_KEY", "").strip()
VIBRATIONS_MODEL_DIR = Path(os.getenv("VIBRATIONS_MODEL_DIR", "artifacts"))
if not VIBRATIONS_MODEL_DIR.is_absolute():
    VIBRATIONS_MODEL_DIR = BASE_DIR / VIBRATIONS_MODEL_DIR
VIBRATIONS_MIN_RPM = float(os.getenv("VIBRATIONS_MIN_RPM", "300"))
VIBRATIONS_SCORE_WARNING = float(os.getenv("VIBRATIONS_SCORE_WARNING", "60"))
VIBRATIONS_SCORE_ALERT = float(os.getenv("VIBRATIONS_SCORE_ALERT", "85"))
VIBRATIONS_MIN_TRAIN_SAMPLES = int(os.getenv("VIBRATIONS_MIN_TRAIN_SAMPLES", "300"))
VIBRATIONS_MIN_TRAIN_MINUTES = float(os.getenv("VIBRATIONS_MIN_TRAIN_MINUTES", "15"))

# El demo usa HTTP local en desarrollo. Implementar HTTPS en proxy inverso en produccion.
VIBRATIONS_USE_VFD_CONTEXT = flag("VIBRATIONS_USE_VFD_CONTEXT", True)

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"vibraciones": {"handlers": ["console"], "level": "INFO"}},
}
