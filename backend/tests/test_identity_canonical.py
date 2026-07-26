"""Canonical identity: one value shape per kind, and what the resolver does with it.

The bug these cover: a strong identifier is person-unique, so "both sides publish this kind and
the values differ" was read as PROOF of distinctness. Any normalizer miss was therefore upgraded
into a confident wrong answer — a forked person and a reset Founder Score — rather than a missed
merge. Every case below is a spelling the resolver used to call two different people.
"""

import pytest

from app.entity_resolution import FounderCandidate, resolve_candidates
from app.identity import canonical_identity, orcid_checksum_ok, parse_identity, profile_url


class TestCanonicalToken:
    @pytest.mark.parametrize(
        "kind,left,right",
        [
            ("orcid", "0000-0002-1825-0097", "https://orcid.org/0000-0002-1825-0097"),
            ("orcid", "0000-0002-1825-0097", "0000000218250097"),
            ("github", "ada-lovelace", "https://github.com/ada-lovelace"),
            ("github", "Ada-Lovelace", "ada-lovelace"),
            ("github", "ada-lovelace", "https://github.com/ada-lovelace/"),
            ("twitter", "@ada", "https://twitter.com/ada"),
            ("twitter", "@ada", "https://x.com/Ada"),
            ("linkedin", "/in/AdaLovelace", "/in/adalovelace"),
            ("linkedin", "https://www.linkedin.com/in/adalovelace", "linkedin.com/in/AdaLovelace"),
        ],
    )
    def test_same_identifier_two_spellings_is_one_token(self, kind, left, right):
        assert canonical_identity(kind, left) == canonical_identity(kind, right) is not None

    def test_orcid_checksum_rejects_a_typo(self):
        assert orcid_checksum_ok("0000000218250097")
        assert not orcid_checksum_ok("0000000218250098")
        assert parse_identity("orcid", "0000-0002-1825-0098").rejected == "checksum"
        assert canonical_identity("orcid", "0000-0002-1825-0098") is None

    @pytest.mark.parametrize(
        "kind,raw",
        [("github", "https://github.com/orgs"), ("twitter", "https://twitter.com/i")],
    )
    def test_reserved_site_paths_are_not_people(self, kind, raw):
        assert parse_identity(kind, raw).rejected == "reserved"

    def test_unknown_kind_fails_loudly(self):
        with pytest.raises(ValueError, match="unknown identity kind"):
            parse_identity("mastodon", "@ada@example.org")

    def test_display_url_is_derived_from_the_token(self):
        assert profile_url(
            "orcid", canonical_identity("orcid", "https://orcid.org/0000-0002-1825-0097")
        ) == ("https://orcid.org/0000-0002-1825-0097")
        assert profile_url("linkedin", canonical_identity("linkedin", "/in/AdaLovelace")) == (
            "https://www.linkedin.com/in/adalovelace"
        )


class TestNotAnIdentifier:
    """A LinkedIn post is real evidence about a person, but it identifies nobody.

    Two people who each posted have different post URLs, which the disjoint rule read as proof
    they were different humans. These are kept as artifacts and removed from identity.
    """

    @pytest.mark.parametrize(
        "raw",
        [
            "https://www.linkedin.com/posts/nicolas-keller_munich-activity-7212",
            "https://linkedin.com/company/analytical-engines",
            "https://linkedin.com/school/tum",
            "https://linkedin.com/feed/update/urn:li:activity:123",
        ],
    )
    def test_non_profile_linkedin_becomes_an_artifact_not_an_identity(self, raw):
        parsed = parse_identity("linkedin", raw)
        assert parsed.value is None, "must never be used as identity"
        assert parsed.artifact_url, "must survive as evidence"

    def test_tweet_permalink_is_an_artifact_not_a_handle(self):
        parsed = parse_identity("twitter", "https://x.com/ada/status/123456")
        assert parsed.value is None
        assert parsed.artifact_url

    def test_a_linkedin_url_in_the_twitter_column_is_rejected(self):
        # Observed live: one identity row had a linkedin.com/in/ URL stored under `twitter`.
        assert parse_identity("twitter", "https://www.linkedin.com/in/karmedge/").rejected == (
            "wrong_host"
        )


class TestResolverNoLongerForks:
    """Each case previously produced CONFIDENCE_CONFLICT -> a second Founder row."""

    @pytest.mark.parametrize(
        "kind,incoming,existing",
        [
            ("orcid", "0000-0002-1825-0097", "https://orcid.org/0000-0002-1825-0097"),
            ("github", "ada-lovelace", "https://github.com/ada-lovelace"),
            ("linkedin", "/in/AdaLovelace", "/in/adalovelace"),
            ("twitter", "@ada", "https://twitter.com/ada"),
        ],
    )
    def test_one_identifier_two_spellings_merges(self, kind, incoming, existing):
        result = resolve_candidates(
            FounderCandidate("Ada Lovelace", **{kind: incoming}),
            [FounderCandidate("Ada Lovelace", founder_id="x", **{kind: existing})],
        )
        assert result.decision == "merge"
        assert not result.conflicts

    def test_shared_identity_outranks_a_disjoint_one(self):
        """One person with an old vanity LinkedIn and a new numeric one still has one GitHub."""
        result = resolve_candidates(
            FounderCandidate(
                "Andreas Mueller", github="amueller", linkedin="https://linkedin.com/in/amueller"
            ),
            [
                FounderCandidate(
                    "Andreas Müller",
                    founder_id="x",
                    github="amueller",
                    linkedin="https://linkedin.com/in/andreas-mueller-123",
                )
            ],
        )
        assert result.decision == "merge", "a shared person-unique handle is the strongest evidence"
        assert result.evidence["linkedin"] == "disjoint_noted"

    def test_genuine_homonyms_with_different_profiles_stay_apart(self):
        """The safe direction: two real people sharing a name must not collapse."""
        result = resolve_candidates(
            FounderCandidate("John Smith", linkedin="https://linkedin.com/in/johnsmith-ai"),
            [
                FounderCandidate(
                    "John Smith", founder_id="x", linkedin="https://linkedin.com/in/jsmith-vc"
                )
            ],
        )
        assert result.conflicts == ("linkedin",)
        assert result.decision == "review"
