"""Dump the FastAPI OpenAPI schema to backend/openapi.json.

The frontend's typed client (orval -> TanStack Query hooks + TS types) is generated
from this file. It is the single source of truth for the FE/BE contract: regenerate
after any response_model change, and CI fails if the checked-in client drifts.

Run: uv run python -m app.export_openapi
"""

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> None:
    OUT.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(app.openapi()['paths'])} paths)")


if __name__ == "__main__":
    main()
