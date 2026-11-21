# Proyecto Fénix – Sistema de Autorreparación de Infraestructura Cloud

**Asignatura:** Programación para Automatización II  
**Trabajo Práctico Final:** Opción 4.3.1  
**Proyecto:** Fénix – Sistema de Autorreparación de Infraestructura Cloud

---

## 1. Descripción del proyecto

Proyecto Fénix es un sistema de autorreparación de infraestructura cloud que permite detectar problemas en recursos simulados de AWS y ejecutar acciones automáticas para recuperar su estado esperado.

El sistema está diseñado para recibir eventos de fallas, validarlos, procesarlos mediante una cola de mensajes y ejecutar acciones de reparación sobre los recursos afectados.

La solución integra webhooks autenticados, mensajería mediante Amazon SQS, un worker de procesamiento y servicios de reparación. Además, incorpora mecanismos de persistencia, control de duplicados, reintentos y una cola de mensajes fallidos (DLQ).

El objetivo es demostrar cómo aplicar técnicas de automatización para mejorar la disponibilidad y recuperación de una infraestructura cloud.

## 2. Funcionamiento general

El funcionamiento del sistema sigue el siguiente flujo:

1. El receptor HTTP recibe un evento de falla mediante un webhook.
2. Verifica la autenticidad del mensaje mediante una firma HMAC-SHA256.
3. Valida el formato, los identificadores y los datos del evento.
4. Publica el evento validado en una cola SQS.
5. El worker recibe el mensaje y comienza su procesamiento.
6. El servicio de reparación identifica el recurso afectado y ejecuta la acción correspondiente.
7. El sistema verifica el resultado de la reparación.
8. Se registra el resultado y se genera la notificación correspondiente.
9. El mensaje se confirma mediante ACK cuando el procesamiento finaliza correctamente.

Si ocurre un error recuperable, el mensaje puede volver a procesarse mediante los mecanismos de reintento.

Cuando se supera el límite establecido de reintentos, el mensaje se deriva a la Dead Letter Queue (DLQ) para su posterior diagnóstico.

## 3. Recursos y acciones de reparación

El proyecto contempla dos tipos principales de recursos:

### 3.1. Instancias EC2

Cuando una instancia se encuentra detenida (`stopped`), el sistema intenta iniciarla y verifica que alcance el estado esperado (`running`).

### 3.2. Buckets S3

Cuando un bucket presenta etiquetas faltantes, el sistema restaura las etiquetas esperadas sin eliminar las etiquetas adicionales existentes.

### 3.3. Entorno de simulación

Las operaciones se realizan mediante LocalStack, que permite simular servicios de AWS en un entorno local de desarrollo y pruebas, sin intervenir sobre infraestructura real.

## 4. Tecnologías utilizadas

- **Python 3.11 o superior:** lenguaje principal del proyecto.
- **Boto3:** interacción con los servicios de AWS simulados.
- **FastAPI:** implementación del receptor HTTP.
- **Amazon SQS:** mensajería y procesamiento asincrónico.
- **Amazon S3 y EC2:** recursos de infraestructura simulados.
- **LocalStack:** entorno local de simulación de servicios cloud.
- **Pytest:** ejecución de pruebas automatizadas.
- **Requests:** comunicación HTTP.
- **HMAC-SHA256:** autenticación e integridad de webhooks.
- **Telegram o Slack:** canales de notificación, según la configuración utilizada.

## 5. Instalación y configuración

### 5.1. Requisitos previos

Antes de ejecutar el proyecto se necesita:

- Python 3.11 o superior.
- Docker.
- LocalStack.
- Git.
- Un entorno virtual de Python.

### 5.2. Obtener el proyecto

Clonar el repositorio:

```bash
git clone https://github.com/agustinalomoro6/Proyecto_Fenix.git
```

Ingresar a la carpeta:

```bash
cd Proyecto_Fenix
```

### 5.3. Crear el entorno virtual

```bash
python -m venv .venv
```

Activar el entorno virtual en Windows:

```bash
.venv\Scripts\activate
```

En Linux o macOS:

```bash
source .venv/bin/activate
```

### 5.4. Instalar las dependencias

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

### 5.5. Configurar las variables de entorno

Copiar el archivo de ejemplo:

```bash
copy .env.example .env
```

En Linux o macOS:

```bash
cp .env.example .env
```

Completar las variables necesarias para la ejecución del proyecto.

La configuración debe apuntar a LocalStack y utilizar las credenciales de prueba indicadas por la cátedra.

**Importante:** no incorporar credenciales reales de AWS ni publicar información sensible en el repositorio.

## 6. Ejecución del sistema

La interfaz de línea de comandos permite realizar distintas operaciones para preparar, ejecutar y probar el sistema.

### 6.1. Consultar los comandos disponibles

```bash
python -m fenix.cli --help
```

### 6.2. Comandos principales

| Comando | Función |
|---|---|
| `init-queues` | Crear o recuperar las colas de trabajo y de mensajes fallidos. |
| `setup-demo` | Preparar los recursos de demostración. |
| `fault` | Inyectar una falla sobre un recurso de prueba. |
| `send` | Enviar un evento mediante el webhook. |
| `worker` | Iniciar el procesamiento de mensajes. |

Para conocer los parámetros específicos de cada operación, consultar la ayuda de la CLI.

### 6.3. Flujo de demostración

La demostración del proyecto contempla las siguientes etapas:

1. Preparar el entorno LocalStack.
2. Configurar las variables de entorno.
3. Inicializar las colas de mensajes.
4. Preparar los recursos de prueba.
5. Inyectar una falla sobre un recurso.
6. Enviar el evento correspondiente.
7. Ejecutar el worker para procesar el mensaje.
8. Comprobar el resultado de la reparación.
9. Verificar los registros y las notificaciones generadas.

Los comandos y parámetros concretos de cada etapa deben ejecutarse según las opciones disponibles en la versión instalada.

## 7. Pruebas automatizadas

El proyecto utiliza Pytest para verificar el funcionamiento de los distintos componentes.

### 7.1. Pruebas base

```bash
python -m pytest -m base -q
```

### 7.2. Pruebas pendientes

```bash
python -m pytest -m pendiente -q
```

### 7.3. Pruebas de integración

Las pruebas de integración requieren que LocalStack se encuentre correctamente iniciado y configurado.

```bash
python -m pytest -m integracion -q
```

### 7.4. Objetivos de las pruebas

Las pruebas contemplan la verificación de:

- Validación de eventos e identificadores.
- Autenticación de webhooks mediante HMAC.
- Creación y utilización de colas SQS.
- Procesamiento de mensajes.
- Reparación de instancias EC2.
- Restauración de etiquetas S3.
- Persistencia del estado de procesamiento.
- Control de eventos duplicados e idempotencia.
- Confirmación de mensajes mediante ACK.
- Reintentos ante errores recuperables.
- Derivación de mensajes fallidos a la DLQ.
- Registro de operaciones y notificaciones.

La ejecución de cada grupo permite comprobar el comportamiento de los componentes y detectar posibles errores durante la integración.

## 8. Organización del equipo

El desarrollo se organizó mediante la distribución de responsabilidades técnicas entre seis integrantes, contemplando módulos específicos y pruebas asociadas a cada área.

| Rol técnico | Apellido y nombre | Correo institucional | Módulos desarrollados | Pruebas técnicas defendidas |
|---|---|---|---|---|
| Integrante 1 – Entradas y Excepciones | Carmela Luciana A. Choque Mojica | luuch77@gmail.com | `validation.py`, `events.py` | Validación de eventos, identificadores y fechas. |
| Integrante 2 – Mensajería e Inventario Cloud | Abel David Acuña | abeldavidok@gmail.com | `sqs.py`, `cloud_support.py`, `demo.py` | Creación de colas y preparación de recursos. |
| Integrante 3 – Webhooks y Reparación | Agustina Leonor Lomoro De la Cuesta | agustinaomoro6@gmail.com | `receiver.py`, `crypto.py`, `remediation.py` | Firma HMAC y reparación de EC2 y S3. |
| Integrante 4 – Observabilidad y Comunicación | Ramiro J. D. Vázquez S. | vazquez.ramiro@gmail.com | `notifications.py`, `logging_json.py` | Notificaciones y registros estructurados. |
| Integrante 5 – Integración y Worker | Néstor Jonatan Villalba | nestorvilla555@hotmail.com | `worker.py`, `remediation.py` | Procesamiento, persistencia e idempotencia. |
| Integrante 6 – Pruebas y Diagnóstico | Rubén Américo Jurado | americorubenjurado2@gmail.com | `tests/`, `demo.py` | Pruebas de duplicados, ACK y DLQ. |

## 9. Seguridad y limitaciones

El sistema contempla diferentes mecanismos para proteger el procesamiento de eventos y evitar operaciones incorrectas:

- Autenticación de webhooks mediante HMAC-SHA256.
- Validación de los eventos antes de su publicación en la cola.
- Uso de credenciales de prueba para el entorno de simulación.
- Separación entre errores recuperables y errores permanentes.
- Mecanismos de reintento para errores recuperables.
- Utilización de una DLQ para mensajes que superan el límite de reintentos.
- Persistencia del estado de procesamiento para evitar repetir operaciones ya completadas.
- Control de duplicados mediante mecanismos de idempotencia.

**Limitaciones:** el proyecto utiliza LocalStack para simular los servicios cloud. Por lo tanto, la demostración permite evaluar la lógica de automatización y recuperación, pero no representa una implementación productiva sobre infraestructura real de AWS.

## 10. Objetivo final

El objetivo de Proyecto Fénix es demostrar cómo automatizar la detección y recuperación de fallas en una infraestructura cloud simulada.

Mediante la integración de validaciones, autenticación, mensajería asincrónica, persistencia, reparación automática, notificaciones y pruebas automatizadas, el proyecto busca mostrar una solución modular y organizada para mejorar la confiabilidad de los sistemas informáticos.

Además, permite aplicar conocimientos de programación, automatización, integración de servicios cloud, manejo de errores y trabajo colaborativo mediante Git y GitHub.

---

**Repositorio oficial:**  
https://github.com/agustinalomoro6/Proyecto_Fenix

**Video de Defensa:**
https://drive.google.com/drive/folders/1TuFwbKGx6Yn0PHrS5HUVPgX6h0dVhbsH?usp=drive_link

