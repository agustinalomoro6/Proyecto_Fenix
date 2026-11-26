"""Pruebas de límites exactos de validation.py; integrante 1."""
from datetime import datetime, timezone

import pytest

from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, ttl_seconds, utc_text


@pytest.mark.parametrize("valor", ["abc", "a" * 32])
def test_identifier_limites_validos(valor):
    """Acepta los largos 3 y 32, ambos incluidos."""
    assert identifier(valor) == valor


@pytest.mark.parametrize("valor", [
    "ab", "a" * 33, "Node-01", "node_01", "", "../ajeno", "node-01\n", None, 123,
])
def test_identifier_limites_invalidos(valor):
    """Rechaza largos 2 y 33, formatos no permitidos y tipos no textuales."""
    with pytest.raises(ValidationError):
        identifier(valor)


@pytest.mark.parametrize("valor", ["60", "600"])
def test_ttl_limites_validos(valor):
    """Acepta 60 y 600, ambos incluidos."""
    assert ttl_seconds(valor) == int(valor)


@pytest.mark.parametrize("valor", [
    "59", "601", "+60", "-60", "060", " 60", "60 ", "6_0", "60.5", "abc", "", 60, None,
])
def test_ttl_limites_invalidos(valor):
    """Rechaza valores fuera de rango, formas no canónicas y tipos no textuales."""
    with pytest.raises(ValidationError):
        ttl_seconds(valor)


@pytest.mark.parametrize("valor", [
    "2026-10-22T18:00:00", "2026-10-22T15:00:00-03:00", "2026-10-22T18:00:00z",
    "2026-10-22", "no-es-fecha", "", None,
])
def test_utc_invalidos(valor):
    """Rechaza fechas sin UTC explícito, mal formadas o que no son texto."""
    with pytest.raises(ValidationError):
        utc_text(valor)


@pytest.mark.parametrize("valor", ["2026-10-22T18:00:00Z", "2026-10-22T18:00:00+00:00"])
def test_utc_validos(valor):
    """Z y +00:00 representan el mismo instante, normalizado a timezone.utc."""
    assert utc_text(valor) == datetime(2026, 10, 22, 18, tzinfo=timezone.utc)
    assert utc_text(valor).tzinfo is timezone.utc
