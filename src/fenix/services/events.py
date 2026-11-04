"""Contrato de eventos de autorreparación; integrante 1."""
from fenix.utils.errors import ValidationError
from fenix.utils.validation import identifier, utc_text

# Campos exactos del evento: no se aceptan faltantes ni sobrantes.
FIELDS = {"schema_version", "event_id", "event_type", "resource_id",
          "occurred_at", "simulate_failures"}

# Cada tipo de evento solo puede apuntar a un tipo de recurso del inventario.
# Según la consigna, I2-C debe guardar "type": "ec2" (node-01) y "s3" (bucket-01).
EVENT_TYPES = {"instance.stopped": "ec2", "bucket.tags_missing": "s3"}


def validate(event: dict, inventory: dict) -> dict:
    """Valida esquema cerrado y resuelve exclusivamente aliases autorizados.

    Args:
        event: JSON objeto con schema_version, event_id, event_type, resource_id,
            occurred_at y simulate_failures.
        inventory: Mapa alias -> recurso, preparado por setup-demo y revisado por el grupo.
    Returns:
        Copia validada del evento; no modifica inventory.
    Raises:
        ValidationError: Tipo, campo, timestamp o recurso no permitido.
    Notes:
        event_type solo permite instance.stopped y bucket.tags_missing.
        simulate_failures solo es de laboratorio: entero de 0 a 5, excluyendo bool.
        La asociación event_id -> contenido (conflicto de reutilización) no se
        guarda aquí: validate es pura y no persiste nada; la hace handle (I5-B).
    """
    if not isinstance(event, dict):  # El cuerpo JSON podría ser lista, número o texto.
        raise ValidationError("El evento debe ser un objeto JSON")
        
    if set(event) != FIELDS:  
        raise ValidationError("El evento debe tener exactamente los campos del contrato")
   
    if type(event["schema_version"]) is not int or event["schema_version"] != 1:
        raise ValidationError("schema_version debe ser el entero 1")
    identifier(event["event_id"]) 
    identifier(event["resource_id"])  
    utc_text(event["occurred_at"])  
    failures = event["simulate_failures"]

    if type(failures) is not int or not 0 <= failures <= 5:  # Fallas de laboratorio.
        raise ValidationError("simulate_failures debe ser un entero entre 0 y 5")
    event_type = event["event_type"]
    
    if not isinstance(event_type, str) or event_type not in EVENT_TYPES:
        raise ValidationError("event_type no permitido")

    if not isinstance(inventory, dict):
        raise ValidationError("Inventario no disponible")
    record = inventory.get(event["resource_id"])  

    if not isinstance(record, dict):  
        raise ValidationError("resource_id no pertenece al inventario autorizado")
    
    if record.get("type") != EVENT_TYPES[event_type]:  
        raise ValidationError("El tipo de evento no corresponde al tipo de recurso")
    return dict(event)  

