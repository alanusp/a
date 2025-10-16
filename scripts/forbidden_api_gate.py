#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "scripts" / "forbidden_api_allowlist.json"


class ForbiddenVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, allow: set[str]) -> None:
        self.path = path
        self.allow = allow
        self.failures: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"eval", "exec"}:
            self.failures.append(f"{self.path}:{node.lineno} uses {func.id}")
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "subprocess":
            if func.attr == "Popen":
                self.failures.append(f"{self.path}:{node.lineno} uses subprocess.Popen")
            if func.attr in {"run", "call"}:
                keys = {kw.arg for kw in node.keywords if kw.arg}
                if "check" not in keys:
                    self.failures.append(f"{self.path}:{node.lineno} subprocess.{func.attr} without check=")
                if "timeout" not in keys:
                    self.failures.append(f"{self.path}:{node.lineno} subprocess.{func.attr} without timeout=")
        self.generic_visit(node)


def scan(paths: Iterable[Path], allow: set[str]) -> list[str]:
    failures: list[str] = []
    for path in paths:
        if path.suffix != ".py":
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in allow:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        visitor = ForbiddenVisitor(path=Path(rel), allow=allow)
        visitor.visit(tree)
        failures.extend(visitor.failures)
    return failures


def main() -> None:
    allow: set[str] = set()
    if ALLOWLIST.exists():
        allow = set(json.loads(ALLOWLIST.read_text(encoding="utf-8")))
    python_files = [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts]
    failures = scan(python_files, allow)
    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)
    print("forbidden API gate passed")


if __name__ == "__main__":
    main()
