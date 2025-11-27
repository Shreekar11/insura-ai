"""Tests for BatchNormalizationProcessor signal handling."""

from unittest.mock import MagicMock

import pytest

from app.services.normalization.batch_normalization_processor import (
    BatchNormalizationProcessor,
)


@pytest.fixture
def processor():
    """Provide a processor instance with mocked dependencies."""
    return BatchNormalizationProcessor(
        unified_extractor=MagicMock(),
        semantic_normalizer=MagicMock(),
        chunking_service=MagicMock(),
        entity_resolver=None,
        chunk_repository=MagicMock(),
        normalization_repository=MagicMock(),
        classification_repository=MagicMock(),
    )


def test_extract_signals_parses_string_payloads(processor):
    """Ensure stringified scores and percentages are converted to floats."""
    batch_result = {
        "signals": {
            "policy": "0.92",
            "claim": "0.03",
            "loss_run": "2%",
            "invoice": "1.4",
        }
    }

    signals = processor._extract_signals(batch_result)

    assert pytest.approx(signals["policy"]) == 0.92
    assert pytest.approx(signals["claim"]) == 0.03
    assert pytest.approx(signals["loss_run"]) == 0.02
    assert signals["invoice"] == 1.0  # clamped


def test_extract_signals_handles_missing_values(processor):
    """Missing or invalid keys should default to 0.0."""
    batch_result = {"signals": {"policy": "not-a-number"}}

    signals = processor._extract_signals(batch_result)

    assert signals["policy"] == 0.0
    assert signals["claim"] == 0.0

