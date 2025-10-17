#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict

AUTHOR = "Alan Uriel Saavedra Pulido"
EMAIL = "alanursapu@gmail.com"


@dataclass
class Mutation:
    path: Path
    transformer: Callable[[str], str]

    def evaluate(self) -> tuple[bool, str, str]:
        original = self.path.read_text(encoding="utf-8")
        updated = self.transformer(original)
        return original != updated, original, updated


def update_pyproject(text: str, module: str) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("name = "):
            lines[idx] = f"name = \"{module}\""
        elif line.startswith("authors = "):
            lines[idx] = (
                "authors = [{ name = \"" + AUTHOR + "\", email = \"" + EMAIL + "\" }]"
            )
        elif line.startswith("license = "):
            lines[idx] = "license = { text = \"Apache-2.0\" }"
    if lines and lines[-1] != "":
        lines.append("")
    return "\n".join(lines)


def update_python_client_readme(_: str, name: str) -> str:
    return f"""# {name} Python SDK

Typed Python client for the {name} API with SPKI pinning and quota headers.

```python
from aegisflux import Client

client = Client(base_url=\"http://127.0.0.1:8000\", api_key=\"demo\", spki_pins=[\"sha256/...\"])
result = client.predict(event_id=\"demo\", tenant_id=\"tenant\", amount_minor=1299, currency=\"USD\")
print(result.decision, result.probability, result.headers.get(\"x-ratelimit-remaining\"))
```
"""


def update_ts_client_readme(_: str, name: str) -> str:
    return f"""# {name} TypeScript SDK

```ts
import {{ createClient }} from \"@aegisflux/sdk\";

const client = createClient({{
  baseUrl: \"http://127.0.0.1:8000\",
  apiKey: \"demo\",
  spkiPins: [\"sha256/...\"]
}});

const result = await client.predict({{
  event_id: \"demo\",
  tenant_id: \"tenant\",
  amount_minor: 1299,
  currency: \"USD\"
}});

console.log(result.decision, result.headers[\"x-ratelimit-remaining\"]);
```
"""


def update_openapi_text(text: str, name: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    info = data.setdefault("info", {})
    info["title"] = name
    contact = info.setdefault("contact", {})
    contact["name"] = AUTHOR
    contact["email"] = EMAIL
    data["x-service-name"] = name.lower()
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def transform_factory(name: str, module: str) -> Dict[Path, Callable[[str], str]]:
    return {
        Path("pyproject.toml"): lambda text: update_pyproject(text, module),
        Path("clients/python/README.md"): lambda text: update_python_client_readme(text, name),
        Path("clients/ts/README.md"): lambda text: update_ts_client_readme(text, name),
    }


def rename_project(name: str, module: str, check: bool) -> int:
    dirty = False
    for path, transformer in transform_factory(name, module).items():
        if not path.exists():
            continue
        mutation = Mutation(path, transformer)
        changed, _, updated = mutation.evaluate()
        if changed:
            if check:
                print(f"{path} would change", file=sys.stderr)
                dirty = True
            else:
                path.write_text(updated, encoding="utf-8")
    openapi_path = Path("artifacts/openapi/current.json")
    if openapi_path.exists():
        original = openapi_path.read_text(encoding="utf-8")
        new_text = update_openapi_text(original, name)
        if new_text != original:
            if check:
                print("artifacts/openapi/current.json would change", file=sys.stderr)
                dirty = True
            else:
                openapi_path.write_text(new_text, encoding="utf-8")
    return 1 if dirty else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename the project")
    parser.add_argument("--name", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return rename_project(args.name, args.module, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
