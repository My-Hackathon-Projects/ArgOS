"""Market-research graph.

Nodes:  plan_research -> run_searches -> extract -> synthesize -> finalize
- plan/extractors use the fast model; the market-axis synthesis uses the smart model (gpt-5.4).
- run_searches + the four extractors fan out in a thread pool (parallel Tavily + LLM I/O).
- Shared tagged search pool: one planner tags queries by sub-goal; each extractor takes its slice.
- Reuses the sourcing tavily client; persist reuses its URL/reliability utils so market `web`
  signals are minted identically to discovery signals. Auto-traced to LangSmith.

finalize hands back an in-memory MarketAnalysis; persistence is a separate single-writer step.
"""

import operator
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, TypedDict

import httpx
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.market import prompts
from app.market.schemas import (
    Comparables,
    Competition,
    KpiBenchmarks,
    MarketSearchPlan,
    MarketSizing,
    MarketSynthesis,
)
from app.sourcing import tavily

# Comparables precision bias — funding-news outlets Tavily can see (paywalled DBs it can't).
FUNDING_NEWS_DOMAINS = [
    "techcrunch.com",
    "sifted.eu",
    "eu-startups.com",
    "tech.eu",
    "crunchbase.com",
]


class MarketState(TypedDict, total=False):
    opportunity: dict
    thesis: dict
    queries: list[dict]
    hits_by_goal: dict[str, list[dict]]
    sizing: dict
    competition: dict
    comparables: dict
    kpi: dict
    synthesis: dict
    stats: dict
    trace: Annotated[list[str], operator.add]


def _llm(schema, smart: bool = False):
    model = settings.model_smart if smart else settings.model_fast
    # function_calling (not strict json_schema) so flexible optional/nested fields are allowed.
    return ChatOpenAI(model=model, api_key=settings.openai_api_key).with_structured_output(
        schema, method="function_calling"
    )


def extractor_hits(hits_by_goal: dict) -> dict:
    """The exact ordered hit list each extractor is given — shared by the graph AND persist so
    `citation_indices` resolve to the same signals. Trend hits inform market dynamics -> sizing."""
    return {
        "sizing": (hits_by_goal.get("sizing") or []) + (hits_by_goal.get("trend") or []),
        "competition": hits_by_goal.get("competition") or [],
        "comparables": hits_by_goal.get("comparables") or [],
        "kpi": hits_by_goal.get("kpi") or [],
    }


# ── ① plan_research (fast model) ─────────────────────────────────────────────
def plan_research(state: MarketState) -> dict:
    opp = state["opportunity"]
    thesis = state["thesis"]
    plan = _llm(MarketSearchPlan).invoke(
        prompts.plan_prompt(opp, thesis, settings.market_queries_per_goal)
    )
    queries = [q.model_dump() for q in plan.queries]
    return {
        "queries": queries,
        "trace": [f"plan_research -> {len(queries)} queries across sub-goals"],
    }


# ── ② run_searches (parallel Tavily, tagged by sub-goal) ─────────────────────
def _search_one(q: dict) -> list[dict]:
    if q.get("domain"):
        domains = [q["domain"]]
    elif q.get("subgoal") == "comparables":
        domains = FUNDING_NEWS_DOMAINS  # bias comps toward funding-news outlets
    else:
        domains = None
    try:
        res = tavily.tavily_search(
            q["query"],
            settings.tavily_api_key,
            max_results=settings.market_max_results,
            include_domains=domains,
        )
    except httpx.HTTPError:
        return []  # one flaky query must not sink the fan-out (narrow, not silent)
    return [
        {
            "subgoal": q.get("subgoal"),
            "title": r.get("title"),
            "url": r.get("url"),
            "content": (r.get("content") or "")[:1500],
        }
        for r in res.get("results", [])
    ]


def run_searches(state: MarketState) -> dict:
    queries = state["queries"]
    hits_by_goal: dict[str, list[dict]] = {}
    seen: set[str] = set()
    with ThreadPoolExecutor(max_workers=settings.max_workers) as ex:
        for batch in ex.map(_search_one, queries):
            for h in batch:
                url = h.get("url")
                sg = h.get("subgoal") or "sizing"
                if not url or url in seen:
                    continue
                seen.add(url)
                bucket = hits_by_goal.setdefault(sg, [])
                if len(bucket) < settings.market_max_hits_per_goal:
                    bucket.append(h)
    total = sum(len(v) for v in hits_by_goal.values())
    return {
        "hits_by_goal": hits_by_goal,
        "trace": [f"run_searches -> {total} unique hits across {len(hits_by_goal)} sub-goals"],
    }


# ── ③ extractors (each independently testable) ───────────────────────────────
def extract_sizing(opp: dict, hits: list[dict]) -> dict:
    return _llm(MarketSizing).invoke(prompts.sizing_prompt(opp, hits)).model_dump()


def extract_competition(opp: dict, hits: list[dict]) -> dict:
    return _llm(Competition).invoke(prompts.competition_prompt(opp, hits)).model_dump()


def extract_comparables(opp: dict, hits: list[dict]) -> dict:
    return _llm(Comparables).invoke(prompts.comparables_prompt(opp, hits)).model_dump()


def extract_kpi(opp: dict, hits: list[dict]) -> dict:
    return _llm(KpiBenchmarks).invoke(prompts.kpi_prompt(opp, hits)).model_dump()


def extract(state: MarketState) -> dict:
    opp = state["opportunity"]
    eh = extractor_hits(state.get("hits_by_goal") or {})
    tasks = {
        "sizing": lambda: extract_sizing(opp, eh["sizing"]),
        "competition": lambda: extract_competition(opp, eh["competition"]),
        "comparables": lambda: extract_comparables(opp, eh["comparables"]),
        "kpi": lambda: extract_kpi(opp, eh["kpi"]),
    }
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {k: ex.submit(fn) for k, fn in tasks.items()}
        out = {k: f.result() for k, f in futs.items()}
    n_comps = len(out["comparables"].get("comparables", []))
    n_competitors = len(out["competition"].get("competitors", []))
    n_figs = len(out["sizing"].get("figures", [])) + len(out["kpi"].get("benchmarks", []))
    return {
        **out,
        "trace": [
            f"extract -> {n_figs} figures, {n_competitors} competitors, {n_comps} comparables"
        ],
    }


# ── ④ synthesize (smart model — the market axis) ─────────────────────────────
def synthesize(state: MarketState) -> dict:
    opp = state["opportunity"]
    thesis = state["thesis"]
    syn = _llm(MarketSynthesis, smart=True).invoke(
        prompts.synthesis_prompt(
            opp,
            thesis,
            state.get("sizing") or {},
            state.get("competition") or {},
            state.get("comparables") or {},
            state.get("kpi") or {},
        )
    )
    d = syn.model_dump()
    axis = d.get("axis") or {}
    return {
        "synthesis": d,
        "trace": [
            f"synthesize -> market axis {axis.get('verdict')} "
            f"score={axis.get('score')} trend={axis.get('trend')}"
        ],
    }


# ── ⑤ finalize ───────────────────────────────────────────────────────────────
def finalize(state: MarketState) -> dict:
    hbg = state.get("hits_by_goal") or {}
    stats = {
        "queries_run": len(state.get("queries", [])),
        "hits": sum(len(v) for v in hbg.values()),
        "sizing_figures": len((state.get("sizing") or {}).get("figures", [])),
        "competitors": len((state.get("competition") or {}).get("competitors", [])),
        "comparables": len((state.get("comparables") or {}).get("comparables", [])),
        "kpi_benchmarks": len((state.get("kpi") or {}).get("benchmarks", [])),
    }
    return {"stats": stats, "trace": [f"finalize -> {stats}"]}


def build_market_graph():
    g = StateGraph(MarketState)
    g.add_node("plan_research", plan_research)
    g.add_node("run_searches", run_searches)
    g.add_node("extract", extract)
    g.add_node("synthesize", synthesize)
    g.add_node("finalize", finalize)
    g.add_edge(START, "plan_research")
    g.add_edge("plan_research", "run_searches")
    g.add_edge("run_searches", "extract")
    g.add_edge("extract", "synthesize")
    g.add_edge("synthesize", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
