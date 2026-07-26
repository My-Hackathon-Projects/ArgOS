"""Explainable person matching primitives used by sourcing and reconciliation."""

import re
import unicodedata
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz.fuzz import ratio
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Signal, founder_signal
from app.normalize import place_key

IdentityValue = str | tuple[str, ...] | None

# ── Resolution thresholds (single source of truth) ───────────────────────────
# Name similarity is a rapidfuzz ratio over compacted first+last names, 0-100.
NAME_MATCH_MIN = 96
"""At or above this, two spellings are treated as the same person's name."""
MERGE_NAME_MIN = 90
"""First-order gate. No evidence merges two people whose names disagree by more than this.

An identifier tells you *which* person a profile belongs to; it cannot establish that two
obviously different names are one human. This was NAME_UNRELATED_MAX = 60, and rapidfuzz scores
unrelated names far higher than intuition suggests on shared n-grams: "Xinyang Tong" vs
"Pengxiang Ding" is 61.5, which cleared 60 and let reconcile propose collapsing three distinct
researchers who happened to share an organisation's GitHub account.

90 sits in the empty band between the two populations actually observed: genuine spelling
variants score 100 ("Ada Lovelace"/"Ada King Lovelace", a "Dr." prefix, "Jose"/"José"), while
different people cluster around 60. Initials ("W. Song" vs "Wenxuan Song", 66.7) fall below the
gate on purpose — that lands in review, which is the safe direction to fail."""

# Confidence is 0-1 and decides the action taken.
MERGE_MIN_CONFIDENCE = 0.90
"""At or above this, the incoming mention is the same person: merge automatically."""
REVIEW_MIN_CONFIDENCE = 0.55
"""At or above this (with a name match), attach to the matched person and flag for review."""

CONFIDENCE_SHARED_IDENTITY = 0.99
"""A shared public profile (github/linkedin/twitter/orcid) is person-unique."""
CONFIDENCE_SHARED_ARTIFACT = 0.97
"""The same canonical artifact under the same name: re-discovery of a known source."""
CONFIDENCE_CONTEXT_ONLY = 0.89
"""Ceiling for corroboration alone. Deliberately below MERGE_MIN_CONFIDENCE: city, company and
education are not unique to a person, so they may never collapse two people on their own."""
CONFIDENCE_CONFLICT = 0.0
"""Contradicting identities. Scored lowest so a genuine match elsewhere always wins."""

STRONG_IDENTITY_KINDS = ("github", "linkedin", "twitter", "orcid")
"""Public profiles that uniquely identify a person. A website is deliberately NOT one: it may
belong to a company, lab or event, so it corroborates but never proves identity."""

NAME_SIMILARITY_WEIGHT = 0.7
CONTEXT_MATCH_WEIGHT = 0.1
"""Fallback scoring weights when no decisive evidence is present."""

_HONORIFICS = {
    "prof",
    "professor",
    "dr",
    "phd",
    "md",
    "dphil",
    "herr",
    "frau",
    "mr",
    "mrs",
    "ms",
    "mx",
    "dipl",
    "ing",
    "msc",
    "bsc",
}


@dataclass(frozen=True)
class FounderCandidate:
    display_name: str | None
    founder_id: str | None = None
    city: str | None = None
    current_company: str | None = None
    github: IdentityValue = None
    linkedin: IdentityValue = None
    twitter: IdentityValue = None
    orcid: IdentityValue = None
    website: IdentityValue = None
    education: tuple[str, ...] = ()
    # Canonical artifacts already attributed to this person. A re-discovered artifact is the
    # highest-precision evidence available and costs one query, so it is carried on the candidate.
    artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolutionResult:
    decision: str
    confidence: float
    matched_id: str | None = None
    reasons: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)


def normalize_person_name(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", (value or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z0-9]+", value)
    while tokens and tokens[0] in _HONORIFICS:
        tokens.pop(0)
    return " ".join(tokens)


# Tokens that mark an organisation, event or programme rather than a human being. Kept as whole
# tokens (never substrings) so real surnames like "Hackett" or "Labbe" are unaffected.
_NON_PERSON_TOKENS = frozenset(
    {
        "hackathon",
        "hack",
        "hacks",
        "makeathon",
        "hackfest",
        "datathon",
        "jam",
        "expo",
        "summit",
        "conference",
        "congress",
        "meetup",
        "festival",
        "challenge",
        "bootcamp",
        "accelerator",
        "incubator",
        "demoday",
        "cohort",
        "edition",
        "university",
        "universitaet",
        "universitat",
        "institute",
        "institut",
        "college",
        "gmbh",
        "ug",
        "ltd",
        "llc",
        "inc",
        "corp",
        "ventures",
        "capital",
        "partners",
        "foundation",
        "association",
        "society",
        "consortium",
        "committee",
    }
)


def is_person_name(name: str | None) -> bool:
    """Deterministic gate: could this string be a human being's name?

    Founder-first means the founder table holds people. Without this gate the only check was
    "two whitespace-separated tokens", which admitted events and GitHub organisations — the dev
    DB accumulated MakeUofT 2026, hackaTUM 2025, MunichTech EXPO and the org handle tum-ei-eda,
    each carrying signals and a Founder Score.
    """
    raw = (name or "").strip()
    if not raw or raw.casefold() == "none":
        return False
    if any(character.isdigit() for character in raw):
        return False  # cohort years: "MakeUofT 2026", "hackaTUM 2025"
    if any(separator in raw for separator in ("&", "|", "/", "@", "!")):
        return False
    if not any(character.isspace() for character in raw):
        return False  # bare handles: "annu12340", "tum-ei-eda", "curatorshashi"
    tokens = normalize_person_name(raw).split()
    if len(tokens) < 2:
        return False
    return not any(token in _NON_PERSON_TOKENS for token in tokens)


def normalize_comparison_text(value: str | None) -> str:
    """Normalize organization and education text without applying person-name rules."""
    value = unicodedata.normalize("NFKD", (value or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def compact_person_name(value: str | None) -> str:
    tokens = normalize_person_name(value).split()
    # Middle names are optional in public sources. Keep the stable first/last identity shape so
    # "Ada Lovelace" and "Ada King Lovelace" can be compared using independent context evidence.
    return " ".join((tokens[0], tokens[-1])) if len(tokens) > 1 else " ".join(tokens)


def _normalize_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value.strip() if "://" in value else f"https://{value.strip()}")
    host = parsed.netloc.casefold().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parsed.query) if not k.startswith("trk")))
    return urlunsplit(("https", host, path, query, ""))


def _identity(value: str | None, kind: str) -> str | None:
    if not value:
        return None
    if kind in {"linkedin", "website", "orcid"} or "://" in value:
        return _normalize_url(value)
    return value.strip().casefold().lstrip("@").rstrip("/")


def _identity_values(value: IdentityValue, kind: str) -> set[str]:
    values = (value,) if isinstance(value, str) else value or ()
    return {normalized for item in values if (normalized := _identity(item, kind))}


def has_shared_strong_identity(left: FounderCandidate, right: FounderCandidate) -> bool:
    """Return whether two candidates share any normalized, person-level public identifier."""
    return any(
        _identity_values(getattr(left, kind), kind) & _identity_values(getattr(right, kind), kind)
        for kind in STRONG_IDENTITY_KINDS
    )


def review_fingerprint(candidate: FounderCandidate) -> str:
    """Stable key for replaying the same unresolved person mention without creating another row."""
    payload = {
        "name": normalize_person_name(candidate.display_name),
        # Place identity, not display name: the same mention spelled "Zürich" and "Zurich" must
        # produce one fingerprint, or it is recorded for review twice.
        "city": place_key(candidate.city),
        "company": normalize_comparison_text(candidate.current_company),
        "github": sorted(_identity_values(candidate.github, "github")),
        "linkedin": sorted(_identity_values(candidate.linkedin, "linkedin")),
        "twitter": sorted(_identity_values(candidate.twitter, "twitter")),
        "orcid": sorted(_identity_values(candidate.orcid, "orcid")),
    }
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _context_matches(left: FounderCandidate, right: FounderCandidate) -> dict[str, bool]:
    matches: dict[str, bool] = {}
    # Compare the resolved place, never the rendered string. city_key already collapsed
    # diacritics, but this compared `city`, so "Zürich" vs "Zurich" — identical key, identical
    # GeoNames id — counted as a city mismatch and weakened the match score.
    left_city = place_key(left.city)
    right_city = place_key(right.city)
    if left_city and right_city:
        matches["city"] = left_city == right_city
    if left.current_company and right.current_company:
        matches["company"] = normalize_comparison_text(
            left.current_company
        ) == normalize_comparison_text(right.current_company)
    if left.education and right.education:
        left_education = {normalize_comparison_text(v) for v in left.education}
        right_education = {normalize_comparison_text(v) for v in right.education}
        matches["education"] = bool(left_education & right_education)
    return matches


def non_identifying_handles(population: list[FounderCandidate]) -> dict[str, frozenset[str]]:
    """Handles claimed by more than one known person — those identify nobody.

    Pass the WHOLE known population, not the pair being compared. "Is this handle identifying?"
    is a property of everyone we know, and a pairwise caller (reconcile compares combinations of
    two) sees one claimant per comparison and would merge on an org account. `resolve_candidates`
    derives this from `existing` when the caller does not supply it, which is correct only
    because discovery passes every founder as the candidate pool.

    A public profile is person-unique in principle, but an organisation account is published on
    every co-founder's profile: github:TheRobotStudio appeared on two different founders of the
    same startup. Once two known people claim a handle it has stopped distinguishing them, so it
    is withdrawn from merge evidence *and* from disjointness conflicts.

    The handle itself is deliberately not deleted anywhere — it is genuinely on both profiles,
    and it is the signal a human reviewer needs. Only its use as identity is withdrawn. A handle
    with a single claimant is untouched, so the strong-identity tier and the conflict/review path
    behave exactly as before.

    Claimants are counted by NAME, not by row. Several rows of one person sharing a handle is
    the duplicate case the handle exists to resolve — withdrawing it there would block the very
    merge it is for. It stops identifying only when the claimants are demonstrably different
    people, which is what disagreeing names mean.
    """
    withdrawn: dict[str, frozenset[str]] = {}
    for kind in STRONG_IDENTITY_KINDS:
        owners: dict[str, set[str]] = {}
        for candidate in population:
            name = compact_person_name(candidate.display_name)
            for value in _identity_values(getattr(candidate, kind), kind):
                owners.setdefault(value, set()).add(name)
        withdrawn[kind] = frozenset(v for v, names in owners.items() if len(names) > 1)
    return withdrawn


def resolve_candidates(
    incoming: FounderCandidate,
    existing: list[FounderCandidate],
    *,
    non_identifying: dict[str, frozenset[str]] | None = None,
) -> ResolutionResult:
    """Return the best safe action for one incoming person against existing candidates.

    `non_identifying` must be supplied by any caller whose `existing` is a subset of the known
    population — a pairwise sweep cannot see that a handle is shared. Defaulting to `existing`
    is correct only when it *is* the whole population.
    """
    incoming_name = compact_person_name(incoming.display_name)
    if non_identifying is None:
        non_identifying = non_identifying_handles(existing)
    best: tuple[float, str | None, tuple[str, ...], tuple[str, ...], dict] | None = None
    conflicted: tuple[float, str | None, tuple[str, ...], tuple[str, ...], dict] | None = None
    for candidate in existing:
        reasons: list[str] = []
        conflicts: list[str] = []
        evidence: dict[str, object] = {}
        name_similarity = ratio(incoming_name, compact_person_name(candidate.display_name))
        for kind in STRONG_IDENTITY_KINDS:
            left = _identity_values(getattr(incoming, kind), kind) - non_identifying[kind]
            right = _identity_values(getattr(candidate, kind), kind) - non_identifying[kind]
            if left & right:
                evidence[kind] = "shared"
                if name_similarity < MERGE_NAME_MIN:
                    # Name gate first. A shared handle under names this different is an
                    # organisation account or a mis-attribution, never proof of one person.
                    conflicts.append(kind)
                else:
                    reasons.append(kind)
            elif left and right and name_similarity >= NAME_MATCH_MIN:
                # Same name, but both sides publish this identifier and they disagree. A public
                # profile is person-unique, so these are two different people sharing a name.
                # Scoped to a name match: unrelated people having different LinkedIns is normal.
                evidence[kind] = "disjoint"
                conflicts.append(kind)
        if name_similarity >= NAME_MATCH_MIN:
            reasons.append("name")
        shared_artifacts = set(incoming.artifact_ids) & set(candidate.artifact_ids)
        if shared_artifacts:
            evidence["shared_artifacts"] = sorted(shared_artifacts)
            if "name" in reasons:
                reasons.append("artifact")
        context = _context_matches(incoming, candidate)
        evidence.update(context)
        reasons.extend(key for key, value in context.items() if value)
        if conflicts:
            # Scored low so a genuinely matching candidate elsewhere in the list still wins;
            # the conflict is carried separately and decides the outcome only if nothing matched.
            score = CONFIDENCE_CONFLICT
        elif any(key in reasons for key in STRONG_IDENTITY_KINDS):
            score = CONFIDENCE_SHARED_IDENTITY
        elif "artifact" in reasons:
            # The same canonical artifact already attributed to this person, under the same
            # normalized name, is decisive: re-discovery of a known source, not a new human.
            score = CONFIDENCE_SHARED_ARTIFACT
        elif "name" in reasons and sum(context.values()) >= 2:
            # City/company/education are corroboration, not unique public identifiers. Keep
            # strong context-only matches reviewable instead of silently collapsing people.
            score = CONFIDENCE_CONTEXT_ONLY
        else:
            score = min(
                CONFIDENCE_CONTEXT_ONLY,
                name_similarity / 100 * NAME_SIMILARITY_WEIGHT
                + sum(context.values()) * CONTEXT_MATCH_WEIGHT,
            )
        item = (
            score,
            candidate.founder_id,
            tuple(sorted(set(reasons))),
            tuple(conflicts),
            evidence,
        )
        if conflicts:
            if conflicted is None:
                conflicted = item
            continue
        if best is None or item[0] > best[0]:
            best = item
    # A conflict only decides the outcome when no candidate matched on its own merits.
    if best is None or best[0] < REVIEW_MIN_CONFIDENCE:
        best = conflicted or best
    if best is None:
        return ResolutionResult("new", 0.0)
    score, matched_id, matched_reasons, matched_conflicts, evidence = best
    decision = (
        "review"
        if matched_conflicts
        else "merge"
        if score >= MERGE_MIN_CONFIDENCE
        # A review verdict attaches the mention to this person, so it demands a real name match.
        # Partial similarity alone (shared surname, common token) must stay a separate person.
        else "review"
        if score >= REVIEW_MIN_CONFIDENCE and "name" in matched_reasons
        else "new"
    )
    return ResolutionResult(
        decision,
        round(score, 3),
        matched_id,
        matched_reasons,
        matched_conflicts,
        evidence,
    )


def artifact_ids_by_founder(db: Session) -> dict[str, tuple[str, ...]]:
    """Canonical artifact URLs already attributed to each founder.

    Shared by the ingest resolver and by reconciliation so both judge re-discovery on the same
    evidence. Without it, reconciliation cannot see that two rows cite the identical source.
    """
    rows = db.execute(
        select(founder_signal.c.founder_id, Signal.canonical_url).join(
            Signal, Signal.id == founder_signal.c.signal_id
        )
    ).all()
    by_founder: dict[str, list[str]] = {}
    for founder_id, canonical_url in rows:
        if canonical_url:
            by_founder.setdefault(str(founder_id), []).append(canonical_url)
    return {key: tuple(value) for key, value in by_founder.items()}
