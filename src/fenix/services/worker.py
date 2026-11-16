"""Plantilla central de integración: un worker, un mensaje por vez."""
import json  # Convierte Body solo dentro del control por mensaje.
import time  # Evita un bucle intensivo si el emulador no responde.
from botocore.exceptions import BotoCoreError, ClientError
from fenix.services.sqs import receive, acknowledge, retry_later
from fenix.utils.errors import ProjectError


def _safe(value) -> str | None:
    """Devuelve un texto público y corto, o None si no es seguro registrarlo.

    Args:
        value: Dato que viene del mensaje y que no es de confianza.
    Returns:
        El mismo texto si es un str de hasta 64 caracteres; None en otro caso.
    """
    return value if isinstance(value, str) and len(value) <= 64 else None


def _process(url: str, message: dict, handler, logger) -> bool:
    """Procesa un mensaje: handler primero, confirmación después y solo si todo salió bien.

    Args:
        url: URL de la cola de trabajo.
        message: Mensaje crudo de SQS con Body, ReceiptHandle, MessageId y Attributes.
        handler: Callable handler(event) que ejecuta el caso de negocio.
        logger: Logger JSON del proceso; solo recibe contexto público.
    Returns:
        True si falló retry_later y conviene esperar antes de seguir; False en otro caso.
    Raises:
        NotImplementedError: Se propaga a propósito: revela que falta completar una tarea.
    Side Effects:
        Confirma el mensaje si terminó bien; si no, lo deja disponible para reintentar.
    """
    attempt = message.get("Attributes", {}).get("ApproximateReceiveCount")
    context = {"message_id": _safe(message.get("MessageId")),  # Antes de decodificar nada.
               "attempt": int(attempt) if str(attempt).isdigit() else None}
    try:  # Todo el control es por mensaje: uno corrupto no detiene a los demás.
        event = json.loads(message["Body"])
        if not isinstance(event, dict):  # Un JSON válido puede ser lista, número o texto.
            raise ValueError("El cuerpo no es un objeto JSON")
        context.update(event_id=_safe(event.get("event_id")),
                       resource_id=_safe(event.get("resource_id")))
        handler(event)  # Revalida, repara, avisa y deja el registro durable.
        acknowledge(url, message["ReceiptHandle"])  # Solo si el handler terminó sin errores.
        logger.info("mensaje_confirmado", extra={**context, "action": "ack"})
    except NotImplementedError:  # Revela que falta completar una tarea: no se esconde.
        raise
    except (ProjectError, ValueError, KeyError, TypeError, OSError,
            BotoCoreError, ClientError) as error:
        # Solo el nombre del tipo: el texto del error podría contener datos sensibles.
        logger.warning("fallo_procesando", extra={**context, "status": type(error).__name__})
        try:  # No se borra: vuelve a la cola y la RedrivePolicy cuenta las recepciones.
            seconds = retry_later(url, message)
            logger.info(f"reintento_programado_en_{seconds}s",
                        extra={**context, "action": "retry"})
        except (BotoCoreError, ClientError, KeyError, ValueError) as retry_error:
            logger.error("fallo_retry_later",
                         extra={**context, "status": type(retry_error).__name__})
            return True  # Indica al bucle que conviene esperar antes de seguir.
    return False


def run(url: str, handler, logger, once: bool = False) -> None:
    """Consume mensajes y confirma únicamente resultados durables.

    Args:
        url: URL de la cola de trabajo, obtenida por get_queue_url.
        handler: Callable handler(event) que revalida y ejecuta el caso de negocio.
        logger: Logger JSON del proceso worker.
        once: Si es True, realiza una sola consulta y termina; útil para pruebas.
    Returns:
        None al terminar la consulta única o al detenerse mediante Ctrl+C.
    Raises:
        NotImplementedError: Si una tarea pendiente lo lanza; se propaga a propósito.
    Side Effects:
        Recibe mensajes, ejecuta el handler y cambia o confirma su recepción.
    Notes:
        Completar I5-A antes de usar. El parseo debe ocurrir por mensaje para que
        un JSON corrupto no termine el worker ni oculte los otros mensajes.
    """
    while True:  # Ctrl+C sale por KeyboardInterrupt y lo atiende el main de la CLI.
        try:  # Un fallo de transporte no termina el worker.
            messages = receive(url)
        except (BotoCoreError, ClientError) as error:
            logger.error("fallo_receive", extra={"status": type(error).__name__})
            if once:
                return
            time.sleep(2)  # Evita un bucle intensivo si el emulador no responde.
            continue
        wait = False
        for message in messages:  # Un mensaje malo no esconde a los siguientes.
            wait = _process(url, message, handler, logger) or wait
        if once:  # Una sola consulta y termina: útil para pruebas.
            return
        if wait:  # Falló retry_later: se espera antes de volver a consultar.
            time.sleep(2)
