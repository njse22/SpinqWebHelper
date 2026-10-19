# Servicio web de ejecución de circuitos sobre el NMR (n8n + FastAPI + RQ)

Este despliegue permite que un usuario envíe un **circuito cuántico en código
Python** (definido con la API nativa `Circuit` de SpinQit o con `QuantumCircuit`
estilo Qiskit) y reciba el resultado (`counts` y `probabilities`) renderizado en
**HTML**.

El equipo NMR (`10.10.94.171:8989`) es un recurso físico único, por lo que las
ejecuciones se encolan y se procesan **de a una** mediante Redis + RQ.

## Arquitectura

```
Usuario ──POST {code}──> n8n (Webhook)
                           │  HTTP Request: POST /execute (envía code + resume_url)
                           ▼
                     quantum-api (FastAPI) ──encola──> Redis
                                                        │
                                                        ▼
                     quantum-worker (RQ) ──TCP──> Equipo NMR 10.10.94.171:8989
                           │  guarda resultado
                           │  callback a n8n (resume_url)
                           ▼
                     n8n renderiza HTML ──> Respuesta HTML al usuario
```

### Servicios

| Servicio        | Imagen / build       | Rol                                                      |
|-----------------|----------------------|----------------------------------------------------------|
| `redis`         | `redis:7-alpine`     | Cola de jobs (RQ)                                        |
| `quantum-api`   | build local (Dockerfile) | API FastAPI: recibe el código y expone el estado        |
| `quantum-worker`| build local (Dockerfile) | Worker RQ: ejecuta SpinQit contra el NMR, de a un job  |
| `n8n`           | `n8nio/n8n:latest`   | Orquestador: recibe, encola, espera y renderiza HTML     |

## Estructura

```
n8n/
├── Dockerfile             # imagen con SpinQit + FastAPI + RQ
├── docker-compose.yml     # redis + quantum-api + quantum-worker + n8n
├── .env.example           # variables de configuración
├── n8n-workflow.json      # workflow de n8n listo para importar (opcional)
├── app/
│   ├── __init__.py
│   ├── config.py          # configuración desde variables de entorno
│   ├── main.py            # API FastAPI (endpoints)
│   ├── jobs.py            # job RQ: ejecuta el circuito sobre el NMR
│   └── worker.py          # punto de entrada del worker RQ
└── README.md
```

## 1. Requisitos

- Docker y Docker Compose.
- Acceso de red desde el contenedor al equipo NMR (`10.10.94.171:8989`).
  Si usas red bridge y no alcanza el equipo, arranca con `--network host` o
  configura el routing correspondiente.

## 2. Configuración

Copia el ejemplo y ajusta las credenciales del NMR:

```bash
cd workspace/n8n
cp .env.example .env
# edita .env con la IP, puerto, usuario y contraseña reales
```

Las variables principales (todas con valores por defecto razonables):

| Variable        | Default         | Descripción                                   |
|-----------------|-----------------|-----------------------------------------------|
| `NMR_IP`        | `10.10.94.171`  | IP del equipo NMR                             |
| `NMR_PORT`      | `8989`          | Puerto del equipo NMR                         |
| `NMR_USER`      | `SpinQ001`      | Usuario del equipo NMR                        |
| `NMR_PASS`      | `123456`        | Contraseña del equipo NMR                     |
| `NMR_TASK`      | `task2`         | Nombre base de tarea (se agrega `job-{id}`)   |
| `JOB_TIMEOUT`   | `600`           | Tiempo máximo (s) por job                     |

> Las credenciales van **solo** por variables de entorno; nunca se escriben en
> el código del usuario ni se devuelven en las respuestas.

## 3. Levantar el despliegue

```bash
cd workspace/n8n
docker compose up -d --build
```

Esto levanta:

- API en `http://localhost:8000` (documentación interactiva en `/docs`).
- Formulario web en `http://localhost:8000/` (sube un `.py` y ejecuta).
- n8n en `http://localhost:5678`.

Verifica el estado:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### Formulario web

Abre `http://localhost:8000/` en el navegador:

- **Sube** (o arrastra) un archivo `.py` con el circuito.
- Botón **Ejecutar circuito**: encola el job, consulta su estado y muestra la
  tabla de `counts` y `probabilities` como HTML.
- Enlaces **Descargar ejemplo**: descargan `example.py` (API nativa) y
  `example_qiskit.py` (estilo Qiskit) listos para adaptar.

El formulario llama a la API del mismo origen (`/execute` y `/jobs/{id}`), por
lo que no depende de n8n. El webhook de n8n (sección 6) sigue disponible como
ruta alternativa.

## 4. Contrato del código Python que envía el usuario

El usuario define **solo el circuito** (y opcionalmente el compilador y los
shots). El servidor aporta la conexión al NMR.

```python
# Opción A: API nativa de SpinQit
from spinqit import Circuit, H, CX, Rx
from math import pi

circuit = Circuit()
q = circuit.allocateQubits(2)
circuit << (Rx, q[0], pi)
circuit << (H, q[1])
circuit << (CX, (q[0], q[1]))

compiler = "native"   # opcional (default "native")
shots = 1024          # opcional (default 1024)
```

```python
# Opción B: estilo Qiskit (QuantumCircuit)
from spinqit.qiskit.circuit import QuantumCircuit
from math import pi

circuit = QuantumCircuit(2)
circuit.h(0)
circuit.rx(pi, 1)
circuit.cx(0, 1)

compiler = "qiskit"
```

Reglas:

1. El circuito debe quedar en una variable llamada **`circuit`**.
   Si no existe, el servicio busca automáticamente **una única** variable de
   tipo `Circuit` o `QuantumCircuit` en el código.
2. `compiler` puede ser `"native"` o `"qiskit"`. Si no se indica, se deduce del
   tipo de circuito (`QuantumCircuit` ⇒ `qiskit`, si no ⇒ `native`).
3. `shots` es el número de disparos (default `1024`).
4. El nivel de optimización queda fijo en `0`.

## 5. Probar la API (sin n8n)

```bash
# Enviar un circuito (Bell) y obtener el job_id
curl -s -X POST http://localhost:8000/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "code": "from spinqit import Circuit, H, CX, Rx\nfrom math import pi\ncircuit = Circuit()\nq = circuit.allocateQubits(2)\ncircuit << (Rx, q[0], pi)\ncircuit << (H, q[1])\ncircuit << (CX, (q[0], q[1]))\nshots = 1024\n"
  }'

# Consultar el resultado (sustituye JOB_ID)
curl -s http://localhost:8000/jobs/JOB_ID
# {"job_id":"...","status":"finished","result":{"counts":{...},"probabilities":{...}}}
```

Estados posibles de `status`: `queued`, `started`, `finished`, `failed`.

## 6. Configurar el workflow de n8n

### Opción A — Importar el workflow (rápido)

1. Abre `http://localhost:5678` y entra a tu instancia de n8n.
2. Ve a **Workflows → ⋯ → Import from File** y selecciona `n8n-workflow.json`.
3. Activa el workflow (**Active** arriba a la derecha).

> Si la importación falla por diferencias de versión, usa la Opción B.

### Opción B — Crear el workflow a mano

Crea un workflow con estos 4 nodos, conectados en orden:

#### 1) Webhook — "Recibir circuito"

- **HTTP Method**: `POST`
- **Path**: `quantum`
- **Response Mode**: `Last Node`

#### 2) HTTP Request — "Enviar a ejecutar"

- **Method**: `POST`
- **URL**: `http://quantum-api:8000/execute`
- **Send Body**: activado
- **Body Content Type**: `JSON`
- **Body** (modo JSON):

```
={{ JSON.stringify({ code: $json.body.code, resume_url: $execution.resumeUrl }) }}
```

#### 3) Wait — "Esperar resultado"

- **Resume**: `On Webhook Call`

#### 4) Code (JavaScript) — "Generar HTML"

Pega este código:

```javascript
const c = $json.counts || {};
const p = $json.probabilities || {};
const keys = Object.keys(c).length ? Object.keys(c) : Object.keys(p);
const rows = keys
  .map(k => `<tr><td>${k}</td><td>${c[k] ?? '-'}</td><td>${p[k] ?? '-'}</td></tr>`)
  .join('');

const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Resultado NMR</title>
<style>
body{font-family:sans-serif;padding:2rem}
table{border-collapse:collapse}
th,td{border:1px solid #ccc;padding:.5rem 1rem;text-align:center}
th{background:#f0f0f0}
</style></head><body>
<h1>Resultado de ejecución</h1>
<p>job_id: ${$json.job_id ?? '-'}</p>
<table><thead><tr><th>Estado</th><th>Counts</th><th>Probabilidad</th></tr></thead>
<tbody>${rows}</tbody></table>
</body></html>`;

return [{ json: { html, job_id: $json.job_id, counts: c, probabilities: p } }];
```

Activa el workflow.

### Probar el workflow

```bash
curl -s -X POST http://localhost:5678/webhook/quantum \
  -H 'Content-Type: application/json' \
  -d '{"code":"from spinqit import Circuit, H, CX, Rx\nfrom math import pi\ncircuit = Circuit()\nq = circuit.allocateQubits(2)\ncircuit << (Rx, q[0], pi)\ncircuit << (H, q[1])\ncircuit << (CX, (q[0], q[1]))\n"}'
```

El webhook responde con el HTML del resultado una vez que el job termina.

## 7. Usar un n8n ya existente (en lugar del incluido)

Si ya tienes un n8n corriendo:

1. Elimina (o ignora) el servicio `n8n` de `docker-compose.yml`.
2. En tu n8n, crea el workflow de la sección 6 (la URL del servicio Python será
   la IP/host donde expongas `quantum-api`, p. ej. `http://TU_HOST:8000/execute`).
3. Asegúrate de que el contenedor `quantum-api`/`quantum-worker` pueda alcanzar
   tu n8n. Como n8n genera la `resume_url` con `localhost`, el servicio la
   reescribe usando `N8N_INTERNAL_HOST` (por defecto `n8n`). Si tu n8n vive en
   otro host, ajusta esta variable:

```yaml
environment:
  - N8N_INTERNAL_HOST=192.168.1.50   # IP/host de tu n8n accesible desde los contenedores
```

4. También asegúrate de que la `resume_url` que genera n8n use un host que los
   contenedores puedan resolver (configura `N8N_HOST`/`N8N_PROTOCOL`/`N8N_PORT`
   o `WEBHOOK_URL` en tu n8n).

> Si el callback falla, el resultado **no se pierde**: queda disponible vía
> `GET /jobs/{job_id}` (puedes consultarlo desde n8n con un nodo HTTP Request
> y un nodo Wait de tiempo como alternativa al callback).

## 8. Seguridad

- El código del usuario se ejecuta con `exec()` **dentro del contenedor**, que
  es el sandbox. Restringe el tráfico de red de salida del contenedor a solo
  `10.10.94.171:8989` (config de `docker run`/compose, p. ej. con `network_mode`
  o un `external_links` controlado) para minimizar el riesgo.
- Las credenciales y la IP del NMR solo se inyectan por variables de entorno.
- Cada job tiene un timeout (`JOB_TIMEOUT`) que evita ejecuciones colgadas.

## 9. Solución de problemas

- **El worker no procesa**: revisa los logs
  `docker compose logs -f quantum-worker`. Verifica que Redis esté sano y que
  `app.jobs` sea importable (`PYTHONPATH=/app` está en el Dockerfile).
- **`No module named 'spinqit'` / falla la extensión nativa**: la imagen
  `python:3.10` es Linux x86_64; si `pip install spinqit` intenta compilar
  desde fuente, instala `build-essential cmake` (línea comentada en el
  Dockerfile).
- **n8n no recibe el callback**: comprueba `N8N_INTERNAL_HOST` y que n8n genere
  una `resume_url` alcanzable desde los contenedores. Como respaldo, consulta
  `GET /jobs/{job_id}`.
- **El NMR devuelve error**: el backend NMR solo admite circuitos de 0 a 3
  qubits y no soporta puertas condicionales ni `MEASURE` explícito.
