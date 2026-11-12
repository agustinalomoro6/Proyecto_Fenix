"""Receptor FastAPI: autenticación, validación y aceptación durable por SQS."""
import os  # Recupera el secreto sin incluirlo en el repositorio.
import json  # Decodifica después de verificar los bytes.
from fastapi import FastAPI, Request, HTTPException  # Interfaz HTTP del curso.
from starlette.concurrency import run_in_threadpool  # Evita bloquear el event loop.
from botocore.exceptions import BotoCoreError, ClientError
from fenix.utils.crypto import verify
from fenix.utils.errors import ValidationError
from fenix.utils.state import load
from fenix.services.events import validate
from fenix.services.sqs import queue_url, publish

app = FastAPI(title="Fénix receptor de alertas")  # Un servidor, un worker Uvicorn.

@app.post("/webhook", status_code=202)
async def webhook(request: Request) -> dict:
    """Recibe un evento firmado y contesta 202 solo después de encolarlo.

    Args:
        request: Petición con X-Webhook-Signature y cuerpo de hasta 16 KiB.
    Returns:
        JSON con status=accepted, event_id y message_id de SQS.
    Raises:
        HTTPException: 401 firma; 400 JSON; 413 tamaño; 422 contrato; 500 sin clave;
            503 SQS.
    Side Effects:
        Publica en SQS; no repara recursos ni llama a Telegram/Slack aquí.
    Notes:
        Leer bytes completos basta para el laboratorio; un proxy limitaría antes
        el tamaño de la transferencia en un despliegue real.
    """
    raw = await request.body()  # Se conservan los bytes originales.
    if len(raw) > 16384:  # Mantiene acotados los ejemplos didácticos.
        raise HTTPException(413, "Cuerpo demasiado grande")  # No encola.
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if len(secret) < 16:  # Es un error del servidor, no del cliente: no es un 401.
        raise HTTPException(500, "Receptor sin clave configurada")
    try:  # Primero se autentica: nada se interpreta ni se encola sin firma válida.
        verify(secret, request.headers.get("X-Webhook-Signature", ""), raw)
    except ValidationError as error:  # Firma, fecha o formato: siempre el mismo mensaje.
        raise HTTPException(401, "Firma o fecha inválida") from error
    try:  # Solo ahora se decodifica: la firma ya cubrió los bytes originales.
        event = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(400, "El cuerpo no es JSON válido") from error
    inventory = await run_in_threadpool(load, "data/inventory.json")  # Lectura de disco.
    try:  # Esquema cerrado y recurso autorizado; los mensajes de error son públicos.
        validated = validate(event, inventory)
    except ValidationError as error:
        raise HTTPException(422, str(error)) from error
    try:  # Las llamadas a Boto3 son bloqueantes: se ejecutan fuera del event loop.
        url = await run_in_threadpool(queue_url, os.environ["QUEUE_PREFIX"])
        message_id = await run_in_threadpool(publish, url, validated)
    except (ClientError, BotoCoreError) as error:  # No se promete aceptación sin SQS.
        raise HTTPException(503, "Cola no disponible; reintentar más tarde") from error
    # Solo se llega aquí si send_message tuvo éxito: recién ahora se acepta.
    return {"status": "accepted", "event_id": validated["event_id"], "message_id": message_id}
