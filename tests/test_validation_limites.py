"""Pruebas de límites exactos de validation.py; integrante 1."""
import pytest

from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, ttl_seconds, utc_text


@pytest.mark.parametrize("valor", ["abc", "a" * 32])
def test_identifier_limites_validos(valor):
    assert identifier(valor) == valor


@pytest.mark.parametrize("valor", ["ab", "a" * 33, "Node-01", "node_01", ""])
def test_identifier_limites_invalidos(valor):
    with pytest.raises(ValidationError):
        identifier(valor)


@pytest.mark.parametrize("valor", ["60", "600"])
def test_ttl_limites_validos(valor):
    assert ttl_seconds(valor) == int(valor)


@pytest.mark.parametrize("valor", ["59", "601", "+60", "60.5", "abc"])
def test_ttl_limites_invalidos(valor):
    with pytest.raises(ValidationError):
        ttl_seconds(valor)


@pytest.mark.parametrize("valor", ["2026-10-22T18:00:00", "2026-10-22T15:00:00-03:00", "no-es-fecha"])
def test_utc_invalidos(valor):
    with pytest.raises(ValidationError):
        utc_text(valor)