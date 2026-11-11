"""Acciones convergentes a completar por integrante 3 y coordinadas por 5."""
from botocore.exceptions import BotoCoreError, ClientError  # Errores de Boto3 a clasificar.
from fenix.config.settings import client
from fenix.services.cloud_support import aws_tags
from fenix.utils.state import load, save
from fenix.services.events import validate
from fenix.services.notifications import notify
from fenix.utils.errors import RetryableError, PermanentError


# Códigos de AWS que indican un fallo pasajero: vale la pena reintentar.
TRANSIENT_CODES = {"Throttling", "ThrottlingException", "RequestLimitExceeded",
                   "ServiceUnavailable", "InternalError", "InternalFailure",
                   "RequestTimeout", "Unavailable", "SlowDown"}


def classify(error: Exception) -> Exception:
    """Traduce un error de Boto3 a un error del proyecto, sin copiar datos sensibles.

    Args:
        error: ClientError o BotoCoreError capturado al llamar a la API.
    Returns:
        RetryableError si el fallo es transitorio; PermanentError en otro caso.
    """
    if isinstance(error, BotoCoreError):  # Red, DNS o conexión: pasajero.
        return RetryableError("Fallo de conexión con el servicio; se reintentará")
    code = error.response.get("Error", {}).get("Code", "")
    status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
    if code in TRANSIENT_CODES or status >= 500:  # Throttling o error 5xx del servicio.
        return RetryableError(f"Fallo transitorio del servicio ({code})")
    return PermanentError(f"Operación rechazada por el servicio ({code})")  # No se reintenta.


def instance_state(ec2, instance_id: str) -> str:
    """Lee el estado actual de una instancia.

    Args:
        ec2: Cliente EC2 del emulador.
        instance_id: InstanceId leído del inventario.
    Returns:
        Nombre del estado: pending, running, stopping, stopped, etc.
    Raises:
        PermanentError: Si la instancia no existe.
    """
    try:
        reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    except ClientError as error:
        if error.response.get("Error", {}).get("Code", "").startswith("InvalidInstanceID"):
            raise PermanentError("La instancia del inventario no existe") from error
        raise
    if not reservations or not reservations[0]["Instances"]:  # Respuesta vacía.
        raise PermanentError("La instancia del inventario no existe")
    return reservations[0]["Instances"][0]["State"]["Name"]


def bucket_tags(s3, bucket: str) -> dict:
    """Lee las etiquetas de un bucket; "sin etiquetas" equivale a un diccionario vacío.

    Args:
        s3: Cliente S3 del emulador.
        bucket: Nombre del bucket del inventario.
    Returns:
        Diccionario clave -> valor con las etiquetas actuales.
    Raises:
        PermanentError: Si el bucket no existe.
    """
    try:
        tag_set = s3.get_bucket_tagging(Bucket=bucket)["TagSet"]
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        if code == "NoSuchTagSet":  # Solo este código significa "sin etiquetas".
            return {}
        if code == "NoSuchBucket":
            raise PermanentError("El bucket del inventario no existe") from error
        raise
    return {row["Key"]: row["Value"] for row in tag_set}


def repair_instance(resource: dict) -> str:
    """Arranca una instancia detenida y exige observarla en running.

    Args:
        resource: Registro de inventario con el id de la instancia.
    Returns:
        "already_ok" si ya estaba running; "repaired" si se arrancó.
    Raises:
        RetryableError: Estado pasajero (pending, stopping) o aún no observado.
        PermanentError: Estado no reparable (terminated, shutting-down).
    """
    ec2 = client("ec2")
    instance_id = resource["id"]
    state = instance_state(ec2, instance_id)
    if state == "running":  # Ya cumple la política: no se toca nada.
        return "already_ok"
    if state in ("pending", "stopping"):  # Transición en curso: se reintenta, sin esperar.
        raise RetryableError(f"La instancia está en transición ({state})")
    if state != "stopped":  # terminated o shutting-down no se pueden reparar.
        raise PermanentError(f"La instancia está en un estado no reparable ({state})")
    ec2.start_instances(InstanceIds=[instance_id])  # Nunca reboot_instances.
    if instance_state(ec2, instance_id) != "running":  # Se verifica, no se supone.
        raise RetryableError("La instancia aún no se observa en running")
    return "repaired"


def repair_bucket(resource: dict) -> str:
    """Restaura las etiquetas obligatorias de un bucket sin borrar las ajenas.

    Args:
        resource: Registro de inventario con el nombre del bucket y expected_tags.
    Returns:
        "already_ok" si las etiquetas ya cumplen; "repaired" si se restauraron.
    Raises:
        RetryableError: Si tras escribir las etiquetas todavía no se observan.
        PermanentError: Bucket inexistente o inventario sin etiquetas esperadas.
    """
    expected = resource.get("expected_tags")  # Etiquetas obligatorias del inventario.
    if not isinstance(expected, dict) or not expected:  # Sin política no hay qué restaurar.
        raise PermanentError("El inventario no define expected_tags para el bucket")
    s3 = client("s3")
    current = bucket_tags(s3, resource["id"])
    if all(current.get(key) == value for key, value in expected.items()):
        return "already_ok"  # Ya cumple: no se escribe nada.
    merged = {**current, **expected}  # Las obligatorias ganan; las ajenas se conservan.
    s3.put_bucket_tagging(Bucket=resource["id"], Tagging={"TagSet": aws_tags(merged)})
    after = bucket_tags(s3, resource["id"])  # Se vuelve a leer para verificar.
    if any(after.get(key) != value for key, value in expected.items()):
        raise RetryableError("Las etiquetas aún no se observan")
    return "repaired"


def repair(resource: dict, event_type: str) -> str:
    """Acerca un recurso autorizado a su estado deseado y verifica el resultado.

    Args:
        resource: Registro de inventario con type/id y etiquetas esperadas.
        event_type: instance.stopped o bucket.tags_missing ya validado.
    Returns:
        "repaired" si cambió el estado; "already_ok" si ya cumplía la política.
    Raises:
        RetryableError: La API falla temporalmente o el estado final aún no se observa.
        PermanentError: Recurso inexistente o configuración no autorizada.
    Side Effects:
        Arranca una instancia EC2 mock detenida o restaura tags de un bucket S3.
    Notes:
        No usar reboot_instances: repetir un reinicio no es convergencia.
        Un estado pending requiere otra recepción, sin esperas largas en el worker.
    """
    kinds = {"instance.stopped": "ec2", "bucket.tags_missing": "s3"}  # Tipos del inventario.
    if kinds.get(event_type) is None or resource.get("type") != kinds[event_type]:
        raise PermanentError("El evento no corresponde al tipo de recurso")  # No autorizado.
    if not isinstance(resource.get("id"), str) or not resource["id"]:
        raise PermanentError("El inventario no define el identificador del recurso")
    try:  # Cualquier error de Boto3 se clasifica: transitorio se reintenta, el resto no.
        if event_type == "instance.stopped":
            return repair_instance(resource)
        return repair_bucket(resource)
    except (ClientError, BotoCoreError) as error:
        raise classify(error) from error


def handle(event: dict) -> None:
    """Completa reparación y notificación usando un registro durable por evento.

    Args:
        event: Objeto recibido de SQS, que se vuelve a validar aquí.
    Returns:
        None solo cuando reparación y aviso quedaron registrados como exitosos.
    Raises:
        ValidationError: Si el evento fue inyectado directamente a SQS y no es válido.
        RetryableError: Si la simulación o una dependencia temporal falla.
        PermanentError: Conflicto de event_id o recurso no autorizado.
        NotImplementedError: Mientras falte TODO I5-B.
    Side Effects:
        Actualiza recursos, data/events.json y el canal de comunicación.
    Notes:
        Un solo proceso modifica el ledger. Un timeout al notificar puede repetir
        un aviso: no existe una transacción común entre JSON, AWS y Telegram/Slack.
    """
    # TODO I5-B: cargar inventario y validar; cargar ledger por event_id.
    # Vincular event_id al contenido del evento; rechazar reutilización con otro contenido.
    # Guardar attempts incrementado antes de simular fallas; persiste entre reinicios.
    # Si attempts <= simulate_failures, lanzar RetryableError sin modificar recursos.
    # Si repair_done es falso: repair; guardar resultado y repair_done=True.
    # Si notified es falso: notify resumen; guardar notified=True después del éxito.
    # Si ambas etapas ya estaban completas, retornar sin efectos repetidos.
    # Cada save debe preservar el resto del ledger; no sobrescribir otros eventos.
    raise NotImplementedError("I5-B: integrar etapas y ledger durable")
