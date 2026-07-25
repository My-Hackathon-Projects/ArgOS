"""Explainable person matching primitives used by sourcing and reconciliation."""

import re
import unicodedata
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz.fuzz import ratio

from app.normalize import normalize_city

IdentityValue = str | tuple[str, ...] | None

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
        for kind in ("github", "linkedin", "twitter", "orcid")
    )


def review_fingerprint(candidate: FounderCandidate) -> str:
    """Stable key for replaying the same unresolved person mention without creating another row."""
    payload = {
        "name": normalize_person_name(candidate.display_name),
        "city": normalize_city(candidate.city),
        "company": normalize_comparison_text(candidate.current_company),
        "github": sorted(_identity_values(candidate.github, "github")),
        "linkedin": sorted(_identity_values(candidate.linkedin, "linkedin")),
        "twitter": sorted(_identity_values(candidate.twitter, "twitter")),
        "orcid": sorted(_identity_values(candidate.orcid, "orcid")),
    }
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _context_matches(left: FounderCandidate, right: FounderCandidate) -> dict[str, bool]:
    matches: dict[str, bool] = {}
    left_city = normalize_city(left.city)
    right_city = normalize_city(right.city)
    if left_city and right_city:
        matches["city"] = left_city.casefold() == right_city.casefold()
    if left.current_company and right.current_company:
        matches["company"] = normalize_comparison_text(
            left.current_company
        ) == normalize_comparison_text(right.current_company)
    if left.education and right.education:
        left_education = {normalize_comparison_text(v) for v in left.education}
        right_education = {normalize_comparison_text(v) for v in right.education}
        matches["education"] = bool(left_education & right_education)
    return matches


def resolve_candidates(
    incoming: FounderCandidate, existing: list[FounderCandidate]
) -> ResolutionResult:
    """Return the best safe action for one incoming person against existing candidates."""
    incoming_name = compact_person_name(incoming.display_name)
    best: tuple[float, str | None, tuple[str, ...], tuple[str, ...], dict] | None = None
    conflicted: tuple[float, str | None, tuple[str, ...], tuple[str, ...], dict] | None = None
    for candidate in existing:
        reasons: list[str] = []
        conflicts: list[str] = []
        evidence: dict[str, object] = {}
        for kind in ("github", "linkedin", "twitter", "orcid"):
            left = _identity_values(getattr(incoming, kind), kind)
            right = _identity_values(getattr(candidate, kind), kind)
            if left & right:
                evidence[kind] = "shared"
                if ratio(incoming_name, compact_person_name(candidate.display_name)) < 60:
                    conflicts.append(kind)
                else:
                    reasons.append(kind)
            elif left and right:
                # Both sides publish this identifier and they disagree. A public profile is
                # person-unique, so this is evidence of two different people even under one name.
                evidence[kind] = "disjoint"
                conflicts.append(kind)
        name_similarity = ratio(incoming_name, compact_person_name(candidate.display_name))
        if name_similarity >= 96:
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
            score = 0.0
        elif any(key in reasons for key in ("github", "linkedin", "twitter", "orcid")):
            score = 0.99
        elif "artifact" in reasons:
            # The same canonical artifact already attributed to this person, under the same
            # normalized name, is decisive: re-discovery of a known source, not a new human.
            score = 0.97
        elif "name" in reasons and sum(context.values()) >= 2:
            # City/company/education are corroboration, not unique public identifiers. Keep
            # strong context-only matches reviewable instead of silently collapsing people.
            score = 0.89
        else:
            score = min(0.89, name_similarity / 100 * 0.7 + sum(context.values()) * 0.1)
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
    if best is None or best[0] < 0.55:
        best = conflicted or best
    if best is None:
        return ResolutionResult("new", 0.0)
    score, matched_id, matched_reasons, matched_conflicts, evidence = best
    decision = (
        "review"
        if matched_conflicts
        else "merge"
        if score >= 0.9
        # A review verdict attaches the mention to this person, so it demands a real name match.
        # Partial similarity alone (shared surname, common token) must stay a separate person.
        else "review"
        if score >= 0.55 and "name" in matched_reasons
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
