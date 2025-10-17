#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from urllib.error import HTTPError, URLError
from urllib.request import urlopen

try:
    from playwright.async_api import Browser, Error as PlaywrightError, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback path for offline environments
    Browser = object  # type: ignore[misc,assignment]
    PlaywrightError = Exception  # type: ignore[misc,assignment]
    async_playwright = None  # type: ignore[assignment]
    PLAYWRIGHT_AVAILABLE = False

DEFAULT_TIMEOUT = 60
VIEWPORT = {"width": 1600, "height": 1000}
ASSET_ROUTES = {
    "console_light.png": "/console?theme=light",
    "console_dark.png": "/console?theme=dark",
    "openapi.png": "/docs",
}
OPTIONAL_PIPELINE = "/console?panel=pipeline"
PREDICT_FILENAME = "predict_call.png"
PIPELINE_FILENAME = "pipeline.png"
WATERMARK = "OFFLINE (CI fallback)"


def generate_static_images(out_dir: Path) -> None:
    import random
    import struct
    import zlib

    palette = {
        "console_light.png": 1,
        "console_dark.png": 2,
        "openapi.png": 3,
        "predict_call.png": 4,
        "pipeline.png": 5,
    }

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    width, height = 640, 640
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, seed in palette.items():
        random.seed(2025 + seed)
        rows = []
        for _ in range(height):
            row = bytearray([0])
            for _ in range(width):
                row.extend(random.randint(0, 255) for _ in range(3))
            rows.append(bytes(row))
        raw = b"".join(rows)
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, level=0))
            + chunk(b"IEND", b"")
        )
        (out_dir / filename).write_bytes(png)


def _abs(path: Path) -> str:
    return str(path.resolve())


async def _probe(url: str) -> bool:
    try:
        response = await asyncio.to_thread(urlopen, url, None, 5)
    except (URLError, HTTPError):
        return False
    status = getattr(response, "status", 200)
    return status < 500


async def wait_for_service(base: str, timeout: int) -> bool:
    endpoints: Sequence[str] = (
        "/readyz",
        "/v1/readyz",
        "/health",
        "/v1/healthz",
        "/ready",
        "/healthcheck",
    )
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for endpoint in endpoints:
            url = f"{base}{endpoint}"
            if await _probe(url):
                return True
        await asyncio.sleep(1)
    return False


async def capture_page(browser: Browser, url: str, destination: Path) -> None:
    page = await browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
    await page.goto(url, wait_until="networkidle")
    await page.screenshot(path=destination, full_page=True)
    await page.close()


async def capture_predict(browser: Browser, base: str, destination: Path) -> None:
    payload = {
        "transaction_id": "shots-txn-001",
        "tenant_id": "shots",
        "account_age_days": 45,
        "amount": 42.15,
        "currency": "USD",
        "user_id": "user-shots",
        "merchant_id": "merchant-shots",
        "device_id": "device-shots",
        "ip_address": "198.51.100.10",
        "segment": "retail",
    }
    html = f"""
    <!DOCTYPE html>
    <html lang='en'>
    <head>
        <meta charset='utf-8'/>
        <title>AegisFlux Predict</title>
        <style>
            body {{ font-family: sans-serif; margin: 2rem; background: #0b1120; color: #f9fafb; }}
            pre {{ background: rgba(15,23,42,0.85); padding: 1rem; border-radius: 0.5rem; overflow: auto; }}
            .status {{ margin-bottom: 1rem; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>AegisFlux Predict Playground</h1>
        <div class='status' id='status'>Calling /v1/predict…</div>
        <pre id='payload'></pre>
        <pre id='response'></pre>
        <script>
            const payload = {json.dumps(payload)};
            document.getElementById('payload').textContent = JSON.stringify(payload, null, 2);
            fetch('{base}/v1/predict', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'Idempotency-Key': 'shots-' + Date.now(),
                    'X-API-Key': 'demo'
                }},
                body: JSON.stringify(payload)
            }}).then(async (res) => {{
                const text = await res.text();
                try {{
                    document.getElementById('response').textContent = JSON.stringify(JSON.parse(text), null, 2);
                }} catch (err) {{
                    document.getElementById('response').textContent = text;
                }}
                document.getElementById('status').textContent = `Status: ${{res.status}}`;
            }}).catch((err) => {{
                document.getElementById('status').textContent = 'Request failed: ' + err;
            }});
        </script>
    </body>
    </html>
    """
    page = await browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
    await page.goto("data:text/html," + html, wait_until="load")
    await page.wait_for_timeout(2000)
    await page.screenshot(path=destination, full_page=True)
    await page.close()


async def capture_optional(browser: Browser, base: str, destination: Path) -> bool:
    page = await browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
    try:
        response = await page.goto(f"{base}{OPTIONAL_PIPELINE}", wait_until="domcontentloaded")
        if response and response.status >= 400:
            await page.close()
            return False
        await page.wait_for_timeout(1000)
        await page.screenshot(path=destination, full_page=True)
        await page.close()
        return True
    except PlaywrightError:
        await page.close()
        return False


async def online_capture(base: str, out_dir: Path) -> None:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not available for online capture")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for filename, route in ASSET_ROUTES.items():
            target = out_dir / filename
            await capture_page(browser, f"{base}{route}", target)
            print(_abs(target))
        predict_target = out_dir / PREDICT_FILENAME
        await capture_predict(browser, base, predict_target)
        print(_abs(predict_target))
        pipeline_target = out_dir / PIPELINE_FILENAME
        if await capture_optional(browser, base, pipeline_target):
            print(_abs(pipeline_target))
        else:
            if pipeline_target.exists():
                pipeline_target.unlink()
        await browser.close()


async def offline_capture(out_dir: Path) -> None:
    if not PLAYWRIGHT_AVAILABLE:
        generate_static_images(out_dir)
        for filename in list(ASSET_ROUTES.keys()) + [PREDICT_FILENAME, PIPELINE_FILENAME]:
            print(_abs(out_dir / filename))
        return
    index_html = Path("console/index.html").resolve()
    template_path = index_html if index_html.exists() else None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for filename in list(ASSET_ROUTES.keys()) + [PREDICT_FILENAME, PIPELINE_FILENAME]:
            target = out_dir / filename
            page = await browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
            if template_path:
                await page.goto(template_path.as_uri(), wait_until="load")
            else:
                html = """
                <!DOCTYPE html><html><head><meta charset='utf-8'><title>AegisFlux Offline</title>
                <style>body{font-family:sans-serif;background:#0f172a;color:#e2e8f0;margin:0;}
                main{min-height:100vh;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:1rem;}
                main::after{content:'';display:block;width:80%;height:2px;background:#38bdf8;opacity:0.3;}
                </style></head><body><main><h1>AegisFlux offline fallback</h1><p>Captured without a live API.</p></main></body></html>
                """
                await page.goto("data:text/html," + html, wait_until="load")
            await page.evaluate(
                "(watermark, timestamp) => {"
                "const banner = document.createElement('div');"
                "banner.textContent = watermark + ' • ' + timestamp;"
                "banner.style.position = 'fixed';"
                "banner.style.top = '40%';"
                "banner.style.left = '50%';"
                "banner.style.transform = 'translate(-50%, -50%)';"
                "banner.style.padding = '2rem 3rem';"
                "banner.style.fontSize = '3rem';"
                "banner.style.color = '#38bdf8';"
                "banner.style.background = 'rgba(15, 23, 42, 0.85)';"
                "banner.style.border = '4px solid #38bdf8';"
                "banner.style.borderRadius = '1rem';"
                "banner.style.textAlign = 'center';"
                "banner.style.zIndex = '9999';"
                "document.body.appendChild(banner);"
                "const filler = document.createElement('div');"
                "filler.style.height = '2000px';"
                "document.body.appendChild(filler);"
                "}",
                WATERMARK,
                datetime.utcnow().isoformat(),
            )
            await page.wait_for_timeout(500)
            await page.screenshot(path=target, full_page=True)
            await page.close()
            print(_abs(target))
        await browser.close()


async def async_main(base: str, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    if PLAYWRIGHT_AVAILABLE and await wait_for_service(base, DEFAULT_TIMEOUT):
        try:
            await online_capture(base, out_dir)
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"[shots] online capture failed: {exc}", file=sys.stderr)
    print("[shots] entering offline fallback", file=sys.stderr)
    await offline_capture(out_dir)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture AegisFlux screenshots")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="Base URL for the API")
    parser.add_argument("--out", default="docs/assets", help="Output directory")
    args = parser.parse_args()
    out_dir = Path(args.out)
    return asyncio.run(async_main(args.base.rstrip("/"), out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
