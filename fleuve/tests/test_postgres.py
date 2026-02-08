"""
Unit tests for les.postgres module.
"""
import os
import pytest

from fleuve.postgres import (
    Encryption,
    EncryptedPydanticType,
    PydanticType,
    load_storage_key,
)
from pydantic import BaseModel


class TestModel(BaseModel):
    value: int
    text: str


class TestEncryption:
    """Tests for Encryption class."""

    @pytest.fixture
    def encryption_key(self):
        """Create a test encryption key."""
        from cryptography.hazmat.primitives.ciphers.algorithms import AES256
        import hashlib

        key_material = b"test_key_material_32_bytes_long!"
        sha256 = hashlib.sha256()
        sha256.update(key_material)
        return AES256(sha256.digest())

    @pytest.fixture
    def encryption(self, encryption_key):
        """Create an Encryption instance."""
        return Encryption(encryption_key)

    def test_encrypt_decrypt(self, encryption):
        """Test encryption and decryption round-trip."""
        original_data = b"test data to encrypt"

        encrypted = encryption.encrypt(original_data)
        assert encrypted != original_data
        assert len(encrypted) > len(original_data)  # Should include nonce

        decrypted = encryption.decrypt(encrypted)
        assert decrypted == original_data

    def test_encrypt_different_outputs(self, encryption):
        """Test that same data encrypts differently each time."""
        data = b"same data"
        encrypted1 = encryption.encrypt(data)
        encrypted2 = encryption.encrypt(data)

        # Should be different due to random nonce
        assert encrypted1 != encrypted2

        # But both should decrypt to same value
        assert encryption.decrypt(encrypted1) == data
        assert encryption.decrypt(encrypted2) == data


class TestPydanticType:
    """Tests for PydanticType SQLAlchemy type decorator."""

    def test_pydantic_type_initialization(self):
        """Test PydanticType initialization."""
        pydantic_type = PydanticType(TestModel)
        assert pydantic_type._pydantic_type == TestModel

    def test_process_bind_param(self):
        """Test binding parameter (Python to DB)."""
        pydantic_type = PydanticType(TestModel)
        model = TestModel(value=42, text="test")

        result = pydantic_type.process_bind_param(model, None)
        assert result is not None
        # Should return JSON string (not bytes) for JSONB columns
        assert isinstance(result, str)
        import json
        assert json.loads(result) == {"value": 42, "text": "test"}

    def test_process_bind_param_none(self):
        """Test binding None parameter."""
        pydantic_type = PydanticType(TestModel)
        result = pydantic_type.process_bind_param(None, None)
        assert result is None

    def test_process_result_value(self):
        """Test processing result value (DB to Python)."""
        pydantic_type = PydanticType(TestModel)
        model = TestModel(value=42, text="test")
        json_data = model.model_dump_json().encode()

        result = pydantic_type.process_result_value(json_data, None)
        assert isinstance(result, TestModel)
        assert result.value == 42
        assert result.text == "test"

    def test_process_result_value_none(self):
        """Test processing None result."""
        pydantic_type = PydanticType(TestModel)
        result = pydantic_type.process_result_value(None, None)
        assert result is None


class TestEncryptedPydanticType:
    """Tests for EncryptedPydanticType SQLAlchemy type decorator."""

    @pytest.fixture
    def encryption_key(self):
        """Create a test encryption key."""
        from cryptography.hazmat.primitives.ciphers.algorithms import AES256
        import hashlib

        key_material = b"test_key_material_32_bytes_long!"
        sha256 = hashlib.sha256()
        sha256.update(key_material)
        return AES256(sha256.digest())

    @pytest.fixture
    def encrypted_type(self, encryption_key):
        """Create an EncryptedPydanticType instance."""
        from fleuve.postgres import Encryption

        encryption = Encryption(encryption_key)
        return EncryptedPydanticType(TestModel, encryption=encryption)

    def test_encrypted_type_initialization(self, encrypted_type):
        """Test EncryptedPydanticType initialization."""
        assert encrypted_type._pydantic_type == TestModel
        assert encrypted_type._encryption is not None

    def test_process_bind_param(self, encrypted_type):
        """Test binding parameter with encryption."""
        model = TestModel(value=42, text="test")

        result = encrypted_type.process_bind_param(model, None)
        assert result is not None
        assert isinstance(result, bytes)
        # Encrypted data should not contain plaintext
        assert b"42" not in result
        assert b"test" not in result

    def test_process_result_value(self, encrypted_type):
        """Test processing result value with decryption."""
        model = TestModel(value=42, text="test")

        # Encrypt first
        encrypted = encrypted_type.process_bind_param(model, None)

        # Then decrypt
        result = encrypted_type.process_result_value(encrypted, None)
        assert isinstance(result, TestModel)
        assert result.value == 42
        assert result.text == "test"

    def test_process_bind_param_with_compression(self, encrypted_type):
        """Test that compression is applied."""
        # Create a model with larger data
        large_text = "x" * 1000
        model = TestModel(value=42, text=large_text)

        result = encrypted_type.process_bind_param(model, None)
        assert isinstance(result, bytes)
        # Should be compressed (zstd: prefix)
        decrypted_raw = encrypted_type._encryption.decrypt(result)
        assert decrypted_raw.startswith(b"zstd:")


class TestLoadStorageKey:
    """Tests for load_storage_key function."""

    def test_load_storage_key(self, monkeypatch):
        """Test loading storage key from environment."""
        test_key = "test_storage_key_32_chars_long!"
        monkeypatch.setenv("STORAGE_KEY", test_key)

        key = load_storage_key()
        assert key is not None
        from cryptography.hazmat.primitives.ciphers.algorithms import AES256

        assert isinstance(key, AES256)

    def test_load_storage_key_missing_env(self, monkeypatch):
        """Test that missing env var raises error."""
        if "STORAGE_KEY" in os.environ:
            monkeypatch.delenv("STORAGE_KEY", raising=False)

        with pytest.raises(KeyError):
            load_storage_key()
