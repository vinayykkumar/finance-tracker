"""ASGI entry: `/v1` health only (no session middleware, no `/v1/auth`)."""

from app.factory import create_app

app = create_app(enable_auth=False)
