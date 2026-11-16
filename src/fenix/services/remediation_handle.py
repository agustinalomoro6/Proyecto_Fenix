INVENTORY_PATH = "data/inventory.json"  # Lo prepara setup-demo.
LEDGER_PATH = "data/events.json"  # Un registro durable por event_id.


def _store(event_id: str, entry: dict) -> None:
    """Guarda un registro sin pisar los de los demás eventos.

    Args:
        event_id: Identificador del evento al que pertenece el registro.
        entry: Estado durable de ese evento.
    Side Effects:
        Relee el ledger, reemplaza solo esta clave y lo publica de forma atómica.
    """
    ledger = load(LEDGER_PATH)  # Se relee para conservar el resto del ledger.
    ledger[event_id] = entry
    save(LEDGER_PATH, ledger)


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
    Side Effects:
        Actualiza recursos, data/events.json y el canal de comunicación.
    Notes:
        Un solo proceso modifica el ledger. Un timeout al notificar puede repetir
        un aviso: no existe una transacción común entre JSON, AWS y Telegram/Slack.
    """
    inventory = load(INVENTORY_PATH)
    valid = validate(event, inventory)  # El evento pudo inyectarse directo en SQS: se revalida.
    event_id = valid["event_id"]
    entry = load(LEDGER_PATH).get(event_id)  # Registro durable de este evento, si existe.
    if entry is None:
        entry = {"event": valid, "attempts": 0, "repair_done": False, "notified": False}
    elif entry["event"] != valid:  # Mismo event_id con otro contenido: nunca se mezcla.
        raise PermanentError("El event_id ya se usó con otro contenido")
    if entry["repair_done"] and entry["notified"]:  # Duplicado de algo ya terminado.
        return  # Sin efectos repetidos: ni reparación ni aviso.
    entry["attempts"] += 1  # Se guarda ANTES de simular fallas: sobrevive al reinicio.
    _store(event_id, entry)
    if entry["attempts"] <= valid["simulate_failures"]:  # Falla de laboratorio.
        raise RetryableError("Falla simulada de laboratorio")  # No toca ningún recurso.
    if not entry["repair_done"]:
        entry["result"] = repair(inventory[valid["resource_id"]], valid["event_type"])
        entry["repair_done"] = True  # Se persiste apenas termina la reparación.
        _store(event_id, entry)
    if not entry["notified"]:
        notify(f"Fénix: {event_id} ({valid['event_type']}) sobre {valid['resource_id']}: "
               f"{entry['result']}")  # Resumen público: nunca el evento completo.
        entry["notified"] = True  # Solo después de que el aviso tuvo éxito.
        _store(event_id, entry)
