# tests/test_crypto.py
import pytest
from cryptography.fernet import InvalidToken

from fusionbench.crypto import encrypt_bytes, decrypt_bytes, generate_key


def test_roundtrip():
    key = generate_key()
    data = b'{"id": "ruler-0001", "reference": "NEEDLE-AAA"}\n'
    token = encrypt_bytes(data, key)
    assert token != data
    assert decrypt_bytes(token, key) == data


def test_wrong_key_fails():
    k1, k2 = generate_key(), generate_key()
    token = encrypt_bytes(b"secret", k1)
    with pytest.raises(InvalidToken):
        decrypt_bytes(token, k2)
