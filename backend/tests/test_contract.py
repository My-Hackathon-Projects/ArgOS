"""Pure unit tests for the connector contract — no DB, so CI stays lightweight."""

from datetime import datetime

from app.connectors.base import Connector, SignalEnvelope


def test_envelope_defaults():
    env = SignalEnvelope(source="github", signal_type="commit", external_id="abc123")
    assert env.source_reliability == 0.5
    assert env.raw == {}
    assert env.entity_hint is None


def test_envelope_roundtrip():
    env = SignalEnvelope(
        source="arxiv",
        signal_type="paper",
        external_id="2401.12345",
        entity_hint="orcid:0000-0002",
        occurred_at=datetime(2026, 1, 1),
        raw={"authors": ["A. Vance"]},
    )
    assert env.model_dump()["raw"]["authors"] == ["A. Vance"]


def test_connector_poll_maps_fetch_through_normalize():
    class FakeConnector(Connector):
        source = "synthetic"

        def fetch(self):
            return [{"id": "1"}, {"id": "2"}]

        def normalize(self, raw):
            return SignalEnvelope(source=self.source, signal_type="post", external_id=raw["id"])

    envelopes = list(FakeConnector().poll())
    assert [e.external_id for e in envelopes] == ["1", "2"]
    assert all(isinstance(e, SignalEnvelope) for e in envelopes)
