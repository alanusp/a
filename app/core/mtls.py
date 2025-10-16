"""mTLS helper utilities for optional air-gapped deployments."""
from __future__ import annotations

import base64
import shutil
import ssl
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Dict

from app.core.config import get_settings


@dataclass(frozen=True)
class MTLSArtifacts:
    ca_cert: Path
    server_cert: Path
    server_key: Path
    client_cert: Path
    client_key: Path


class MTLSGenerationError(RuntimeError):
    """Raised when openssl invocation fails."""


def _run(
    cmd: list[str],
    cwd: Path,
    input_data: str | bytes | None = None,
    *,
    text: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    if shutil.which("openssl") is None:
        raise MTLSGenerationError("openssl binary not found; cannot provision mTLS certificates")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=text,
        input=input_data,
    )
    if result.returncode != 0:
        raise MTLSGenerationError(result.stderr.strip() or "openssl command failed")
    return result


def _generate_certificates(base_dir: Path) -> MTLSArtifacts:
    base_dir.mkdir(parents=True, exist_ok=True)
    ca_key = base_dir / "ca.key"
    ca_cert = base_dir / "ca.crt"
    server_key = base_dir / "server.key"
    server_csr = base_dir / "server.csr"
    server_cert = base_dir / "server.crt"
    client_key = base_dir / "client.key"
    client_csr = base_dir / "client.csr"
    client_cert = base_dir / "client.crt"
    serial = base_dir / "serial"
    index = base_dir / "index.txt"

    if not ca_key.exists():
        _run(["openssl", "genrsa", "-out", str(ca_key), "4096"], base_dir)
    if not ca_cert.exists():
        _run(
            [
                "openssl",
                "req",
                "-x509",
                "-new",
                "-key",
                str(ca_key),
                "-sha256",
                "-days",
                "365",
                "-out",
                str(ca_cert),
                "-subj",
                "/CN=fraud-stack-local-ca",
            ],
            base_dir,
        )
        serial.write_text("01", encoding="utf-8")
        index.write_text("", encoding="utf-8")

    if not server_key.exists():
        _run(["openssl", "genrsa", "-out", str(server_key), "4096"], base_dir)
    if not server_cert.exists():
        _run(
            [
                "openssl",
                "req",
                "-new",
                "-key",
                str(server_key),
                "-out",
                str(server_csr),
                "-subj",
                "/CN=fraud-api",
            ],
            base_dir,
        )
        _run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(server_csr),
                "-CA",
                str(ca_cert),
                "-CAkey",
                str(ca_key),
                "-CAcreateserial",
                "-out",
                str(server_cert),
                "-days",
                "365",
                "-sha256",
            ],
            base_dir,
        )

    if not client_key.exists():
        _run(["openssl", "genrsa", "-out", str(client_key), "4096"], base_dir)
    if not client_cert.exists():
        _run(
            [
                "openssl",
                "req",
                "-new",
                "-key",
                str(client_key),
                "-out",
                str(client_csr),
                "-subj",
                "/CN=fraud-client",
            ],
            base_dir,
        )
        _run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(client_csr),
                "-CA",
                str(ca_cert),
                "-CAkey",
                str(ca_key),
                "-CAcreateserial",
                "-out",
                str(client_cert),
                "-days",
                "365",
                "-sha256",
            ],
            base_dir,
        )

    return MTLSArtifacts(
        ca_cert=ca_cert,
        server_cert=server_cert,
        server_key=server_key,
        client_cert=client_cert,
        client_key=client_key,
    )


@lru_cache(maxsize=1)
def get_mtls_artifacts() -> MTLSArtifacts:
    settings = get_settings()
    base_dir = Path(settings.mtls_artifact_dir)
    return _generate_certificates(base_dir)


def server_ssl_context() -> ssl.SSLContext:
    artifacts = get_mtls_artifacts()
    context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(
        certfile=str(artifacts.server_cert), keyfile=str(artifacts.server_key)
    )
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(artifacts.ca_cert))
    context.check_hostname = False
    return context


def client_ssl_kwargs() -> Dict[str, str | bool]:
    artifacts = get_mtls_artifacts()
    return {
        "ssl": True,
        "ssl_certfile": str(artifacts.client_cert),
        "ssl_keyfile": str(artifacts.client_key),
        "ssl_ca_certs": str(artifacts.ca_cert),
        "ssl_cert_reqs": "required",
    }


def _spki_pin(cert: Path) -> str:
    pubkey = _run(["openssl", "x509", "-in", str(cert), "-noout", "-pubkey"], cert.parent)
    input_bytes = pubkey.stdout if isinstance(pubkey.stdout, bytes) else pubkey.stdout.encode("utf-8")
    der = _run(
        ["openssl", "pkey", "-pubin", "-outform", "DER"],
        cert.parent,
        input_data=input_bytes,
        text=False,
    )
    digest = sha256(der.stdout).digest()
    return base64.b64encode(digest).decode("ascii")


def export_spki_pin() -> str:
    artifacts = get_mtls_artifacts()
    return _spki_pin(artifacts.server_cert)


def rotate_certificates() -> MTLSArtifacts:
    base_dir = Path(get_settings().mtls_artifact_dir)
    for suffix in ("ca", "server", "client"):
        for extension in (".crt", ".key", ".csr"):
            path = base_dir / f"{suffix}{extension}"
            if path.exists():
                path.unlink()
    get_mtls_artifacts.cache_clear()  # type: ignore[attr-defined]
    return get_mtls_artifacts()
