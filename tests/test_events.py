"""Pruebas para events."""
import pytest

from fenix.services.events import validate
from fenix.utils.errors import ValidationError

INVENTARIO = {
    "node-01": {"type": "ec2", "id": "i-123"},
    "bucket-01": {"type": "s3", "id": "b-123"},
}
EVENTO = {
    "schema_version": 1,
    "event_id": "evt-node-001",
    "event_type": "instance.stopped",
    "resource_id": "node-01",
    "occurred_at": "2026-10-22T18:00:00Z",
    "simulate_failures": 0,
}


def test_evento_valido_devuelve_copia():
    resultado = validate(EVENTO, INVENTARIO)
    assert resultado == EVENTO
    assert resultado is not EVENTO


@pytest.mark.parametrize("evento", [
    [EVENTO],                                              # una lista no es un objeto
    {**EVENTO, "extra": 1},                                # clave de más
    {k: v for k, v in EVENTO.items() if k != "event_id"},  # clave de menos
    {**EVENTO, "simulate_failures": True},                 # bool no es entero
    {**EVENTO, "simulate_failures": 6},                    # fuera de rango
    {**EVENTO, "schema_version": 2},                       # versión desconocida
    {**EVENTO, "event_type": "otro.evento"},               # tipo desconocido
    {**EVENTO, "resource_id": "i-0abc12345"},              # recurso ajeno
    {**EVENTO, "event_type": "bucket.tags_missing"},       # tipo no encaja con node-01
    {**EVENTO, "occurred_at": "2026-10-22T18:00:00"},      # fecha sin zona UTC
])
def test_evento_invalido_se_rechaza(evento):
    with pytest.raises(ValidationError):
        validate(evento, INVENTARIO)