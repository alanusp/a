from __future__ import annotations

import datetime as _dt
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


@dataclass(slots=True)
class CertificateAuthority:
    key_path: Path
    cert_path: Path


def _write_private_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _write_certificate(path: Path, certificate: x509.Certificate) -> None:
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def ensure_ca(directory: Path) -> CertificateAuthority:
    directory.mkdir(parents=True, exist_ok=True)
    key_path = directory / "ca.key"
    cert_path = directory / "ca.crt"
    if key_path.exists() and cert_path.exists():
        return CertificateAuthority(key_path=key_path, cert_path=cert_path)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Hyperion Fraud Defense"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Hyperion CA"),
        ]
    )
    now = _dt.datetime.utcnow()
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + _dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    _write_private_key(key_path, key)
    _write_certificate(cert_path, certificate)
    return CertificateAuthority(key_path=key_path, cert_path=cert_path)


def issue_certificate(
    *,
    ca: CertificateAuthority,
    common_name: str,
    cert_path: Path,
    key_path: Path,
    san_hosts: Iterable[str] | None = None,
) -> Tuple[Path, Path]:
    ca_key = serialization.load_pem_private_key(ca.key_path.read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate(ca.cert_path.read_bytes())

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Hyperion Fraud Defense"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ])
        )
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_dt.datetime.utcnow() - _dt.timedelta(minutes=1))
        .not_valid_after(_dt.datetime.utcnow() + _dt.timedelta(days=825))
    )
    if san_hosts:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(host) for host in san_hosts]),
            critical=False,
        )
    certificate = builder.sign(private_key=ca_key, algorithm=hashes.SHA256())
    _write_private_key(key_path, key)
    _write_certificate(cert_path, certificate)
    return cert_path, key_path


def build_ssl_context(*, ca: CertificateAuthority, cert_path: Path, key_path: Path, server: bool) -> ssl.SSLContext:
    purpose = ssl.Purpose.CLIENT_AUTH if server else ssl.Purpose.SERVER_AUTH
    context = ssl.create_default_context(purpose=purpose)
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    context.load_verify_locations(cafile=str(ca.cert_path))
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = not server
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context
