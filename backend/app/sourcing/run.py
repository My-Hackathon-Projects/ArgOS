"""Manual discovery smoke-run — invokes the graph, prints stats, writes the delivery JSON.

No DB writes here (persist is wired separately). Traces to LangSmith when enabled.
Run: uv run python -m app.sourcing.run
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.sourcing.graph import build_discovery_graph
from app.sourcing.thesis import DEFAULT_THESIS


def main() -> None:
    graph = build_discovery_graph()
    started = datetime.now(UTC)
    state = graph.invoke({"thesis": DEFAULT_THESIS.model_dump(), "trace": []})
    finished = datetime.now(UTC)

    delivery = {
        "run": {
            "job": "discovery",
            "run_id": str(uuid.uuid4()),
            "triggered_by": "manual",
            "thesis_snapshot": DEFAULT_THESIS.model_dump(),
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "stats": state.get("stats", {}),
            "trace": state.get("trace", []),
        },
        "founders": state.get("founders", []),
    }
    out = Path(__file__).resolve().parents[2] / "examples" / "discovery_live_output.json"
    out.write_text(json.dumps(delivery, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== discovery run complete ===")
    print(json.dumps(delivery["run"]["stats"], indent=2))
    for f in delivery["founders"]:
        print(
            f"  - {f['display_name']} [{f['status']}] conf={f['discovery_confidence']} signals={len(f['signals'])}"
        )
    print(f"\nwrote {out}")
    print("LangSmith: https://smith.langchain.com  (project: vc-brain-sourcing)")


if __name__ == "__main__":
    main()
