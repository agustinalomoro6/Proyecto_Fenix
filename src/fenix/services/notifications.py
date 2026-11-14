"""Adaptador HTTP guiado. Elegir Telegram O Slack, no ambos obligatoriamente."""
import os  # Recupera credenciales fuera del repositorio.
import requests  # Aplica timeout explícito a cada llamada HTTP.
from fenix.utils.errors import PermanentError, RetryableError
 
 
def _post(url: str, payload: dict) -> requests.Response:
    """Hace el POST con timeout y sin dejar rastros de la URL en los errores.
 
    Args:
        url: Dirección del proveedor; puede contener el token, por eso no se registra.
        payload: Cuerpo JSON del mensaje.
    Returns:
        La respuesta HTTP, sin interpretar todavía.
    Raises:
        RetryableError: Timeout o falla de conexión.
        PermanentError: URL inválida u otro error de la librería.
    """
    try:  # timeout=(conexión, lectura): una llamada colgada nunca bloquea al worker.
        return requests.post(url, json=payload, timeout=(2, 5))
    except (requests.Timeout, requests.ConnectionError):
        # "from None" descarta la excepción original: su texto puede incluir la URL con el token.
        raise RetryableError("El proveedor no respondió a tiempo; se reintentará") from None
    except requests.RequestException:
        raise PermanentError("No se pudo enviar la solicitud al proveedor") from None
 
 
def _retry_after(response: requests.Response) -> int:
    """Lee la espera pedida por el proveedor y la acota entre 1 y 60 segundos.
 
    Args:
        response: Respuesta 429 del proveedor.
    Returns:
        Segundos de espera; 5 si el proveedor no indica un valor utilizable.
    """
    value = response.headers.get("Retry-After")  # Slack y otros usan esta cabecera.
    if value is None:  # Telegram la informa en el JSON de la respuesta.
        try:
            value = response.json().get("parameters", {}).get("retry_after")
        except (ValueError, AttributeError):
            value = None
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return 5  # Valor por defecto, acotado.
    return max(1, min(seconds, 60))  # Nunca se promete una demora ilimitada.
 
 
def _check_status(response: requests.Response) -> None:
    """Traduce el código HTTP a un error reintentable o permanente.
 
    Args:
        response: Respuesta del proveedor.
    Raises:
        RetryableError: 429 o 5xx.
        PermanentError: Cualquier otro código que no sea 200.
    """
    status = response.status_code
    if status == 429:  # Límite de tasa: transitorio, con espera acotada.
        wait = _retry_after(response)  # Espera pedida por el proveedor, acotada.
        raise RetryableError(f"Límite de tasa del proveedor (429); esperar {wait} s")
    if status >= 500:  # Falla del proveedor: transitoria.
        raise RetryableError(f"El proveedor respondió {status}; se reintentará")
    if status != 200:  # Otros 4xx (token inválido, chat inexistente): no se reintenta.
        raise PermanentError(f"El proveedor rechazó la solicitud ({status})")
 
 
def notify(text: str) -> None:
    """Envía un mensaje breve y valida la respuesta del proveedor seleccionado.
 
    Args:
        text: Resumen público de hasta 1000 caracteres, sin secretos ni raw body.
    Returns:
        None únicamente después de confirmar éxito del proveedor.
    Raises:
        RetryableError: Timeout, conexión, 429 o respuesta 5xx.
        PermanentError: Configuración inválida, 4xx definitivo o rechazo funcional.
    Side Effects:
        Publica en el chat/canal del grupo. Un timeout puede causar duplicados.
    Notes:
        El modo console sirve para desarrollo; no reemplaza la evidencia final real.
        No registrar la excepción requests original: puede contener el token en URL.
    """
    mode = os.getenv("NOTIFY_PROVIDER", "console")  # Selecciona un adaptador explícito.
    if mode == "console":  # Ensayo local sin credenciales de terceros.
        print(text[:1000])  # No imprimir eventos completos o URLs privadas.
        return  # El modo debe figurar en el informe de pruebas.
    text = text[:1000]  # Resumen público acotado; nunca el evento completo.
    if mode == "telegram":
        token, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat:  # Sin credenciales no hay nada que reintentar.
            raise PermanentError("Configuración de Telegram incompleta")
        response = _post(f"https://api.telegram.org/bot{token}/sendMessage",
                         {"chat_id": chat, "text": text})
        _check_status(response)
        try:  # Telegram responde JSON; un HTTP 200 solo no basta.
            confirmed = response.json().get("ok") is True
        except (ValueError, AttributeError):
            confirmed = False
        if not confirmed:
            raise PermanentError("Telegram no confirmó el envío")
    elif mode == "slack":
        url = os.getenv("SLACK_WEBHOOK_URL", "")
        if not url.startswith("https://"):  # El webhook es un secreto y debe ir por HTTPS.
            raise PermanentError("Configuración de Slack incompleta")
        response = _post(url, {"text": text})
        _check_status(response)
        if response.text.strip() != "ok":  # Slack confirma con el cuerpo "ok".
            raise PermanentError("Slack no confirmó el envío")
    else:
        raise PermanentError("NOTIFY_PROVIDER no es válido")

