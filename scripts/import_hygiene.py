#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Set, Tuple

ALLOWLIST_PATH = Path("scripts/import_hygiene_allowlist.json")
REPORT_PATH = Path("artifacts/import_hygiene.json")
PACKAGE_ROOT = Path("app")
HEAVY_IMPORTS = {"numpy", "pandas", "torch", "sklearn"}
HOT_PREFIXES = ("app.api", "app.services", "app.models")
ENTRY_PREFIXES = (
    "app.api",
    "app.core",
    "app.services",
    "app.models",
    "app.console",
    "app.streaming",
    "app.offline",
    "app.security",
    "app.quality",
)


class ImportCollector(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.edges: Set[str] = set()
        self.top_level_imports: List[str] = []
        self._scope: List[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            target = alias.name
            if target.startswith("app"):
                self.edges.add(target.split(" as ")[0])
            if not self._scope:
                root = target.split(".")[0]
                self.top_level_imports.append(root)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        level = node.level or 0
        base = self.module.split(".")
        if level:
            base = base[: -level]
        if module:
            parts = module.split(".")
        else:
            parts = []
        resolved = base + parts
        if resolved:
            target_module = ".".join(resolved)
            if target_module.startswith("app"):
                self.edges.add(target_module)
        if not self._scope:
            root = (module.split(".")[0] if module else base[0]) if base else module
            if root:
                self.top_level_imports.append(root)


def _module_name(path: Path) -> str:
    relative = path.with_suffix("").relative_to(PACKAGE_ROOT.parent)
    return ".".join(relative.parts)


def _discover_modules() -> Dict[str, Path]:
    modules: Dict[str, Path] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        modules[_module_name(path)] = path
    return modules


def _load_allowlist() -> Dict[str, Set[str]]:
    if not ALLOWLIST_PATH.exists():
        return {"orphans": set(), "cycles": set(), "heavy": set()}
    data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return {
        "orphans": set(data.get("orphans", [])),
        "cycles": set(data.get("cycles", [])),
        "heavy": set(data.get("heavy", [])),
    }


def analyze() -> Dict[str, List[str]]:
    modules = _discover_modules()
    allowlist = _load_allowlist()
    edges: Dict[str, Set[str]] = defaultdict(set)
    inbound: Dict[str, int] = defaultdict(int)
    heavy_hits: List[str] = []

    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        collector = ImportCollector(module)
        collector.visit(tree)
        for target in collector.edges:
            edges[module].add(target)
            inbound[target] += 1
        if module.startswith(HOT_PREFIXES) and module not in allowlist["heavy"]:
            for top in collector.top_level_imports:
                if top in HEAVY_IMPORTS:
                    heavy_hits.append(module)
                    break

    entrypoints = {"app.main", "app.api.routes"}
    orphans = [
        module
        for module in modules
        if inbound[module] == 0
        and module not in entrypoints
        and module not in allowlist["orphans"]
        and not any(module == prefix or module.startswith(f"{prefix}.") for prefix in ENTRY_PREFIXES)
    ]

    cycles: List[str] = []
    visited: Dict[str, int] = {}

    def dfs(node: str, stack: List[str]) -> None:
        visited[node] = 1
        stack.append(node)
        for neighbour in edges.get(node, set()):
            if neighbour not in modules:
                continue
            if visited.get(neighbour, 0) == 0:
                dfs(neighbour, stack)
            elif neighbour in stack and node not in allowlist["cycles"]:
                cycle = stack[stack.index(neighbour) :] + [neighbour]
                cycles.append(" -> ".join(cycle))
        stack.pop()
        visited[node] = 2

    for module in modules:
        if visited.get(module, 0) == 0:
            dfs(module, [])

    report = {
        "orphans": sorted(set(orphans)),
        "cycles": sorted(set(cycles)),
        "heavy": sorted(set(heavy_hits)),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = analyze()
    if report["orphans"] or report["cycles"] or report["heavy"]:
        print(json.dumps(report, indent=2))
        raise SystemExit("import hygiene check failed")
    print("import hygiene ok")


if __name__ == "__main__":
    main()
