"""Contratos de validación del integrante 1: identificadores, TTL y fechas UTC."""
import re  # Comprueba el formato de los identificadores.
from datetime import datetime, timedelta, timezone  # Fechas conscientes de UTC.
from fenix.utils.errors import ValidationError  # Error público del dominio.


def identifier(value: str) -> str:
    """Valida un identificador corto y devuelve su texto sin modificar.

    Args:
        value: Texto entre 3 y 32 caracteres; letras minúsculas, dígitos o guion.
    Returns:
        El identificador original válido.
    Raises:
        ValidationError: Si el tipo o el patrón no cumplen el contrato.
    Examples:
        identifier("grupo-01") devuelve "grupo-01"; "../ajeno" debe fallar.
    """
    # Primero el tipo: re.fullmatch lanzaría TypeError con algo que no es texto.
    if not isinstance(value, str) or re.fullmatch(r"[a-z0-9-]{3,32}", value) is None:
        # El mensaje no copia la entrada: podría ser una ruta o un dato sensible.
        raise ValidationError(
            "Identificador inválido: usar de 3 a 32 caracteres entre "
            "minúsculas, dígitos o guion")
    return value  # Se devuelve tal cual: pasar a minúsculas cambiaría la identidad.


def ttl_seconds(value: str) -> int:
    """Valida el TTL didáctico empleado en la opción de entornos efímeros.

    Args:
        value: Texto con un entero entre 60 y 600 segundos inclusive.
    Returns:
        El número entero de segundos.
    Raises:
        ValidationError: Si no es entero o está fuera de los límites.
    Notes:
        La CLI traduce ValidationError a parser.error para salir con código 2.
    """
    if not isinstance(value, str):  # El contrato recibe texto, como llega de la CLI.
        raise ValidationError("El TTL debe indicarse como texto con un entero")
    try:  # int() rechaza decimales ("60.5") y texto ("abc").
        ttl = int(value)
    except ValueError as error:  # Se encadena la causa original con "from".
        raise ValidationError("El TTL debe ser un entero de segundos") from error
    if str(ttl) != value:  # int() tolera "+60", "6_0" o " 60"; el contrato no.
        raise ValidationError("El TTL debe escribirse como un entero simple")
    if not 60 <= ttl <= 600:  # Ambos límites están incluidos; no se redondea.
        raise ValidationError("El TTL debe estar entre 60 y 600 segundos")
    return ttl


def utc_text(value: str) -> datetime:
    """Interpreta una fecha UTC explícita sin aceptar fechas ingenuas.

    Args:
        value: ISO 8601 terminado en Z o con offset +00:00.
    Returns:
        Fecha con zona UTC; por ejemplo 2026-10-22T18:00:00+00:00.
    Raises:
        ValidationError: Si falta zona, hay offset no nulo o formato inválido.
    """
    if not isinstance(value, str):  # Una fecha llega siempre como texto.
        raise ValidationError("La fecha debe ser texto ISO 8601 con zona UTC")
    # fromisoformat entiende +00:00; la Z final se traduce explícitamente.
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:  # Un formato roto lanza ValueError, que se traduce al error público.
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValidationError("Fecha inválida: usar ISO 8601, por ejemplo "
                              "2026-10-22T18:00:00Z") from error
    if parsed.tzinfo is None:  # Sin zona no hay comparación segura entre equipos.
        raise ValidationError("La fecha debe incluir zona UTC (Z o +00:00)")
    if parsed.utcoffset() != timedelta(0):  # Solo UTC; -03:00 también se rechaza.
        raise ValidationError("La fecha debe estar en UTC, sin otro offset")
    return parsed.astimezone(timezone.utc)  # Normaliza el tipo de zona devuelto.
