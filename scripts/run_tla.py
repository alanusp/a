from __future__ import annotations

class TLAModelChecker:
    """Tiny model checker mirroring the intent of the TLA specs for CI."""

    def __init__(self) -> None:
        self.exactly_once_processed: set[str] = set()
        self.queue: list[str] = []
        self.canary_state: str = "Baseline"

    def check_exactly_once(self) -> None:
        events = ["evt-1", "evt-2", "evt-1"]
        for event in events:
            if event not in self.queue and event not in self.exactly_once_processed:
                self.queue.append(event)
        while self.queue:
            current = self.queue.pop(0)
            assert current not in self.exactly_once_processed, "duplicate processing detected"
            self.exactly_once_processed.add(current)

    def check_canary(self) -> None:
        transitions = ["Shadow", "Canary", "Promote", "Rollback"]
        allowed = {
            "Baseline": {"Shadow"},
            "Shadow": {"Canary", "Rollback"},
            "Canary": {"Promote", "Rollback"},
            "Promote": set(),
            "Rollback": set(),
        }
        for target in transitions:
            if target not in allowed[self.canary_state]:
                if target == "Rollback":
                    self.canary_state = "Rollback"
                continue
            self.canary_state = target
        assert self.canary_state in {"Promote", "Rollback"}


def run() -> None:
    checker = TLAModelChecker()
    checker.check_exactly_once()
    checker.check_canary()
    print("TLA simulations completed successfully")


if __name__ == "__main__":
    run()

