"""API key obligatoria fuera de desarrollo, sin SQL ni contrasenas publicadas."""
from __future__ import annotations
import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


class ApiKeyPermission(BasePermission):
    message = "Se requiere una API key valida en X-API-Key."

    def has_permission(self, request, view):
        if getattr(view, "allow_public_health", False):
            return True
        configured = settings.VIBRATIONS_API_KEY
        if not configured:
            return bool(settings.DEBUG)  # Solo desarrollo local
        supplied = request.headers.get("X-API-Key", "")
        return bool(supplied) and secrets.compare_digest(supplied, configured)
