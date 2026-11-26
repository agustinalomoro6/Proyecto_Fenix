"""Contratos de validación del integrante 1: identificadores, TTL y fechas UTC."""
import re  # Comprueba el formato de los identificadores.
from datetime import datetime, timedelta, timezone  # Fechas conscientes de UTC.
from fenix.utils.errors import ValidationError  # Error público del dominio.


def identifier(value: str) -> str:
    """Valida un identificador corto y devuelve su texto sin modificar.

    Args:
        value: str de 3 a 32 caracteres (ambos incluidos) formado solo por
            letras minúsculas a-z, dígitos 0-9 o guion.
    Returns:
        El mismo texto recibido, sin normalizar espacios ni mayúsculas.
    Raises:
        ValidationError: Si no es str o no cumple el patrón completo; por
            ejemplo rutas, mayúsculas, guion bajo, espacios o saltos de línea.
    Notes:
        Solo valida el formato. No comprueba que el recurso exista ni que sea
        del grupo: eso se resuelve contra el inventario en events.validate.
    Examples:
        identifier("grupo-01") devuelve "grupo-01"; "../ajeno" debe fallar.
    """
    # Primero el tipo: re.fullmatch lanzaría TypeError con algo que no es texto.
    if not isinstance(value, str) or re.fullmatch(r"[a-z0-9-]{3,32}", value) is None:
        # El mensaje no copia la entrada: podría ser una ruta o un dato sensible.
        raise ValidationError(
            "Identificador inválido: usar de 3 a 32 caracteres entre "
            "minúsculas, dígitos o guion")
    return value  # Sin cambios: pasar a minúsculas cambiaría la identidad.


def ttl_seconds(value: str) -> int:
    """Valida el TTL didáctico empleado en la opción de entornos efímeros.

    Args:
        value: str con un entero de 60 a 600 (ambos incluidos) en forma canónica,
            es decir, str(int(value)) == value.
    Returns:
        El número entero de segundos.
    Raises:
        ValidationError: Si no es str, no es un entero, no está en forma canónica
            (signo "+", espacios, ceros iniciales, guion bajo) o está fuera de
            rango.
    Notes:
        No normaliza la entrada: " 60", "+60" y "060" se rechazan. Es una
        práctica común del helper: los subcomandos actuales de fenix.cli no la
        utilizan.
    Examples:
        ttl_seconds("60") devuelve 60; ttl_seconds("060") debe fallar.
    """
    if not isinstance(value, str):  # El contrato recibe texto.
        raise ValidationError("El TTL debe indicarse como texto con un entero")
    try:  # int() rechaza decimales ("60.5") y texto ("abc").
        ttl = int(value)
    except ValueError as error:  # Conserva la causa original con "from".
        raise ValidationError("El TTL debe ser un entero de segundos") from error
    if str(ttl) != value:  # int() tolera "+60", "060" o " 60"; el contrato no.
        raise ValidationError("El TTL debe escribirse como un entero simple")
    if not 60 <= ttl <= 600:  # Ambos límites incluidos; no se redondea.
        raise ValidationError("El TTL debe estar entre 60 y 600 segundos")
    return ttl


def utc_text(value: str) -> datetime:
    """Interpreta una fecha UTC explícita sin aceptar fechas ingenuas.

    Args:
        value: str con fecha y hora en un formato ISO 8601 que entienda
            datetime.fromisoformat (Python 3.11 o superior), con UTC explícito:
            una "Z" mayúscula al final o un desplazamiento cero como "+00:00".
    Returns:
        datetime con tzinfo=timezone.utc.
    Raises:
        ValidationError: Si no es str, el formato es inválido, falta la zona o
            el desplazamiento es distinto de cero (por ejemplo "-03:00").
    Notes:
        La "Z" final se convierte en "+00:00" antes de interpretar el texto. No
        se convierten otras zonas horarias a UTC: se rechazan.
    Examples:
        utc_text("2026-10-22T18:00:00Z") es válido;
        utc_text("2026-10-22T18:00:00") debe fallar.
    """
    if not isinstance(value, str):  # Una fecha llega siempre como texto.
        raise ValidationError("La fecha debe ser texto ISO 8601 con zona UTC")
    # Solo la "Z" mayúscula final se traduce a "+00:00".
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:  # Un formato roto lanza ValueError.
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValidationError("Fecha inválida: usar ISO 8601, por ejemplo "
                              "2026-10-22T18:00:00Z") from error
    if parsed.tzinfo is None:  # Sin zona no hay comparación segura.
        raise ValidationError("La fecha debe incluir zona UTC (Z o +00:00)")
    if parsed.utcoffset() != timedelta(0):  # Solo UTC.
        raise ValidationError("La fecha debe estar en UTC, sin otro offset")
    return parsed.astimezone(timezone.utc)

