"""Synthetic pytest suite exercising the engine block via a fixture."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from engine.service import ReportBuilder


@pytest.fixture
def report_builder() -> Generator[ReportBuilder, None, None]:
    """Yield a ReportBuilder instance for engine tests."""
    builder = ReportBuilder()
    yield builder


def test_build_summary(report_builder) -> None:
    """Exercise ReportBuilder.build_summary via fixture type inference."""
    rows = report_builder.build_summary("alice")
    assert isinstance(rows, list)
