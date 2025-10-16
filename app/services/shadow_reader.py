from __future__ import annotations

from dataclasses import dataclass

from app.services.parity import get_parity_service


@dataclass
class ShadowReaderReport:
    match_rate: float
    mismatches: int
    total: int


class ShadowReader:
    """Parses parity metrics to ensure read-only consumers can validate dual writes."""

    def __init__(self) -> None:
        self._parity = get_parity_service()

    def report(self) -> ShadowReaderReport:
        metrics = self._parity.metrics()
        return ShadowReaderReport(
            match_rate=metrics.match_rate,
            mismatches=metrics.mismatches,
            total=metrics.total,
        )

    def assert_ready(self, threshold: float) -> None:
        report = self.report()
        if report.match_rate < threshold:
            raise RuntimeError(
                f"shadow readers not ready: match_rate={report.match_rate:.4f} < {threshold:.4f}"
            )


def get_shadow_reader() -> ShadowReader:
    return ShadowReader()
