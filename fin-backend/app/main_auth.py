"""ASGI entry with cookie sessions + `/v1/auth/*` (use while the auth slice is in progress)."""

from app.factory import create_app

app = create_app(enable_auth=True)
