"""Gu├¡a ejecutable del integrante 6; sustituir cada pendiente por aserciones reales."""
import pytest  # Mantiene visibles los casos sin implementar.

@pytest.mark.pendiente
def test_duplicate_is_idempotent():
    """Comprueba que repetir un evento no repite recursos ni acciones completadas.

    Returns:
        None cuando dos ejecuciones conservan el estado final esperado.
    Raises:
        NotImplementedError: Hasta que I6 implemente la preparaci├│n y aserciones.
    Notes:
        Usar un cliente falso con contador de llamadas; reinicializar el handler
        leyendo el mismo ledger para que el ensayo represente un reinicio.
    """
    # TODO I6-B: preparar inventario/manifiesto v├ílido en tmp_path y evento fijo.
    # Ejecutar handler dos veces; verificar IDs y una sola acci├│n efectiva.
    # Guardar/releer el estado antes de la segunda ejecuci├│n; no usar un set en memoria.
    raise NotImplementedError("I6-B: prueba durable de duplicados")

@pytest.mark.pendiente
def test_ack_is_after_success(monkeypatch):
    import json
    import logging
    from fenix.services import worker

    message = {
        "Body": json.dumps({
            "event_id": "evt-ack-001",
            "resource_id": "node-01"
        }),
        "ReceiptHandle": "receipt-123",
        "MessageId": "message-123",
        "Attributes": {"ApproximateReceiveCount": "1"}
    }

    actions = []

    monkeypatch.setattr(worker, "receive", lambda url: [message])
    monkeypatch.setattr(
        worker, "acknowledge",
        lambda url, receipt: actions.append(("ack", receipt))
    )
    monkeypatch.setattr(
        worker, "retry_later",
        lambda url, msg: actions.append(("retry", None)) or 1
    )

    def failing_handler(event):
        actions.append(("handler", None))
        raise ValueError("fallo simulado")

    worker.run("queue-test", failing_handler, logging.getLogger("test"), once=True)

    assert ("handler", None) in actions
    assert ("retry", None) in actions
    assert not any(action[0] == "ack" for action in actions)

    actions.clear()

    def successful_handler(event):
        actions.append(("handler", None))

    worker.run("queue-test", successful_handler, logging.getLogger("test"), once=True)

    assert actions == [
        ("handler", None),
        ("ack", "receipt-123")
    ]

@pytest.mark.integracion
def test_redrive_with_localstack():
    """Comprueba DLQ efectiva usando el broker, no una lista simulada en Python.

    Returns:
        None si un mensaje venenoso termina en la DLQ y el worker sigue vivo.
    Raises:
        NotImplementedError: Hasta implementar el ensayo con espera total acotada.
    Side Effects:
        Crea colas de prueba exclusivas y las limpia despu├®s de guardar evidencia.
    Notes:
        Usar un prefijo de test nuevo y no purgar colas del laboratorio del grupo.
    """
    # TODO I6-D: publicar JSON corrupto en una cola con RedrivePolicy real.
    # Consumir con el worker y consultar DLQ con deadline total de 120 segundos.
    # Comparar el Body original; un contador aproximado por s├¡ solo no demuestra redrive.
    # Si se agota el deadline, fallar con diagn├│stico; no pasar el test por timeout.
    raise NotImplementedError("I6-D: verificar redrive real en LocalStack")
