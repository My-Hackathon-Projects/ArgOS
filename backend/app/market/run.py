"""Manual market-research smoke-run — invokes the graph on one demo opportunity, prints the memo
inputs (TAM/SAM/SOM + competitors + comparables + market axis), writes the analysis JSON.

No DB writes here (persist is exercised via app.market.service against the live DB).
Run: uv run python -m app.market.run
"""

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.market.graph import build_market_graph
from app.market.schemas import OpportunityInput
from app.sourcing.thesis import DEFAULT_THESIS

# Windows console defaults to cp1252 and mangles € / em-dash in the demo print — force UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEMO_OPPORTUNITY = OpportunityInput(
    company_name="Nimbus Edge",
    idea="On-device LLM inference runtime that cuts GPU cost for robotics autonomy stacks",
    sector="AI infrastructure / edge ML",
    geo="Germany",
)


def _fig_line(f: dict) -> str:
    cites = len(f.get("citation_indices") or [])
    val = f.get("value") if f.get("basis") != "gap" else "— (gap)"
    return (
        f"    {f.get('metric')}: {val}  "
        f"[{f.get('basis')}, {cites} cite(s), conf={f.get('confidence')}]"
    )


def main() -> None:
    graph = build_market_graph()
    started = datetime.now(UTC)
    state = graph.invoke(
        {
            "opportunity": DEMO_OPPORTUNITY.model_dump(),
            "thesis": DEFAULT_THESIS.model_dump(),
            "trace": [],
        }
    )
    finished = datetime.now(UTC)

    sizing = state.get("sizing") or {}
    competition = state.get("competition") or {}
    comparables = state.get("comparables") or {}
    kpi = state.get("kpi") or {}
    syn = state.get("synthesis") or {}
    axis = syn.get("axis") or {}

    delivery = {
        "run": {
            "job": "market",
            "run_id": str(uuid.uuid4()),
            "opportunity": DEMO_OPPORTUNITY.model_dump(),
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "stats": state.get("stats", {}),
            "trace": state.get("trace", []),
        },
        "analysis": {
            "sizing": sizing,
            "competition": competition,
            "comparables": comparables,
            "kpi": kpi,
            "synthesis": syn,
        },
    }
    out = Path(__file__).resolve().parents[2] / "examples" / "market_live_output.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(delivery, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== market research complete ===")
    print(json.dumps(state.get("stats", {}), indent=2))

    print("\n--- Market sizing ---")
    for f in sizing.get("figures", []):
        print(_fig_line(f))
    print(f"    maturity: {sizing.get('market_maturity')}")

    print("\n--- KPI benchmarks ---")
    for f in kpi.get("benchmarks", []):
        print(_fig_line(f))

    print("\n--- Competition ---")
    for c in competition.get("competitors", [])[:8]:
        threat = " (emerging threat)" if c.get("is_emerging_threat") else ""
        print(f"    {c.get('name')} [{c.get('cluster')}]{threat}: {c.get('positioning')}")
    print(f"    concentration: {competition.get('concentration')}")

    print("\n--- Comparables (raised) ---")
    for c in comparables.get("comparables", [])[:8]:
        print(
            f"    {c.get('name')} — {c.get('round_size') or 'undisclosed'} "
            f"{c.get('stage') or ''} ({c.get('date') or 'n/a'}) :: {c.get('similarity_rationale')}"
        )

    print("\n--- MARKET AXIS ---")
    print(
        f"    verdict={axis.get('verdict')}  score={axis.get('score')}  "
        f"trend={axis.get('trend')}  conf={axis.get('confidence')}"
    )
    print(f"    rationale: {axis.get('rationale')}")
    if syn.get("gaps"):
        print(f"    gaps: {syn.get('gaps')}")

    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
