"""XML-tag-structured prompts for the market-research graph.

Structured sections (<role>/<opportunity>/<thesis>/<evidence>/<task>/<rules>/<output>) so each
instruction block is unambiguous and the model can attend to it cleanly — a prompting best practice
for multi-section reasoning. Every extractor is told to cite evidence by hit index and to gap-flag
rather than invent. The thesis rides in every prompt so scoring stays thesis-relative.
"""

from app.market.schemas import SUBGOALS


def opp_block(opp: dict) -> str:
    return (
        "<opportunity>\n"
        f"  <company_name>{opp.get('company_name') or 'undisclosed / idea-stage'}</company_name>\n"
        f"  <idea>{opp.get('idea') or ''}</idea>\n"
        f"  <sector>{opp.get('sector') or 'unspecified'}</sector>\n"
        f"  <geo>{opp.get('geo') or 'unspecified'}</geo>\n"
        "</opportunity>"
    )


def thesis_block(thesis: dict) -> str:
    return (
        "<thesis>\n"
        f"  <industries>{thesis.get('industries')}</industries>\n"
        f"  <geo>{thesis.get('geo')}</geo>\n"
        f"  <stage>{thesis.get('stage')}</stage>\n"
        f"  <keywords>{thesis.get('keywords')}</keywords>\n"
        f"  <check_size>{thesis.get('check_size')}</check_size>\n"
        "</thesis>"
    )


def hits_block(hits: list[dict]) -> str:
    if not hits:
        return "<evidence>\n  (no search results were returned for this sub-goal)\n</evidence>"
    body = "\n".join(
        f'  <hit index="{i}">\n'
        f"    <title>{h.get('title') or ''}</title>\n"
        f"    <url>{h.get('url') or ''}</url>\n"
        f"    <content>{(h.get('content') or '')[:1500]}</content>\n"
        f"  </hit>"
        for i, h in enumerate(hits)
    )
    return f"<evidence>\n{body}\n</evidence>"


# ── ① planner ────────────────────────────────────────────────────────────────
def plan_prompt(opp: dict, thesis: dict, per_goal: int) -> str:
    return f"""<role>You are a VC market-research strategist. You plan web searches that gather the
outside-world evidence a fund needs before a term sheet: market size, competition, comparable
fundings, and sector KPI benchmarks.</role>

{opp_block(opp)}

{thesis_block(thesis)}

<task>
Write {per_goal} focused, executable web-search queries for EACH of these sub-goals
({", ".join(SUBGOALS)}):
- sizing        — size the GENERAL / PARENT market (broad sector, e.g. "robotics market size",
                  "edge AI market size 2025") + growth/CAGR. Don't over-narrow to the exact product.
- competition   — direct competitors, incumbents, and challengers to this idea.
- comparables   — startups solving a SIMILAR PROBLEM at a similar stage that RAISED funding
                  (seed / Series A). Phrase for funding announcements ("raised", "seed round").
- kpi           — sector unit-economics benchmarks: typical CAC, CPC, LTV, gross margin, ACV,
                  seed round size.
- trend         — why-now: tailwinds, regulation, technology shifts, demand signals.
</task>

<rules>
1. Set `subgoal` to exactly one of {", ".join(SUBGOALS)}.
2. Anchor queries to the idea + sector; add the geo when it sharpens the result.
3. Prefer specific, recent phrasing (include years 2023-2025 for comparables/trends).
4. `domain` optional — set it only to force a specific site; else null (open web).
</rules>

Generate the queries now."""


_CITATION_RULES = """<rules>
CITATION + HONESTY (non-negotiable — a flagged gap scores HIGHER than a fabricated number):
1. Every quantitative claim MUST trace to the evidence. Put the backing <hit> index/indices in
   `citation_indices`.
2. `basis` is one of:
   - reported            -> a source states this figure. citation_indices REQUIRED.
   - estimated_bottom_up -> you DERIVED it (e.g. # customers x ACV, or TAM x penetration). Put the
     derivation + which inputs you used in `assumptions`, and cite those inputs in citation_indices.
   - gap                 -> not found and cannot be derived from cited inputs. value=null,
     citation_indices=[]. DO NOT invent a number.
3. NEVER output a numeric value with basis=reported/estimated_bottom_up and no citation_indices.
4. Only use facts present in <evidence>. Do not use outside knowledge as if it were sourced.
</rules>"""


# ── ② sizing ─────────────────────────────────────────────────────────────────
def sizing_prompt(opp: dict, hits: list[dict]) -> str:
    return f"""<role>You are a VC analyst producing the market-sizing section of an
investment memo.</role>

{opp_block(opp)}

{hits_block(hits)}

<task>
Size the market in three NESTED tiers — anchor on the general market, then narrow:
- TAM: the broad GENERAL / PARENT market this idea sits in (the sector, e.g. "global robotics
  market" or "edge AI market"). Use a reputable REPORTED total — general markets have stable
  published figures; do NOT chase an ultra-niche number no report cleanly measures.
- SAM: the slice addressable given the specific idea + geography/thesis (reported or bottom-up).
- SOM: the realistic near-term obtainable share (usually a cited bottom-up estimate).
Also emit a "CAGR" figure and set `market_maturity`. In each figure's `note`, state EXACTLY which
market it measures (e.g. "global robotics market"). Emit AT MOST ONE figure per metric.
Prefer a stable general-market TAM + clearly-scoped SAM/SOM over a noisy niche figure.
</task>

{_CITATION_RULES}

Produce the sizing now."""


# ── ③ competition ────────────────────────────────────────────────────────────
def competition_prompt(opp: dict, hits: list[dict]) -> str:
    return f"""<role>You are a VC analyst mapping the competitive landscape for an
investment memo.</role>

{opp_block(opp)}

{hits_block(hits)}

<task>
Identify the named competitors from the evidence. For each: `cluster`
(incumbent|challenger|emerging|adjacent), a one-line `positioning`, and whether it is an
`is_emerging_threat`. Set overall `concentration` (fragmented|moderate|concentrated). Cite each
competitor's backing hit index in `citation_indices`.
</task>

<rules>
1. Only name competitors that appear in <evidence>. Do not invent companies.
2. If evidence is thin, return few competitors and say so in `summary` — do not pad.
</rules>

Map the competition now."""


# ── ④ comparables ────────────────────────────────────────────────────────────
def comparables_prompt(opp: dict, hits: list[dict]) -> str:
    return f"""<role>You are a VC analyst building a comparables/benchmarking table:
similar startups that RAISED funding, used to benchmark this opportunity.</role>

{opp_block(opp)}

{hits_block(hits)}

<task>
Extract startups solving a SIMILAR PROBLEM at a similar stage that raised funding. For each: `name`,
`one_liner`, `stage`, `round_size`, `valuation`, `investors`, `date`, and a `similarity_rationale`
(why it is comparable to THIS opportunity). Cite the announcement hit index in `citation_indices`.
</task>

<rules>
1. A comparable whose EXISTENCE is cited but whose amount is undisclosed is still valid — set
   round_size/valuation to null, keep the comparable. NEVER guess an amount.
2. Same PROBLEM / business model beats same sector: an infra/software comp beats a hardware giant
   in the same vertical. Rank by (problem similarity + stage match).
3. STAGE + SIZE MATCH: prioritize seed / Series A rounds (roughly <=$50M). Strongly DE-prioritize
   mega-rounds (>$100M) and late-stage / hardware category leaders — they are NOT benchmarks for an
   early-stage deal; include at most one, at LOW confidence, only if directly problem-similar.
4. Only include companies present in <evidence>.
</rules>

Build the comparables now."""


# ── ⑤ kpi benchmarks ─────────────────────────────────────────────────────────
def kpi_prompt(opp: dict, hits: list[dict]) -> str:
    return f"""<role>You are a VC analyst extracting sector unit-economics benchmarks
to contextualize a startup's KPIs in the Traction & KPIs memo section.</role>

{opp_block(opp)}

{hits_block(hits)}

<task>
Extract typical sector UNIT-ECONOMICS bands as `Figure`s (metric one of: CAC, CPC, LTV,
gross_margin, ACV, seed_round_size). Values are ranges/bands ("$1,200-1,800", "70-80%").
These contextualize a startup's OWN KPIs, so they must be per-company norms, not market totals:
- seed_round_size = a TYPICAL PER-COMPANY seed round for this sector/stage (e.g. "$1.5M-4M"), NOT
  an aggregate market/annual fundraising total. Reject any figure that is a whole-market total.
Emit AT MOST ONE figure per metric. Gap-flag any not found — a gap beats a wrong band.
</task>

{_CITATION_RULES}

Extract the benchmarks now."""


# ── ⑥ synthesis + market axis ────────────────────────────────────────────────
def _findings_block(sizing: dict, competition: dict, comparables: dict, kpi: dict) -> str:
    import json

    def dump(x):
        return json.dumps(x, ensure_ascii=False, indent=2)

    return (
        "<findings>\n"
        f"  <sizing>{dump(sizing)}</sizing>\n"
        f"  <competition>{dump(competition)}</competition>\n"
        f"  <comparables>{dump(comparables)}</comparables>\n"
        f"  <kpi_benchmarks>{dump(kpi)}</kpi_benchmarks>\n"
        "</findings>"
    )


def synthesis_prompt(
    opp: dict, thesis: dict, sizing: dict, competition: dict, comparables: dict, kpi: dict
) -> str:
    return f"""<role>You are a VC partner writing the market judgment for an investment memo.
You reason over researched market findings and score the MARKET axis of a 3-axis
screen — RELATIVE TO THE FUND THESIS. You are honest: a thin, cold, or crowded
market scores low and you say why.</role>

{opp_block(opp)}

{thesis_block(thesis)}

{_findings_block(sizing, competition, comparables, kpi)}

<task>
1. hypotheses: 2-4 market bull hypotheses AND at least one bear counter-case (kind='bear').
2. opportunities / threats: the market halves of a SWOT (tailwinds / competitive + regulatory risk).
3. why_now: one-paragraph timing case, or state that timing is unclear.
4. axis: the MARKET verdict — verdict (bull|neutral|bear), score 0..100 (thesis-relative
   attractiveness), trend (improving|declining|stable), and a `rationale` that NAMES the findings it
   rests on. Confidence reflects how much of this is reported vs estimated vs gap.
5. gaps: list every material figure that was gap-flagged or is unverified.
</task>

<rules>
1. Thesis-relative: judge the market against THIS fund's stage/check/sector, not in the abstract.
2. Ground every claim in <findings>. If the findings are mostly gaps, the verdict must reflect that
   (lower score, lower confidence) — do not manufacture conviction from thin evidence.
3. `trend` is a market-momentum proxy: accelerating growth / strong why-now -> improving; shrinking
   or commoditizing -> declining; otherwise stable.
4. When you cite sizing, quote the EXACT TAM/SAM/SOM values and CAGR from <findings> and name which
   market the TAM measures (from the figure's note). Never introduce a different number.
</rules>

Write the market judgment now."""
