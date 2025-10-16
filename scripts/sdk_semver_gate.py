#!/usr/bin/env python3
"""Simple SDK semantic versioning gate."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Dict, List

PY_CLIENT = Path("clients/python/client.py")
TS_CLIENT = Path("clients/ts/index.ts")
BASELINE_DIR = Path("artifacts/sdk")
PY_BASELINE = BASELINE_DIR / "python.json"
TS_BASELINE = BASELINE_DIR / "ts.json"
CHANGELOG = Path("CHANGELOG.md")


class SurfaceDiffError(RuntimeError):
    pass


def _python_surface() -> List[str]:
    tree = ast.parse(PY_CLIENT.read_text(encoding="utf-8"))
    names: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            names.append(node.name)
        elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            names.append(node.name)
    return sorted(names)


def _ts_surface() -> List[str]:
    exports: List[str] = []
    for line in TS_CLIENT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export function"):
            name = line.split()[2].split("(")[0]
            exports.append(name)
        if line.startswith("export interface"):
            name = line.split()[2]
            exports.append(name)
    return sorted(set(exports))


def _load(path: Path) -> List[str]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, surface: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(surface, indent=2, sort_keys=True), encoding="utf-8")


def _diff(old: List[str], new: List[str]) -> Dict[str, List[str]]:
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
    }


def gate(update: bool = False) -> None:
    py_surface = _python_surface()
    ts_surface = _ts_surface()
    py_old = _load(PY_BASELINE)
    ts_old = _load(TS_BASELINE)
    py_diff = _diff(py_old, py_surface)
    ts_diff = _diff(ts_old, ts_surface)
    if update or not py_old or not ts_old:
        _save(PY_BASELINE, py_surface)
        _save(TS_BASELINE, ts_surface)
        return
    breaking = bool(py_diff["removed"] or ts_diff["removed"])
    changed = bool(py_diff["added"] or ts_diff["added"]) or breaking
    if not changed:
        return
    entry = {
        "python": py_diff,
        "ts": ts_diff,
    }
    if breaking:
        message = "SDK surface changed without baseline update"
    else:
        message = "SDK surface expanded; bump required"
    raise SurfaceDiffError(json.dumps(entry, indent=2) + "\n" + message)


def main(argv: List[str] | None = None) -> int:
    update = argv and "--update" in argv
    try:
        gate(update=update)
    except SurfaceDiffError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
