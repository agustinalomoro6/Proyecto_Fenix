# Proyecto Fénix – Sistema de Autorreparación de Infraestructura Cloud

**Asignatura:** Programación para Automatización II  
**Trabajo Práctico Final:** 

## 1. Descripción del proyecto

Proyecto Fénix es un sistema de autorreparación de infraestructura cloud que permite detectar problemas en recursos simulados de AWS y ejecutar acciones automáticas para recuperar su estado esperado.

El sistema utiliza webhooks autenticados, colas de mensajes SQS, un worker de procesamiento y servicios de reparación. También registra las operaciones realizadas y contempla reintentos y una cola de mensajes fallidos (DLQ).

## 2. Funcionamiento general

1. El receptor HTTP recibe un evento.
2. Verifica su autenticidad mediante una firma HMAC.
3. Valida el formato y los datos del evento.
4. Publica el evento en una cola SQS.
5. El worker recibe y procesa el mensaje.
6. El módulo de reparación actúa sobre el recurso correspondiente.
7. El sistema verifica el resultado y envía una notificación.
8. El mensaje se confirma únicamente cuando el procesamiento termina correctamente.

Si ocurre un error recuperable, el mensaje puede volver a intentarse. Los mensajes que superan el límite de reintentos se derivan a la DLQ.

## 3. Recursos y acciones de reparación

- **EC2:** si una instancia se encuentra detenida, el sistema intenta iniciarla y verifica que alcance el estado `running`.
- **S3:** si faltan etiquetas esperadas, el sistema las restaura sin eliminar las etiquetas adicionales.

La infraestructura se trabaja mediante LocalStack, sin intervenir sobre recursos reales de AWS.

## 4. Tecnologías utilizadas

- Python 3.11 o superior.
- Boto3.
- FastAPI.
- Amazon SQS y S3 simulados mediante LocalStack.
- Pytest.
- Requests.
- HMAC para autenticación de webhooks.
- Telegram o Slack para notificaciones.

## 5. Instalación y configuración

Crear y activar un entorno virtual de Python.

Instalar las dependencias:

```bash
python -m pip install -e .
```

Copiar el archivo `.env.example` como `.env` y completar las variables de configuración necesarias.

La configuración debe apuntar a LocalStack y utilizar las credenciales de prueba indicadas por la cátedra. No utilizar credenciales reales de AWS.

## 6. Comandos disponibles

La interfaz de línea de comandos incluye:

| Comando | Función |
|---|---|
| `init-queues` | Crear o recuperar las colas de trabajo y de mensajes fallidos. |
| `setup-demo` | Preparar los recursos de demostración. |
| `fault` | Inyectar una falla sobre un recurso de prueba. |
| `send` | Enviar un evento mediante el webhook. |
| `worker` | Iniciar el procesamiento de mensajes. |

Para consultar las opciones disponibles:

```bash
python -m fenix.cli --help
```

## 7. Pruebas

Ejecutar las pruebas base:

```bash
python -m pytest -m base -q
```

Ejecutar las pruebas pendientes:

```bash
python -m pytest -m pendiente -q
```

Las pruebas de integración requieren LocalStack en ejecución:

```bash
python -m pytest -m integracion -q
```

## 8. Organización del equipo

| Rol técnico | Apellido y nombre | Correo institucional | Módulos desarrollados | Pruebas técnicas defendidas |
|---|---|---|---|---|
| Integrante 1 – Entradas y Excepciones | [Completar] | [Completar] | `validation.py`, `events.py` | Validación de eventos, identificadores y fechas. |
| Integrante 2 – Mensajería e Inventario Cloud | [Completar] | [Completar] | `sqs.py`, `cloud_support.py`, `demo.py` | Creación de colas y preparación de recursos. |
| Integrante 3 – Webhooks y Reparación | [Completar] | [Completar] | `receiver.py`, `crypto.py`, `remediation.py` | Firma HMAC y reparación de EC2 y S3. |
| Integrante 4 – Observabilidad y Comunicación | [Completar] | [Completar] | `notifications.py`, `logging_json.py` | Notificaciones y registros estructurados. |
| Integrante 5 – Integración y Worker | [Completar] | [Completar] | `worker.py`, `remediation.py` | Procesamiento, persistencia e idempotencia. |
| Integrante 6 – Pruebas y Diagnóstico | [Completar] | [Completar] | `tests/`, `demo.py` | Pruebas de duplicados, ACK y DLQ. |

## 9. Seguridad y limitaciones

- La autenticación de los webhooks utiliza HMAC-SHA256.
- Las credenciales de prueba no deben reemplazarse por credenciales reales de AWS.
- La infraestructura de demostración utiliza LocalStack.
- Los eventos se validan antes de publicarse en la cola.
- Los errores se clasifican para determinar si corresponde reintentar o rechazar el procesamiento.
- El sistema registra el avance de las operaciones para evitar repetir acciones ya completadas.

## 10. Objetivo final

El objetivo de Proyecto Fénix es demostrar cómo automatizar la detección y recuperación de fallas en una infraestructura cloud simulada, integrando validaciones, mensajería, persistencia, reparación automática, notificaciones y pruebas reproducibles.
