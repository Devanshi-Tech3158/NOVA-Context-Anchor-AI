"""Nova Context Anchor API entrypoint and runner."""

import os

import uvicorn

from nova.api.main import app, create_app

__all__ = ["app", "create_app"]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("nova.api.main:app", host=host, port=port, reload=False)
