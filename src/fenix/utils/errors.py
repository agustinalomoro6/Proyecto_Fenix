"""Excepciones compartidas del proyecto; integrante 1.

Jerarquía: Exception -> ProjectError -> ValidationError, RetryableError y
PermanentError. Ninguna define un constructor propio: todas reciben el mensaje
igual que Exception, por ejemplo ValidationError("event_type no permitido").
"""


class ProjectError(Exception):
    """Error controlado del TP; base común de las excepciones del proyecto.

    Hereda de Exception y no agrega constructor propio. Capturar ProjectError
    atrapa también a sus tres subclases; si llega hasta la CLI, esta lo
    registra y termina con código 1.

    Args:
        message: Descripción pública, sin tokens ni URLs privadas.
    """


class ValidationError(ProjectError):
    """Entrada o contrato inválido, o recurso fuera del inventario autorizado.

    La clase solo comunica el rechazo: quien la captura decide cómo traducirlo.
    El receptor responde 401 si falla la firma y 422 si falla el contrato; el
    worker no confirma el mensaje y programa un reintento.

    Args:
        message: Regla incumplida, sin copiar secretos de la entrada.
    """


class RetryableError(ProjectError):
    """Fallo transitorio y recuperable de un paso que quedó pendiente.

    La excepción no aplica Retry-After ni programa nada en la cola por sí sola.
    Es el worker quien, al capturarla, cambia la visibilidad del mensaje para que
    SQS lo vuelva a entregar.

    Args:
        message: Descripción del paso pendiente, sin datos sensibles.
    """


class PermanentError(ProjectError):
    """Fallo no recuperable: conflicto, configuración o recurso no autorizado.

    El worker no confirma el mensaje (no hace ACK, para no ocultar el fallo): lo
    conserva y, al agotar las recepciones, la RedrivePolicy lo mueve a la DLQ.

    Args:
        message: Motivo público del rechazo definitivo del evento.
    """
