"""Firma de apoyo y verificación a completar por el integrante 3."""
import hashlib  # Selecciona SHA-256 para autenticar el contenido.
import hmac  # Usa una comparación segura para las firmas.
import re  # Comprueba que v1 sea exactamente 64 caracteres hexadecimales.
import time  # Comprueba la ventana temporal.
from fenix.utils.errors import ValidationError  # Rechazo de autenticación público.


def signature(secret: str, timestamp: int, body: bytes) -> str:
    """Firma exactamente timestamp, punto y cuerpo binario original.

    Args:
        secret: Secreto compartido de al menos 16 caracteres, leído del entorno.
        timestamp: Unix epoch en segundos, igual al enviado en la cabecera.
        body: Bytes exactos enviados por HTTP; no volver a serializar el JSON.
    Returns:
        HMAC-SHA256 hexadecimal de 64 caracteres.
    Raises:
        ValidationError: Si el secreto es demasiado corto.
    """
    if len(secret) < 16:  # Se comprueba también al enviar la prueba.
        raise ValidationError("Configurar WEBHOOK_SECRET de 16 caracteres o más")
    signed = str(timestamp).encode("ascii") + b"." + body  # Prefijo autenticado.
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify(secret: str, header: str, body: bytes, now: int | None = None) -> None:
    """Rechaza cabeceras ambiguas y firmas o fechas inválidas.

    Args:
        secret: Secreto compartido del entorno, nunca del payload.
        header: Cabecera exacta t=<epoch>,v1=<hex> sin claves duplicadas.
        body: Bytes del cuerpo antes de llamar a json.loads.
        now: Reloj inyectable para pruebas; None usa time.time.
    Returns:
        None si las comprobaciones son satisfactorias.
    Raises:
        ValidationError: Formato inválido, firma incorrecta o diferencia mayor a 300 s.
    Notes:
        La ventana de tiempo mitiga replay antiguo. No impide repetir un evento
        válido dentro de la ventana; event_id e idempotencia cubren ese caso.
        Los mensajes de error no incluyen la cabecera, la firma ni el secreto.
    """
    if not isinstance(header, str) or not isinstance(body, bytes):  # Tipos del contrato.
        raise ValidationError("Cabecera de firma inválida")
    parts = header.split(",")  # Debe haber exactamente dos pares: t y v1.
    if len(parts) != 2:
        raise ValidationError("Cabecera de firma inválida")
    fields = {}
    for part in parts:  # Se arma el diccionario rechazando pares rotos o repetidos.
        key, separator, value = part.partition("=")
        if not separator or key in fields:  # Sin "=" o clave duplicada: ambiguo.
            raise ValidationError("Cabecera de firma inválida")
        fields[key] = value
    if set(fields) != {"t", "v1"}:  # Ni claves de menos ni claves desconocidas.
        raise ValidationError("Cabecera de firma inválida")
    raw_timestamp, received = fields["t"], fields["v1"]
    # isascii evita dígitos de otros alfabetos; isdigit descarta signos, puntos y espacios.
    if not (raw_timestamp.isascii() and raw_timestamp.isdigit()):
        raise ValidationError("Cabecera de firma inválida")
    try:  # Conversión explícita: cualquier fallo se traduce al error público.
        timestamp = int(raw_timestamp)
    except ValueError as error:
        raise ValidationError("Cabecera de firma inválida") from error
    if re.fullmatch(r"[0-9a-f]{64}", received) is None:  # SHA-256 en hexadecimal minúscula.
        raise ValidationError("Cabecera de firma inválida")
    current = int(time.time()) if now is None else now  # Reloj inyectable en pruebas.
    if abs(current - timestamp) > 300:  # Ventana de 5 minutos, pasado y futuro.
        raise ValidationError("Fecha fuera de la ventana permitida")
    expected = signature(secret, timestamp, body)  # Firma esperada sobre los bytes crudos.
    if not hmac.compare_digest(expected, received):  # Tiempo constante: nunca "==".
        raise ValidationError("Firma inválida")
