"""Withdraw the handles a lookalike host produced.

`app.identity._segments` decided whether a URL belonged to GitHub/X/LinkedIn with `known in host`
— substring containment. `catalyzex.com` contains `x.com`, so
`https://catalyzex.com/author/Felix%20Brakel` parsed as a Twitter profile and stored the handle
`author`; `adscientificindex.com/scientist/<name>` stored `scientist` the same way.

That is a wrong assignment, not merely an ugly value. `twitter` is one of the four kinds the
resolver treats as person-unique evidence, so another site's URL structure was sitting in a
column used to decide whether two rows are the same human — `author` on five founders and
`scientist` on two. Nothing merged wrongly only because `non_identifying_handles` withdraws any
handle several people claim, which is a safety net, not the intended behaviour.

Identifying them from the stored value alone is impossible: `author` is a shape-valid handle.
So they are identified the way they were created — a value is withdrawn when the OLD containment
rule would derive it from one of that founder's own signal URLs on a host that is not really the
site, and the FIXED rule derives it from none of them. That leaves untouched the ~30 handles that
no artifact corroborates but which are plainly correct (`dfull` on David Full, `theophilegervet`
on Theophile Gervet) — those come from the research synthesis, not from a URL, so the old rule
could not have produced them either.

Both rules are FROZEN COPIES, per 0011/0015/0016: the migration must keep reproducing this result
after `app.identity` changes again.
"""

from urllib.parse import unquote, urlsplit

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels = None
depends_on = None

_KINDS = ("github", "twitter", "linkedin")
_HOSTS = {
    "github": ("github.com",),
    "twitter": ("twitter.com", "x.com"),
    "linkedin": ("linkedin.com", "linkedin."),
}


def _host_of(url: str) -> str:
    return urlsplit(url).netloc.casefold().removeprefix("www.").split(":")[0]


def _matched_before(host: str, known: str) -> bool:
    """The defect: containment anywhere in the host."""
    return known in host


def _matched_after(host: str, known: str) -> bool:
    """Frozen copy of app.identity._host_matches."""
    if known.endswith("."):
        return host.startswith(known) or host.endswith(f".{known.rstrip('.')}.com")
    return host == known or host.endswith(f".{known}")


def _first_segment(kind: str, url: str) -> str | None:
    """The token the parser would have taken as the handle for this kind."""
    segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    if not segments:
        return None
    if kind == "linkedin":
        head = segments[0].casefold()
        if head in ("in", "pub"):
            return unquote(segments[1]).casefold() if len(segments) > 1 else None
        return unquote(segments[0]).casefold()
    if kind == "twitter" and len(segments) >= 2 and segments[1].casefold() == "status":
        return None
    return segments[0].casefold()


def upgrade() -> None:
    bind = op.get_bind()
    urls: dict[str, list[str]] = {}
    for founder_id, url in bind.execute(
        sa.text(
            "SELECT fs.founder_id, s.canonical_url FROM founder_signal fs "
            "JOIN signal s ON s.id = fs.signal_id WHERE s.canonical_url IS NOT NULL"
        )
    ):
        urls.setdefault(str(founder_id), []).append(url)

    withdrawn = 0
    for row in bind.execute(
        sa.text(f"SELECT id, founder_id, {', '.join(_KINDS)} FROM identity")
    ).mappings():
        clear = []
        for kind in _KINDS:
            value = row[kind]
            if value is None:
                continue
            from_lookalike = legitimate = False
            for url in urls.get(str(row["founder_id"]), []):
                host = _host_of(url)
                if _first_segment(kind, url) != value:
                    continue
                if any(_matched_after(host, known) for known in _HOSTS[kind]):
                    legitimate = True
                elif any(_matched_before(host, known) for known in _HOSTS[kind]):
                    from_lookalike = True
            if from_lookalike and not legitimate:
                clear.append(kind)
        if clear:
            bind.execute(
                sa.text(
                    f"UPDATE identity SET {', '.join(f'{k} = NULL' for k in clear)} WHERE id = :id"
                ),
                {"id": row["id"]},
            )
            withdrawn += len(clear)
    print(f"[0017] withdrew {withdrawn} handle(s) derived from a lookalike host")


def downgrade() -> None:
    raise NotImplementedError(
        "0017 nulls handles that never identified anyone; the values are not worth restoring. "
        "Restore from a backup taken before the upgrade."
    )
