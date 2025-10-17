from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Iterable, Set

REPO_ROOT = Path(__file__).resolve().parent.parent


def _collect_imports(paths: Iterable[Path]) -> Set[str]:
    modules: set[str] = set()
    for path in paths:
        if path.name == "__init__.py":
            continue
        try:
            node = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - defensive
            continue
        for item in ast.walk(node):
            if isinstance(item, ast.Import):
                for alias in item.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(item, ast.ImportFrom):
                if item.module is None:
                    continue
                root = item.module.split(".")[0]
                if item.level and root == "":
                    continue
                modules.add(root)
    return modules


def _declared_packages(lockfile: Path) -> Set[str]:
    declared: set[str] = set()
    if not lockfile.exists():
        return declared
    for line in lockfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("==")[0]
        declared.add(name.replace("-", "_").lower())
    return declared



INTERNAL_PACKAGES = {
    "app", "streaming", "tests", "adversary", "canary", "graph", "offline", "quality",
    "scripts", "sketches", "policy", "security", "feature_repo", "docs",
}

KNOWN_EXTRAS = {"pytest", "hypothesis", "yaml", "starlette", "redis", "numpy", "scipy", "torch", "kafka", "plotly", "sklearn"}

def run(lockfile: Path, report_path: Path) -> int:
    python_files = [
        path
        for path in REPO_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and not path.parts[-2:] == (".venv", "lib")
    ]
    modules = _collect_imports(python_files)
    stdlib = set(sys.stdlib_module_names)
    allowed_third_party = _declared_packages(lockfile)
    allowed_third_party.update(INTERNAL_PACKAGES)
    allowed_third_party.update(KNOWN_EXTRAS)

    unknown = sorted(
        module
        for module in modules
        if module not in stdlib and module not in allowed_third_party and not module.startswith("app")
    )

    report = {"modules": sorted(modules), "unknown": unknown}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if unknown:
        print("Undeclared third-party modules detected:")
        for module in unknown:
            print(f"  - {module}")
        return 1
    print("BOM closure verified")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify import coverage against lockfile")
    parser.add_argument("--lockfile", type=Path, default=REPO_ROOT / "requirements.lock")
    parser.add_argument("--report", type=Path, default=REPO_ROOT / "artifacts" / "import_hygiene.json")
    args = parser.parse_args()
    return run(args.lockfile, args.report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
