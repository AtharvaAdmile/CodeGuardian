#!/usr/bin/env python3
"""
Entry-point script to launch the CodeGuardian FastAPI server.

Usage:
    python run.py
    python run.py --host 127.0.0.1 --port 9000
"""

import argparse
import uvicorn

from server.config import get_settings


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Run the CodeGuardian API server")
    parser.add_argument("--host", default=settings.server_host, help="Bind host")
    parser.add_argument("--port", type=int, default=settings.server_port, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    uvicorn.run(
        "server.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
