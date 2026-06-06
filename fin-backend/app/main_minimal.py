"""Minimal ASGI entry: `/v1/health` only (no session, no financial routes)."""

from app.factory import create_app

app = create_app(enable_auth=False)
