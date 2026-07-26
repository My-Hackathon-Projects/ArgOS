"""Canonical identity for a person's public profiles — one value shape per kind.

`geonameid` is the canonical identity of a place and `ror_id` of an institution. Public profiles
had no equivalent: the same person's ORCID arrived as `0000-0002-1825-0097` and as
`https://orcid.org/0000-0002-1825-0097`, GitHub as `ada-lovelace` and as a profile URL, and the
comparison in `entity_resolution` treated the two spellings as *different identifiers*. Because a
strong identifier is person-unique, "both sides publish one and they differ" is read as proof of
distinctness — so a normalizer miss was upgraded into a confident wrong answer and forked one
person into two rows, resetting the Founder Score that is supposed to never reset.

The fix is a single canonical token per kind, applied at the WRITE boundary rather than defensively
at each comparison, so the stored value is already the identity:

    orcid     0000-0002-1825-0097   (hyphenated, checksum-verified)
    github    ada-lovelace          (lowercased login)
    twitter   ada                   (lowercased handle)
    linkedin  adalovelace           (lowercased /in/ slug)
    website   https://example.com   (normalized URL — corroborates, never identifies)

Display URLs are DERIVED (`profile_url`), never stored: one source of truth, no drift.

Not every value that arrives is an identifier. A LinkedIn *post* or *company* page is a real
artifact about the person but identifies nobody — two people who each posted have different post
URLs, which the disjoint rule then reads as proof they are different humans. Those are returned
with `artifact_url` set so the caller can keep them as evidence (a Signal) instead of as identity.
Values that are neither (a reserved path, a bad ORCID checksum) are rejected outright and counted.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

STRONG_KINDS = ("github", "linkedin", "twitter", "orcid")
"""Public profiles that identify a person. `website` is deliberately excluded: it may belong to a
company, lab or event, so it corroborates but never proves identity."""

ALL_KINDS = (*STRONG_KINDS, "website")

# Reserved first-path segments that are site features, not people. graph.py carried two partial
# copies of this list with different contents (one had "sponsors", the other did not); this is the
# single source of truth for both the extractor and the writer.
_GITHUB_RESERVED = frozenset(
    """about apps collections codespaces contact customer-storiesdashboard enterprise events
    explore features issues join login logout marketplace new notifications orgs organizations
    pricing pulls readme security settings sponsors stars topics trending signup site
    security-advisories""".split()
)
_TWITTER_RESERVED = frozenset(
    """about account compose explore hashtag home i intent jobs login logout messages notifications
    privacy search settings share signup status tos welcome who_to_follow""".split()
)

# LinkedIn path prefixes that are real artifacts about a person but are not that person's profile.
# Kept rather than dropped: a post IS evidence, it just is not an identifier.
_LINKEDIN_ARTIFACT_PREFIXES = ("posts", "feed", "pulse", "company", "school", "groups", "jobs")

_GITHUB_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_TWITTER_HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_LINKEDIN_SLUG = re.compile(r"^[\w\-%.]{3,100}$", re.UNICODE)
_ORCID_DIGITS = re.compile(r"(\d{4})-?(\d{4})-?(\d{4})-?(\d{3}[\dXx])")

_TRACKING_PREFIX = "trk"


@dataclass(frozen=True)
class ParsedIdentity:
    """What one raw identity value turned out to be.

    Exactly one of `value` / `artifact_url` / `rejected` is set. `value` is the canonical identity
    token; `artifact_url` is a real URL worth keeping as evidence but not as identity; `rejected`
    names why the value is unusable, so the count is visible to the operator instead of silent.
    """

    kind: str
    raw: str
    value: str | None = None
    artifact_url: str | None = None
    rejected: str | None = None


_HOSTS = {
    "github": ("github.com",),
    "twitter": ("twitter.com", "x.com"),
    "linkedin": ("linkedin.",),
}


def _segments(kind: str, raw: str) -> list[str] | None:
    """Path segments of a profile reference, or None when the value names a different site.

    Accepts every shape a source actually produces for the same profile: a full URL, a
    host-relative path (`/in/AdaLovelace`), a bare handle, an `@handle`, and any of those with a
    trailing slash. All of them reduce to the same segment list, which is what makes the four
    spellings of one identifier compare equal.
    """
    value = raw.strip()
    hosts = _HOSTS[kind]
    if "://" in value or any(host in value.casefold() for host in hosts):
        parsed = urlsplit(value if "://" in value else f"https://{value}")
        host = parsed.netloc.casefold().removeprefix("www.").split(":")[0]
        if not any(known in host for known in hosts):
            return None
        return [segment for segment in parsed.path.split("/") if segment]
    return [segment for segment in value.lstrip("@").strip("/").split("/") if segment]


def normalize_website(raw: str | None) -> str | None:
    """Scheme/host/tracking-normalized URL. Not an identity — kept for corroboration only."""
    if not raw or not raw.strip():
        return None
    parsed = urlsplit(raw.strip() if "://" in raw else f"https://{raw.strip()}")
    host = parsed.netloc.casefold().removeprefix("www.")
    if not host:
        return None
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parsed.query) if not k.startswith(_TRACKING_PREFIX))
    )
    return urlunsplit(("https", host, parsed.path.rstrip("/"), query, ""))


def _artifact_url(raw: str) -> str | None:
    """Canonical URL for a non-identifying page, matching the signal writer's dedup key.

    linkedin.com and x.com serve case-insensitive paths, and `sourcing.graph._canonicalize`
    lowercases them for exactly that reason. An artifact rerouted from here must land on the same
    key or it becomes a second row for one page — which inflates noisy-OR trust as if the claim
    had been independently corroborated.
    """
    normalized = normalize_website(raw)
    if not normalized:
        return None
    parts = urlsplit(normalized)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.lower(), parts.query, ""))


def orcid_checksum_ok(digits: str) -> bool:
    """ORCID's ISO 7064 MOD 11-2 check digit. A typo is provably rejectable, not just suspicious."""
    if len(digits) != 16:
        return False
    total = 0
    for character in digits[:15]:
        if not character.isdigit():
            return False
        total = (total + int(character)) * 2
    remainder = (12 - total % 11) % 11
    return ("X" if remainder == 10 else str(remainder)) == digits[15].upper()


def _parse_orcid(raw: str) -> ParsedIdentity:
    match = _ORCID_DIGITS.search(raw)
    if match is None:
        return ParsedIdentity("orcid", raw, rejected="malformed")
    digits = "".join(match.groups()).upper()
    if not orcid_checksum_ok(digits):
        # An ORCID carries its own check digit, so this is a transcription error or an invention,
        # never a valid identifier we merely failed to recognise.
        return ParsedIdentity("orcid", raw, rejected="checksum")
    return ParsedIdentity("orcid", raw, value="-".join(digits[i : i + 4] for i in range(0, 16, 4)))


def _parse_github(raw: str) -> ParsedIdentity:
    segments = _segments("github", raw)
    if segments is None:
        return ParsedIdentity("github", raw, rejected="wrong_host")
    if not segments:
        return ParsedIdentity("github", raw, rejected="malformed")
    login = segments[0]
    if login.casefold() in _GITHUB_RESERVED:
        return ParsedIdentity("github", raw, rejected="reserved")
    if not _GITHUB_LOGIN.match(login):
        return ParsedIdentity("github", raw, rejected="malformed")
    return ParsedIdentity("github", raw, value=login.casefold())


def _parse_twitter(raw: str) -> ParsedIdentity:
    segments = _segments("twitter", raw)
    if segments is None:
        return ParsedIdentity("twitter", raw, rejected="wrong_host")
    if not segments:
        return ParsedIdentity("twitter", raw, rejected="malformed")
    # A tweet permalink (/user/status/123) is an artifact about the person, not their handle.
    if len(segments) >= 2 and segments[1].casefold() == "status":
        return ParsedIdentity("twitter", raw, artifact_url=_artifact_url(raw))
    handle = segments[0]
    if handle.casefold() in _TWITTER_RESERVED:
        return ParsedIdentity("twitter", raw, rejected="reserved")
    if not _TWITTER_HANDLE.match(handle):
        return ParsedIdentity("twitter", raw, rejected="malformed")
    return ParsedIdentity("twitter", raw, value=handle.casefold())


def _parse_linkedin(raw: str) -> ParsedIdentity:
    segments = _segments("linkedin", raw)
    if segments is None:
        return ParsedIdentity("linkedin", raw, rejected="wrong_host")
    if not segments:
        return ParsedIdentity("linkedin", raw, rejected="malformed")
    head = segments[0].casefold()
    if head in _LINKEDIN_ARTIFACT_PREFIXES:
        # A post/company/school page is real evidence about the founder — it is simply not that
        # founder's identity. Two people who each posted have different post URLs, and treating
        # those as identifiers made "different post" read as "different person".
        return ParsedIdentity("linkedin", raw, artifact_url=_artifact_url(raw))
    if head in ("in", "pub"):
        if len(segments) < 2:
            return ParsedIdentity("linkedin", raw, rejected="malformed")
        slug = segments[1]
    else:
        # A bare slug with no path context is assumed to be a profile — that is how sources that
        # strip the URL down to its last segment deliver it.
        slug = segments[0]
    slug = unquote(slug)
    if not _LINKEDIN_SLUG.match(slug):
        return ParsedIdentity("linkedin", raw, rejected="malformed")
    return ParsedIdentity("linkedin", raw, value=slug.casefold())


_PARSERS = {
    "orcid": _parse_orcid,
    "github": _parse_github,
    "twitter": _parse_twitter,
    "linkedin": _parse_linkedin,
}


def parse_identity(kind: str, raw: str | None) -> ParsedIdentity:
    """Canonicalize one raw identity value. Fails loudly on an unknown kind."""
    if kind not in ALL_KINDS:
        raise ValueError(f"unknown identity kind: {kind!r}")
    if raw is None or not str(raw).strip():
        return ParsedIdentity(kind, "", rejected="empty")
    raw = str(raw).strip()
    if kind == "website":
        normalized = normalize_website(raw)
        return (
            ParsedIdentity(kind, raw, value=normalized)
            if normalized
            else ParsedIdentity(kind, raw, rejected="malformed")
        )
    return _PARSERS[kind](raw)


def canonical_identity(kind: str, raw: str | None) -> str | None:
    """The canonical token, or None when the value does not identify a person."""
    return parse_identity(kind, raw).value


def profile_url(kind: str, value: str | None) -> str | None:
    """Derive the public URL for a canonical token. Display is derived, never stored."""
    if not value:
        return None
    if kind == "website":
        return value
    return {
        "github": f"https://github.com/{value}",
        "twitter": f"https://x.com/{value}",
        "linkedin": f"https://www.linkedin.com/in/{value}",
        "orcid": f"https://orcid.org/{value}",
    }[kind]
