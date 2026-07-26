"""Single-writer persist step (Q10 ⑥⑦). Resolves each founder, dedups + writes signals.

Resolution ladder (MVP cut): strong-id exact → normalized-name exact → create new.
Fuzzy/LLM tiers are additive later; strong-id + normalized-name keeps re-runs idempotent
without false-merging on a bare shared name.
"""

import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.entity_resolution import (
    STRONG_IDENTITY_KINDS,
    FounderCandidate,
    artifact_ids_by_founder,
    compact_person_name,
    is_person_name,
    resolve_candidates,
    review_fingerprint,
)
from app.identity import ALL_KINDS, parse_identity
from app.models import (
    Founder,
    FounderResolutionReview,
    Identity,
    JobRun,
    Signal,
    TraceStep,
    founder_signal,
)
from app.places import apply_location

log = logging.getLogger(__name__)


def _norm_name(s: str | None) -> str:
    """Canonical key for founder-name matching.

    Accent-folds + lowercases, strips leading honorifics (Prof./Dr./...), and reduces a person
    name to its stable first + last shape. This lets sources omit either a middle initial or a
    full middle name; automatic merging still needs independent identity or context evidence.
    """
    return compact_person_name(s)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _incoming_candidate(f: dict, artifact_ids: tuple[str, ...] = ()) -> FounderCandidate:
    ident = f.get("identity") or {}
    return FounderCandidate(
        display_name=f.get("display_name"),
        city=f.get("city"),
        current_company=f.get("current_company"),
        artifact_ids=artifact_ids,
        github=ident.get("github"),
        linkedin=ident.get("linkedin"),
        twitter=ident.get("twitter"),
        orcid=ident.get("orcid"),
        website=ident.get("website"),
        education=tuple(str(x) for x in (f.get("education") or [])),
    )


def _identity_values(founder: Founder, field: str) -> tuple[str, ...] | None:
    values = tuple(
        value for identity in founder.identities if (value := getattr(identity, field)) is not None
    )
    return values or None


@dataclass(frozen=True)
class Resolution:
    """Outcome of resolving one incoming mention against the known population."""

    founder_id: uuid.UUID | None
    method: str | None
    needs_review: bool = False
    # The person this mention contradicted, when it is being kept apart from them. Recorded so a
    # fork is a visible, reviewable pair rather than two unrelated-looking rows.
    counterpart_id: uuid.UUID | None = None
    conflict_kinds: tuple[str, ...] = ()


def _resolve(db: Session, f: dict, artifact_ids: tuple[str, ...] = ()) -> Resolution:
    """Resolve one incoming person against every known founder.

    A ``review`` verdict deliberately returns the MATCHED founder rather than nothing. Minting a
    fresh Founder row for an unresolved mention is what fragmented the Founder Score into 12
    duplicate pairs; an uncertain match is recorded on the person we already have, not as a new
    human. The one exception is a strong-identity conflict, which signals genuinely distinct
    people (or a bad identity) and must stay separate — see `FounderResolutionReview`.
    """
    incoming = _incoming_candidate(f, artifact_ids)
    # Ordered, not incidental: `resolve_candidates` breaks a tie with a strict `>`, so the first
    # candidate handed to it wins. Unordered, that was whichever row the scan happened to return —
    # free to change after any UPDATE or VACUUM — and the same mention would attach to a different
    # human between runs, taking their Founder Score with it. Earliest discovery wins, the rule
    # `find_merge_candidates` already uses.
    founders = (
        db.execute(
            select(Founder)
            .options(selectinload(Founder.identities))
            .order_by(Founder.first_discovered_at.nullsfirst(), Founder.id)
        )
        .scalars()
        .all()
    )
    artifacts = artifact_ids_by_founder(db)
    candidates = []
    for founder in founders:
        candidates.append(
            FounderCandidate(
                founder_id=str(founder.id),
                display_name=founder.display_name,
                city=founder.city,
                current_company=founder.current_company,
                artifact_ids=artifacts.get(str(founder.id), ()),
                github=_identity_values(founder, "github"),
                linkedin=_identity_values(founder, "linkedin"),
                twitter=_identity_values(founder, "twitter"),
                orcid=_identity_values(founder, "orcid"),
                website=_identity_values(founder, "website"),
                education=tuple(str(x) for x in (founder.education or [])),
            )
        )
    result = resolve_candidates(incoming, candidates)
    if result.decision == "merge" and result.matched_id:
        method = (
            "exact_key"
            if any(key in result.reasons for key in STRONG_IDENTITY_KINDS)
            else "artifact"
            if "artifact" in result.reasons
            else "evidence"
        )
        return Resolution(uuid.UUID(result.matched_id), method)
    if result.decision == "review" and result.matched_id and not result.conflicts:
        return Resolution(uuid.UUID(result.matched_id), "review", needs_review=True)
    if result.decision == "review":
        # Conflicting strong identities. The two are kept apart — attaching one human's evidence
        # to another is undetectable and has no undo, while a fork is found by
        # find_merge_candidates and reversed by merge_founders — but the pair is recorded so the
        # split is reviewable instead of silent.
        return Resolution(
            None,
            "conflict",
            needs_review=True,
            counterpart_id=uuid.UUID(result.matched_id) if result.matched_id else None,
            conflict_kinds=result.conflicts,
        )
    return Resolution(None, None)


def _new_founder(
    db: Session, f: dict, *, status: str = "candidate", withheld: list[str]
) -> Founder:
    founder = Founder(
        display_name=f["display_name"],
        first_name=f.get("first_name"),
        last_name=f.get("last_name"),
        occupation=f.get("occupation"),
        current_company=f.get("current_company"),
        education=f.get("education"),
        status=status,
        discovery_confidence=f.get("discovery_confidence"),
        first_discovered_at=_parse_dt(f.get("first_discovered_at")) or datetime.now(UTC),
        last_checked_at=datetime.now(UTC),
    )
    db.add(founder)
    # After `education` is set: the place resolver reads the founder's affiliations to tell
    # namesake cities apart.
    apply_location(db, founder, f.get("city"))
    db.flush()
    fields, held_back = withhold_claimed_identity(db, canonical_identity_fields(f))
    withheld.extend(held_back)
    db.add(Identity(founder_id=founder.id, **fields))
    # The session runs with autoflush=False, so without this the identity stays invisible to the
    # next candidate in the same delivery and the same person resolves twice.
    db.flush()
    return founder


def canonical_identity_fields(f: dict) -> dict[str, str | None]:
    """The identity columns to store: canonical tokens only, never a raw URL or a non-profile page.

    Canonicalizing at the write boundary rather than at each comparison is what makes the stored
    value BE the identity — the resolver, the review fingerprint and the unique indexes then all
    agree without each re-deriving it.
    """
    incoming = f.get("identity") or {}
    return {kind: parse_identity(kind, incoming.get(kind)).value for kind in ALL_KINDS}


# Kinds carrying a GLOBAL uniqueness guarantee in the schema. A github login can legitimately sit
# on six co-founders (an organisation account); an ORCID cannot sit on two researchers.
_EXCLUSIVE_KINDS = ("orcid",)


def withhold_claimed_identity(
    db: Session, fields: dict[str, str | None], *, founder_id: uuid.UUID | None = None
) -> tuple[dict[str, str | None], list[str]]:
    """Drop values a *different* founder already holds under a global unique index.

    Handing the database a value it is about to reject is not a validation failure, it is a lost
    run: `persist_delivery` writes one transaction, so a single `uq_identity_orcid` violation
    rolls back every founder and signal in the delivery. That happened live — the extractor put
    one invented ORCID on two different people in one batch and 40+ founders were lost with it.

    Two people publishing one ORCID means one of the two records is wrong, so the value is not
    evidence about either and is withdrawn from the second, exactly as `non_identifying_handles`
    withdraws a shared organisation handle from merge evidence. It is returned as a reason so the
    operator sees a count instead of a silent drop.
    """
    kept, withheld = dict(fields), []
    for kind in _EXCLUSIVE_KINDS:
        value = fields.get(kind)
        if value is None:
            continue
        column = getattr(Identity, kind)
        query = select(Identity.founder_id).where(func.lower(column) == value.lower())
        if founder_id is not None:
            query = query.where(Identity.founder_id != founder_id)
        holder = db.scalar(query)
        if holder is not None:
            kept[kind] = None
            withheld.append(kind)
            log.warning(
                "identity.withheld kind=%s value=%s already held by founder=%s", kind, value, holder
            )
    return kept, withheld


def identity_artifact_payloads(f: dict) -> list[dict]:
    """Signal payloads for identity values that are real artifacts but identify nobody.

    A LinkedIn post or company page is genuine evidence about this founder; it simply is not their
    identifier. Keeping it as one made two people's post URLs read as proof they were two people.
    """
    incoming = f.get("identity") or {}
    payloads = []
    for kind in ALL_KINDS:
        parsed = parse_identity(kind, incoming.get(kind))
        if parsed.artifact_url:
            payloads.append(
                {
                    "source": "linkedin" if kind == "linkedin" else kind,
                    "signal_type": "profile_activity",
                    "canonical_url": parsed.artifact_url,
                    "url": parsed.raw,
                    "title": None,
                    "summary": None,
                    "source_reliability": 0.55,
                    "sources_seen": [kind],
                }
            )
    return payloads


_IDENTITY_FIELDS = ("github", "twitter", "linkedin", "website", "orcid")


def _enrich_identity(db: Session, founder: Founder, f: dict, withheld: list[str]) -> None:
    """Persist newly discovered handles onto an already-known founder.

    Research rounds surface a person's LinkedIn/GitHub non-deterministically. Discarding a handle
    found on a later pass kept the strong-identity tier permanently unable to fire, which is why
    re-discovery fell through to a duplicate.
    """
    known = {
        field: {getattr(identity, field) for identity in founder.identities} - {None}
        for field in _IDENTITY_FIELDS
    }
    # Compare canonical against canonical: the same profile arriving as a URL after being stored
    # as a bare handle used to look "fresh" and inserted a second row for one account.
    incoming, held_back = withhold_claimed_identity(
        db, canonical_identity_fields(f), founder_id=founder.id
    )
    withheld.extend(held_back)
    fresh = {
        field: value for field, value in incoming.items() if value and value not in known[field]
    }
    if not fresh:
        return
    db.add(Identity(founder_id=founder.id, **fresh))
    db.flush()


def _record_review(
    db: Session,
    f: dict,
    artifact_ids: tuple[str, ...],
    founder_id,
    *,
    counterpart_id: uuid.UUID | None = None,
    conflict_kinds: tuple[str, ...] = (),
) -> None:
    """Record an unresolved mention against the founder it was attached to, once per fingerprint."""
    fingerprint = review_fingerprint(_incoming_candidate(f, artifact_ids))
    exists = db.scalar(
        select(FounderResolutionReview.id).where(FounderResolutionReview.fingerprint == fingerprint)
    )
    if exists is None:
        db.add(
            FounderResolutionReview(
                fingerprint=fingerprint,
                founder_id=founder_id,
                counterpart_founder_id=counterpart_id,
                conflict_kinds=",".join(conflict_kinds) or None,
            )
        )
        db.flush()


_FOUNDER_WRITER_LOCK = 437_117


def _lock_founder_writes(db: Session) -> None:
    """Serialize founder resolution across processes, in the writer rather than at one caller.

    Resolution reads every founder and then decides whether to create one, so two processes
    doing it concurrently can both conclude "new" for the same person and mint the duplicate the
    resolver exists to prevent. Guarding the discovery cron alone was not enough — the inbound
    deck intake calls this same function with no lock at all, from a request handler, so the two
    funnels could race each other. The lock belongs to the write, not to one of its callers.

    Transaction-scoped and BLOCKING: a second writer must wait its turn and then see the first
    one's rows, not skip the person. Released by the caller's commit or rollback. Re-taking it
    per candidate in a delivery loop is free — Postgres reference-counts a lock already held.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _FOUNDER_WRITER_LOCK})


def resolve_or_create_founder(
    db: Session,
    f: dict,
    artifact_ids: tuple[str, ...] = (),
    *,
    withheld: list[str] | None = None,
) -> tuple[uuid.UUID, str]:
    """Resolve a founder dict to an existing founder, or create one. Returns (founder_id, method).

    method in {"exact_key", "artifact", "evidence", "review", "conflict", "created"}. Shared by the
    discovery persist path and the inbound intake so BOTH funnels attach the same person through
    the one resolver (_resolve) — ArgOS is founder-first, every opportunity needs a person.
    `withheld` collects the identity kinds this call refused to store because another founder
    already holds them under a global unique index. Optional: a caller that does not want the
    count still gets the protection, since the refusal happens in the writer.

    Flushes; the caller commits.
    """
    _lock_founder_writes(db)
    withheld = withheld if withheld is not None else []
    resolution = _resolve(db, f, artifact_ids)
    if resolution.founder_id is not None:
        founder = db.get(Founder, resolution.founder_id)
        _enrich_identity(db, founder, f, withheld)
        if resolution.needs_review:
            founder.status = "needs_review"
            _record_review(db, f, artifact_ids, resolution.founder_id)
        return resolution.founder_id, resolution.method or "evidence"
    founder = _new_founder(
        db,
        f,
        status="needs_review" if resolution.needs_review else f.get("status", "candidate"),
        withheld=withheld,
    )
    if resolution.needs_review:
        _record_review(
            db,
            f,
            artifact_ids,
            founder.id,
            counterpart_id=resolution.counterpart_id,
            conflict_kinds=resolution.conflict_kinds,
        )
        if resolution.counterpart_id is not None:
            # Both rows are flagged: whichever the reviewer opens, the open question is visible.
            counterpart = db.get(Founder, resolution.counterpart_id)
            if counterpart is not None:
                counterpart.status = "needs_review"
            log.info(
                "resolution.fork founder=%s counterpart=%s conflicts=%s",
                founder.id,
                resolution.counterpart_id,
                ",".join(resolution.conflict_kinds),
            )
    return founder.id, "conflict" if resolution.method == "conflict" else "created"


def persist_delivery(
    db: Session, founders: list[dict], *, source: str = "discovery", commit: bool = True
) -> dict:
    job = JobRun(source=source)
    db.add(job)
    db.flush()

    existing_signals = db.execute(select(Signal)).scalars().all()
    signals_by_url = {
        signal.canonical_url: signal for signal in existing_signals if signal.canonical_url
    }
    signals_by_hash = {
        signal.content_hash: signal for signal in existing_signals if signal.content_hash
    }

    def materialize_signal(payload: dict) -> tuple[Signal | None, bool]:
        """Return the global artifact, creating it only once.

        Reusing an existing artifact is deliberate: attribution is recorded separately in
        ``founder_signal``, so one team/page artifact can support every referenced founder.
        """
        canon = payload.get("canonical_url")
        content_hash = payload.get("content_hash")
        if not canon:
            return None, False
        existing = signals_by_url.get(canon) or (
            signals_by_hash.get(content_hash) if content_hash else None
        )
        if existing is not None:
            # Dual use is legitimate — one URL can be evidence about a founder AND about a
            # market, and (source, external_id) is unique so both uses share this row. Promote
            # it: a market artifact about to gain founder attribution must not stay 'market',
            # or it would sit in the founder pipeline while claiming otherwise.
            if existing.kind == "market":
                existing.kind = "founder"
            return existing, False
        signal = Signal(
            source=payload["source"],
            signal_type=payload["signal_type"],
            kind="founder",
            external_id=canon,
            canonical_url=canon,
            content_hash=content_hash,
            url=payload.get("url"),
            title=payload.get("title"),
            summary=payload.get("summary"),
            occurred_at=_parse_dt(payload.get("occurred_at")),
            source_reliability=payload.get("source_reliability"),
            resolution_confidence=payload.get("resolution_confidence"),
            resolution_method=payload.get("resolution_method"),
            sources_seen=payload.get("sources_seen"),
            raw=payload,
        )
        db.add(signal)
        db.flush()
        signals_by_url[canon] = signal
        if content_hash:
            signals_by_hash[content_hash] = signal
        return signal, True

    new_founders = 0
    new_signals = 0
    resolved = 0
    dropped_no_evidence = 0
    dropped_non_person = 0
    # Identity values that named no person, by reason. Reported rather than silently discarded so
    # a change in what the extractor emits is visible instead of quietly shrinking the evidence.
    dropped_identity: Counter[str] = Counter()
    rerouted_identity = 0

    for f in founders:
        # Personhood is decided at the single writer, so no caller can put an event or an
        # organisation into the founder table regardless of what upstream extraction produced.
        if not is_person_name(f.get("display_name")):
            dropped_non_person += 1
            continue
        # Materialize evidence first. A new outbound founder is never created without at
        # least one attributable artifact; invalid/empty research output is discarded.
        attributed_signals: list[tuple[Signal, dict]] = []
        created_signal_ids: list[str] = []
        seen_signal_ids: set[uuid.UUID] = set()
        incoming_identity = f.get("identity") or {}
        for kind in ALL_KINDS:
            parsed = parse_identity(kind, incoming_identity.get(kind))
            if parsed.rejected and parsed.rejected != "empty":
                dropped_identity[f"{kind}:{parsed.rejected}"] += 1
        # A post/company page keeps its evidentiary value as an artifact; it is only its use as
        # an identifier that is withdrawn.
        identity_artifacts = identity_artifact_payloads(f)
        rerouted_identity += len(identity_artifacts)
        for payload in [*f.get("signals", []), *identity_artifacts]:
            signal, created = materialize_signal(payload)
            if signal is None or signal.id in seen_signal_ids:
                continue
            seen_signal_ids.add(signal.id)
            attributed_signals.append((signal, payload))
            if created:
                created_signal_ids.append(str(signal.id))
                new_signals += 1
        if not attributed_signals:
            dropped_no_evidence += 1
            continue

        # The artifacts we just materialized are the resolution evidence: an artifact already
        # attributed to a founder identifies that person more precisely than any name comparison.
        artifact_ids = tuple(
            signal.canonical_url for signal, _ in attributed_signals if signal.canonical_url
        )
        withheld: list[str] = []
        fid, method = resolve_or_create_founder(db, f, artifact_ids, withheld=withheld)
        for kind in withheld:
            # Same counter as a rejected value: in both cases the value reached the writer and
            # did not become an identity, and the operator needs the number either way.
            dropped_identity[f"{kind}:claimed"] += 1
        if method in {"created", "conflict"}:
            founder = db.get(Founder, fid)
            new_founders += 1
        else:
            resolved += 1
            founder = db.get(Founder, fid)
            founder.last_checked_at = datetime.now(UTC)
            if f.get("discovery_confidence"):
                founder.discovery_confidence = max(
                    founder.discovery_confidence or 0.0, f["discovery_confidence"]
                )
            if not founder.city and f.get("city"):
                # Through the single writer: this path used to set `.city` alone and leave the
                # place id, key, country and quality NULL — a founder who looks located and
                # fails every place invariant in `maintenance.audit_identity`.
                apply_location(db, founder, f["city"])
            for attr in ("occupation", "current_company"):
                if not getattr(founder, attr) and f.get(attr):
                    setattr(founder, attr, f[attr])

        for signal, payload in attributed_signals:
            statement = insert(founder_signal).values(
                founder_id=fid,
                signal_id=signal.id,
                attribution_confidence=payload.get("resolution_confidence"),
                attribution_method=payload.get("resolution_method"),
            )
            # Attribution quality must be monotonic: re-discovering an artifact once identity is
            # better known should raise its confidence, never be discarded as a duplicate key.
            db.execute(
                statement.on_conflict_do_update(
                    index_elements=["founder_id", "signal_id"],
                    set_={
                        "attribution_confidence": func.greatest(
                            func.coalesce(founder_signal.c.attribution_confidence, 0.0),
                            func.coalesce(statement.excluded.attribution_confidence, 0.0),
                        ),
                        "attribution_method": func.coalesce(
                            statement.excluded.attribution_method,
                            founder_signal.c.attribution_method,
                        ),
                    },
                    where=func.coalesce(statement.excluded.attribution_confidence, 0.0)
                    > func.coalesce(founder_signal.c.attribution_confidence, 0.0),
                )
            )

        if fid:
            # Agentic traceability (stretch #1): record what sourcing did for this founder.
            db.add(
                TraceStep(
                    founder_id=fid,
                    stage="sourcing",
                    agent="discovery",
                    input={"candidate": f.get("display_name")},
                    output={
                        "resolved": "new_founder"
                        if method in {"created", "conflict"}
                        else "existing",
                        "resolution_method": method or "created",
                        "new_signals": len(created_signal_ids),
                        "attributed_signals": len(attributed_signals),
                        "discovery_confidence": f.get("discovery_confidence"),
                    },
                    evidence_ids=[str(signal.id) for signal, _ in attributed_signals],
                )
            )

    job.finished_at = datetime.now(UTC)
    job.new_signals = new_signals
    if commit:
        db.commit()
    else:
        db.flush()
    # This runs unattended under cron and mutates person records. Without a line per run there is
    # no way to tell a quiet night from a resolver that stopped resolving.
    log.info(
        "persist[%s]: %d candidates -> %d new, %d resolved, %d signals | dropped "
        "no_evidence=%d non_person=%d identity=%s | rerouted %d",
        source,
        len(founders),
        new_founders,
        resolved,
        new_signals,
        dropped_no_evidence,
        dropped_non_person,
        dict(dropped_identity) or "-",
        rerouted_identity,
    )
    return {
        "new_founders": new_founders,
        "resolved_to_existing": resolved,
        "new_signals": new_signals,
        # Candidates discarded for having no attributable artifact. Reported so a silent drop
        # of thin-footprint (cold-start) founders is visible to the operator.
        "dropped_no_evidence": dropped_no_evidence,
        "dropped_non_person": dropped_non_person,
        # Identity values that identified nobody: rejected outright (by reason), or kept as
        # evidence but withdrawn as an identifier.
        "dropped_identity": dict(dropped_identity),
        "rerouted_identity_artifacts": rerouted_identity,
        "job_run_id": str(job.id),
    }
