"""Contrato de eventos de autorreparación; integrante 1."""
from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, utc_text

# Esquema cerrado: no se aceptan campos faltantes ni sobrantes.
FIELDS = {"schema_version", "event_id", "event_type", "resource_id",
          "occurred_at", "simulate_failures"}

# Cada tipo de evento admite un único tipo de recurso del inventario.
EVENT_TYPES = {"instance.stopped": "ec2", "bucket.tags_missing": "s3"}


def validate(event: dict, inventory: dict) -> dict:
    """Valida esquema cerrado y resuelve exclusivamente aliases autorizados.

    Args:
        event: dict con exactamente estos campos: schema_version (int 1),
            event_id y resource_id (ver identifier), event_type
            ("instance.stopped" o "bucket.tags_missing"), occurred_at (UTC
            explícito, ver utc_text) y simulate_failures (int de 0 a 5).
            Los enteros no admiten bool.
        inventory: dict alias -> recurso, preparado por setup-demo. El recurso de
            resource_id debe existir y su type debe corresponder a event_type
            ("ec2" para instance.stopped, "s3" para bucket.tags_missing).
    Returns:
        Un dict nuevo con los mismos campos y valores que event.
    Raises:
        ValidationError: Si falla el tipo, los campos, un valor, la fecha, el
            alias o la compatibilidad entre evento y recurso.
    Notes:
        No tiene efectos: no modifica event ni inventory, no escribe en disco ni
        publica en SQS. dict(event) es una copia superficial: alcanza porque los
        campos son escalares, pero no vuelve inmutable al resultado.
        La asociación event_id -> contenido (conflicto de reutilización) no se
        guarda aquí: la persiste remediation.handle (I5-B).
    """
    if not isinstance(event, dict):  # Un JSON puede ser lista, número o texto.
        raise ValidationError("El evento debe ser un objeto JSON")

    if set(event) != FIELDS:
        raise ValidationError("El evento debe tener exactamente los campos del contrato")

    # type(...) is int excluye bool, que para isinstance también es int.
    if type(event["schema_version"]) is not int or event["schema_version"] != 1:
        raise ValidationError("schema_version debe ser el entero 1")
    identifier(event["event_id"])
    identifier(event["resource_id"])
    utc_text(event["occurred_at"])  # Solo valida: se conserva el texto original.
    failures = event["simulate_failures"]

    if type(failures) is not int or not 0 <= failures <= 5:  # Fallas de laboratorio.
        raise ValidationError("simulate_failures debe ser un entero entre 0 y 5")

    event_type = event["event_type"]  # El isinstance evita TypeError con listas.
    if not isinstance(event_type, str) or event_type not in EVENT_TYPES:
        raise ValidationError("event_type no permitido")

    if not isinstance(inventory, dict):
        raise ValidationError("Inventario no disponible")
    record = inventory.get(event["resource_id"])  # Solo aliases, nunca IDs libres.

    if not isinstance(record, dict):
        raise ValidationError("resource_id no pertenece al inventario autorizado")

    if record.get("type") != EVENT_TYPES[event_type]:
        raise ValidationError("El tipo de evento no corresponde al tipo de recurso")
    return dict(event)  # Copia superficial.

