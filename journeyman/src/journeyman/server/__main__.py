"""Entrypoint: `python -m journeyman.server` (PORT default 8787 to match Vite)."""

from __future__ import annotations

import os

import uvicorn

from journeyman.spend import load_local_env


def main() -> None:
    load_local_env()
    port = int(os.environ.get("PORT", "8787"))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(
        "journeyman.server.app:app",
        host=host,
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
