"""URL canonicalization — one artifact, one signal row.

`canonical_url` is the global dedup key for artifacts, and `(source, external_id)` is the
idempotency key for polling. Both are only as good as `_canonicalize`: any URL form it leaves
distinct becomes a second row for the same artifact.

That is not cosmetic. Claim trust is noisy-OR over evidence weights, so the same artifact cited
twice reads as two independent corroborations — one source at w=0.6 scores 0.6, the same source
duplicated scores 0.84, and `corroboration_n` reports 2. Ten live claims were inflated exactly
this way:

    "Pedro Abreu hosts the Type Theory Forall Podcast"  trust 0.5184  n=2  <- http+https
    "Flavio Rump is Entrepreneur-in-Residence at ETH"   trust 0.5184  n=2  <- x.com case
    "Daniel San José Pro co-authored 'CRISP...'"        trust 0.9030  n=2  <- arXiv abs + pdf
"""

from app.sourcing.graph import _canonicalize


def test_scheme_does_not_create_a_second_artifact():
    """http and https of one page are one page. Observed live on pedroabreu0.github.io."""
    assert _canonicalize("http://pedroabreu0.github.io/") == _canonicalize(
        "https://pedroabreu0.github.io/"
    )


def test_handle_hosts_are_case_insensitive():
    """x.com/FlavioRump and x.com/flaviorump are the same profile — the host says so."""
    assert _canonicalize("https://x.com/FlavioRump") == _canonicalize("https://x.com/flaviorump")
    assert _canonicalize("https://github.com/Torvalds") == _canonicalize(
        "https://github.com/torvalds"
    )
    assert _canonicalize("https://www.linkedin.com/in/Ada-Lovelace") == _canonicalize(
        "https://linkedin.com/in/ada-lovelace"
    )


def test_path_case_is_preserved_for_ordinary_hosts():
    """Most servers ARE case-sensitive — blanket lowercasing would merge distinct pages."""
    assert _canonicalize("https://example.test/Paper") != _canonicalize(
        "https://example.test/paper"
    )


def test_arxiv_forms_of_one_paper_collapse():
    """abs / pdf / html and version suffixes are renderings of a single paper."""
    forms = [
        "https://arxiv.org/abs/2408.00776",
        "https://arxiv.org/pdf/2408.00776",
        "https://arxiv.org/html/2408.00776v1",
        "https://arxiv.org/html/2408.00776v2",
        "https://arxiv.org/pdf/2408.00776v3",
        "http://www.arxiv.org/abs/2408.00776",
    ]
    canonical = {_canonicalize(f) for f in forms}
    assert len(canonical) == 1, canonical
    assert canonical == {"https://arxiv.org/abs/2408.00776"}


def test_distinct_arxiv_papers_stay_distinct():
    assert _canonicalize("https://arxiv.org/abs/2408.00776") != _canonicalize(
        "https://arxiv.org/abs/2408.00777"
    )


def test_existing_normalisation_still_holds():
    """www, tracking params, trailing slash and fragments were already handled — keep them."""
    assert _canonicalize("https://www.example.test/a/") == _canonicalize("https://example.test/a")
    assert _canonicalize("https://example.test/a?utm_source=x") == _canonicalize(
        "https://example.test/a"
    )
    assert _canonicalize("https://example.test/a#section") == _canonicalize(
        "https://example.test/a"
    )
    # a meaningful query parameter is NOT dropped
    assert _canonicalize("https://example.test/a?id=7") != _canonicalize("https://example.test/a")


def test_canonicalize_is_idempotent():
    """Re-canonicalizing a stored key must not move it, or dedup drifts between runs."""
    for url in [
        "http://www.arxiv.org/pdf/2408.00776v2",
        "https://x.com/FlavioRump",
        "https://example.test/a?utm_source=x&id=7",
        "https://pedroabreu0.github.io/",
    ]:
        once = _canonicalize(url)
        assert _canonicalize(once) == once, url


def test_ar5iv_renderer_is_the_same_paper():
    """ar5iv.labs.arxiv.org is arXiv's own HTML view — a different host, one artifact."""
    assert _canonicalize("https://ar5iv.labs.arxiv.org/html/2009.10632") == _canonicalize(
        "https://arxiv.org/abs/2009.10632"
    )
