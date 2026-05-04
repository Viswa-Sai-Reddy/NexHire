"""PAN encryption + hashing — decision A3.

Two distinct cryptographic operations are required, with different
security properties:

  hash_for_lookup(pan)   →  HMAC-SHA256(pepper, pan_normalized)
                            Deterministic, suitable for the unique
                            index `idx_referrals_active_pan` and all
                            duplicate-check queries. Rainbow-table-
                            resistant because of the peppered key.

  encrypt_for_display(pan) → AES-256-GCM(key, pan_normalized)
                            Non-deterministic; only decrypted in-memory
                            when an HR clicks "Reveal PAN" (audit-logged
                            per decision E19). Resists chosen-ciphertext
                            attacks even if the DB is dumped.

  mask(pan)              →  "ABCDE****F" — a public, non-reversible
                            display string we can show to anyone.

Keys are sourced from environment / Key Vault. They MUST be 32 bytes
each (hex-encoded in the env var). A future Phase-2 rotation involves
re-hashing every row using a new pepper — see Implementation_Plan B19.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from base64 import b64encode
from functools import lru_cache
from typing import NamedTuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings
from app.shared.exceptions import InvalidPanFormatError
from app.shared.value_objects import Pan

logger = logging.getLogger("nexhire.pan_crypto")

# AES-GCM nonce length, fixed by the spec.
_NONCE_LEN = 12


class PanCiphertext(NamedTuple):
    """Wire format: nonce || ciphertext+tag.

    AES-GCM appends the auth tag to the ciphertext, so the layout is
    fully self-describing once we know the nonce length.
    """

    blob: bytes

    @classmethod
    def from_parts(cls, nonce: bytes, ciphertext: bytes) -> "PanCiphertext":
        if len(nonce) != _NONCE_LEN:
            raise ValueError("nonce must be 12 bytes")
        return cls(nonce + ciphertext)

    @property
    def nonce(self) -> bytes:
        return self.blob[:_NONCE_LEN]

    @property
    def ciphertext(self) -> bytes:
        return self.blob[_NONCE_LEN:]


# ────────────────────────────────────────────────────────────────────
# Key material — loaded once per process from settings.
# Hex strings are decoded; we never keep the printable form alive any
# longer than necessary.
# ────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _pepper() -> bytes:
    cfg = get_settings()
    raw = cfg.pan_hmac_pepper
    if not raw:
        raise RuntimeError("PAN_HMAC_PEPPER is not configured")
    pepper = bytes.fromhex(raw) if all(c in "0123456789abcdefABCDEF" for c in raw) else raw.encode()
    if len(pepper) < 32:
        raise RuntimeError("PAN_HMAC_PEPPER must be at least 32 bytes")
    return pepper


@lru_cache(maxsize=1)
def _aes_key() -> bytes:
    cfg = get_settings()
    raw = cfg.pan_aes_key
    if not raw:
        raise RuntimeError("PAN_AES_KEY is not configured")
    key = bytes.fromhex(raw) if all(c in "0123456789abcdefABCDEF" for c in raw) else raw.encode()
    if len(key) != 32:
        raise RuntimeError("PAN_AES_KEY must be exactly 32 bytes (AES-256)")
    return key


# ────────────────────────────────────────────────────────────────────
# Public API.
# ────────────────────────────────────────────────────────────────────
def hash_for_lookup(pan: str | Pan) -> str:
    """HMAC-SHA256 over the normalized PAN, hex-encoded.

    Deterministic by design — identical PANs always produce the same
    hash, which is what the unique index `idx_referrals_active_pan`
    relies on.
    """
    pan_obj = pan if isinstance(pan, Pan) else _validate(pan)
    digest = hmac.new(_pepper(), pan_obj.value.encode("ascii"), hashlib.sha256).digest()
    return digest.hex()


def encrypt_for_display(pan: str | Pan) -> bytes:
    """AES-256-GCM encrypt the PAN. Returns nonce||ciphertext||tag.

    Each call uses a fresh nonce so two encryptions of the same PAN
    produce different blobs — defends against pattern analysis on the
    DB even though the *hash* column is deterministic.
    """
    pan_obj = pan if isinstance(pan, Pan) else _validate(pan)
    import secrets

    nonce = secrets.token_bytes(_NONCE_LEN)
    aes = AESGCM(_aes_key())
    ciphertext = aes.encrypt(nonce, pan_obj.value.encode("ascii"), associated_data=None)
    return PanCiphertext.from_parts(nonce, ciphertext).blob


def decrypt_to_pan(blob: bytes) -> Pan:
    """Reverse of `encrypt_for_display`. Raises on tampering."""
    if len(blob) <= _NONCE_LEN:
        raise InvalidPanFormatError(
            user_message="Stored PAN ciphertext is malformed."
        )
    box = PanCiphertext(blob)
    aes = AESGCM(_aes_key())
    try:
        plaintext = aes.decrypt(box.nonce, box.ciphertext, associated_data=None)
    except InvalidTag as exc:
        # Tampering or wrong key. Never expose detail to users.
        logger.critical("nexhire.pan_crypto.tag_invalid")
        raise InvalidPanFormatError(
            user_message="Stored PAN failed integrity check."
        ) from exc
    return Pan(plaintext.decode("ascii"))


def mask(pan: str | Pan) -> str:
    """Public-safe display form: `ABCDE****F`."""
    pan_obj = pan if isinstance(pan, Pan) else _validate(pan)
    return pan_obj.masked()


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
def _validate(pan: str) -> Pan:
    try:
        return Pan(pan)
    except ValueError as exc:
        raise InvalidPanFormatError() from exc


def fingerprint(pan: str | Pan) -> str:
    """Short hex prefix of the lookup hash — for log-safe correlation
    in audit events without exposing the full hash. 8 hex chars =
    32 bits, safe to log even though it's not reversible.
    """
    return hash_for_lookup(pan)[:8]


def encode_blob_for_logging(blob: bytes) -> str:
    """Best-effort encoding for one-off operational diagnostics. Never
    use for actual storage — use the raw bytes.
    """
    return b64encode(blob).decode("ascii")


__all__ = [
    "PanCiphertext",
    "decrypt_to_pan",
    "encode_blob_for_logging",
    "encrypt_for_display",
    "fingerprint",
    "hash_for_lookup",
    "mask",
]
