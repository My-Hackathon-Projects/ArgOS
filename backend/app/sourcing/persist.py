"""Single-writer persist step (Q10 ⑥⑦). Resolves each founder, dedups + writes signals.

Resolution ladder (MVP cut): strong-id exact → normalized-name exact → create new.
Fuzzy/LLM tiers are additive later; strong-id + normalized-name keeps re-runs idempotent
without false-merging on a bare shared name.
"""

import unicodedata
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Founder, Identity, JobRun, Signal

_STRONG_KEYS = ("github", "twitter", "linkedin", "website", "orcid")


def _norm_name(s: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", (s or "").lower().strip())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.split())


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolve(db: Session, f: dict) -> tuple[object | None, str | None]:
    ident = f.get("identity") or {}
    for key in _STRONG_KEYS:
        val = ident.get(key)
        if val:
            row = (
                db.execute(select(Identity).where(getattr(Identity, key) == val)).scalars().first()
            )
            if row:
                return row.founder_id, "exact_key"
    target = _norm_name(f["display_name"])
    if target:
        for fid, name in db.execute(select(Founder.id, Founder.display_name)).all():
            if _norm_name(name) == target:
                return fid, "fuzzy"
    return None, None


def persist_delivery(db: Session, founders: list[dict]) -> dict:
    job = JobRun(source="discovery")
    db.add(job)
    db.flush()

    seen_urls = {
        u
        for (u,) in db.execute(select(Signal.canonical_url).where(Signal.canonical_url.isnot(None)))
    }
    seen_hashes = {
        h for (h,) in db.execute(select(Signal.content_hash).where(Signal.content_hash.isnot(None)))
    }

    new_founders = 0
    new_signals = 0
    resolved = 0

    for f in founders:
        fid, method = _resolve(db, f)
        if fid is None:
            founder = Founder(
                display_name=f["display_name"],
                first_name=f.get("first_name"),
                last_name=f.get("last_name"),
                city=f.get("city"),
                occupation=f.get("occupation"),
                current_company=f.get("current_company"),
                education=f.get("education"),
                status=f.get("status", "candidate"),
                discovery_confidence=f.get("discovery_confidence"),
                first_discovered_at=_parse_dt(f.get("first_discovered_at")) or datetime.now(UTC),
                last_checked_at=datetime.now(UTC),
            )
            db.add(founder)
            db.flush()
            fid = founder.id
            new_founders += 1
            ident = f.get("identity") or {}
            db.add(
                Identity(
                    founder_id=fid,
                    github=ident.get("github"),
                    twitter=ident.get("twitter"),
                    linkedin=ident.get("linkedin"),
                    website=ident.get("website"),
                    orcid=ident.get("orcid"),
                )
            )
        else:
            resolved += 1
            founder = db.get(Founder, fid)
            founder.last_checked_at = datetime.now(UTC)
            if f.get("discovery_confidence"):
                founder.discovery_confidence = max(
                    founder.discovery_confidence or 0.0, f["discovery_confidence"]
                )
            for attr in ("city", "occupation", "current_company"):
                if not getattr(founder, attr) and f.get(attr):
                    setattr(founder, attr, f[attr])

        for s in f.get("signals", []):
            canon = s.get("canonical_url")
            chash = s.get("content_hash")
            if not canon or canon in seen_urls or (chash and chash in seen_hashes):
                continue  # dedup (Q5): same artifact URL or same content
            seen_urls.add(canon)
            if chash:
                seen_hashes.add(chash)
            db.add(
                Signal(
                    source=s["source"],
                    signal_type=s["signal_type"],
                    external_id=canon,
                    canonical_url=canon,
                    content_hash=chash,
                    url=s.get("url"),
                    title=s.get("title"),
                    summary=s.get("summary"),
                    occurred_at=_parse_dt(s.get("occurred_at")),
                    source_reliability=s.get("source_reliability"),
                    resolution_confidence=s.get("resolution_confidence"),
                    resolution_method=s.get("resolution_method"),
                    sources_seen=s.get("sources_seen"),
                    founder_id=fid,
                    raw=s,
                )
            )
            new_signals += 1

    job.finished_at = datetime.now(UTC)
    job.new_signals = new_signals
    db.commit()
    return {
        "new_founders": new_founders,
        "resolved_to_existing": resolved,
        "new_signals": new_signals,
        "job_run_id": str(job.id),
    }
