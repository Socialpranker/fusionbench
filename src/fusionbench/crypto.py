# src/fusionbench/crypto.py
"""Thin Fernet wrapper for the held-out gold file. Fernet = AES-128-CBC + HMAC, so a
tampered ciphertext fails to decrypt rather than silently returning garbage. The key
lives in the GOLD_DECRYPT_KEY GitHub secret; never commit it."""
from __future__ import annotations

from cryptography.fernet import Fernet


def generate_key() -> bytes:
    """Generate a new base64 Fernet key. Run once; store as GOLD_DECRYPT_KEY secret."""
    return Fernet.generate_key()


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    return Fernet(key).encrypt(data)


def decrypt_bytes(token: bytes, key: bytes) -> bytes:
    """Raises cryptography.fernet.InvalidToken on wrong key or tampered ciphertext."""
    return Fernet(key).decrypt(token)
