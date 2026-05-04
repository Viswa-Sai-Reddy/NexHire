"""PAN crypto — hashing determinism + GCM tampering safety.

These tests make/break the unique-index dedup story. If hashing isn't
deterministic the index can't enforce active-PAN uniqueness; if AES
tampering isn't detected the encrypted blob is meaningless. Both are
load-bearing.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.modules.referral import pan_crypto
from app.shared.exceptions import InvalidPanFormatError


pytestmark = pytest.mark.usefixtures("test_settings")


class TestHashForLookup:
    def test_deterministic_per_pan(self) -> None:
        a = pan_crypto.hash_for_lookup("ABCDE1234F")
        b = pan_crypto.hash_for_lookup("ABCDE1234F")
        assert a == b

    def test_case_insensitive_input(self) -> None:
        a = pan_crypto.hash_for_lookup("abcde1234f")
        b = pan_crypto.hash_for_lookup("ABCDE1234F")
        assert a == b

    def test_different_pans_hash_differently(self) -> None:
        a = pan_crypto.hash_for_lookup("ABCDE1234F")
        b = pan_crypto.hash_for_lookup("ABCDE1234G")
        assert a != b

    def test_invalid_pan_raises(self) -> None:
        with pytest.raises(InvalidPanFormatError):
            pan_crypto.hash_for_lookup("not-a-pan")


class TestEncryptionRoundtrip:
    def test_encrypt_then_decrypt(self) -> None:
        blob = pan_crypto.encrypt_for_display("ABCDE1234F")
        recovered = pan_crypto.decrypt_to_pan(blob)
        assert recovered.value == "ABCDE1234F"

    def test_encrypt_is_nondeterministic(self) -> None:
        a = pan_crypto.encrypt_for_display("ABCDE1234F")
        b = pan_crypto.encrypt_for_display("ABCDE1234F")
        # Same plaintext → different ciphertext (fresh nonce per call).
        # Both decrypt to the same value.
        assert a != b
        assert pan_crypto.decrypt_to_pan(a).value == pan_crypto.decrypt_to_pan(b).value

    def test_tampering_detected(self) -> None:
        blob = bytearray(pan_crypto.encrypt_for_display("ABCDE1234F"))
        # Flip a byte in the ciphertext+tag region.
        blob[-1] ^= 0x01
        with pytest.raises(InvalidPanFormatError):
            pan_crypto.decrypt_to_pan(bytes(blob))

    def test_truncation_detected(self) -> None:
        blob = pan_crypto.encrypt_for_display("ABCDE1234F")
        with pytest.raises(InvalidPanFormatError):
            pan_crypto.decrypt_to_pan(blob[:5])  # smaller than nonce length


class TestMaskAndFingerprint:
    def test_mask_format(self) -> None:
        assert pan_crypto.mask("ABCDE1234F") == "ABCDE****F"

    def test_fingerprint_short_and_stable(self) -> None:
        a = pan_crypto.fingerprint("ABCDE1234F")
        b = pan_crypto.fingerprint("ABCDE1234F")
        assert len(a) == 8
        assert a == b

    def test_unused_settings_param(self, test_settings: Settings) -> None:
        # Just ensures the test_settings fixture wires PAN keys correctly
        # for callers that don't use any other setting.
        assert test_settings.pan_hmac_pepper
        assert test_settings.pan_aes_key
