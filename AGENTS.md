# AGENTS.md

Servicio que ejecuta circuitos SpinQit sobre un equipo NMR físico remoto.
Flujo: usuario envía código Python → FastAPI (`app/main.py`) lo encola en
Redis/RQ → worker lo ejecuta contra el NMR → resultado vía `GET /jobs/{id}`.
El NMR es un recurso **único**: las ejecuciones van de a una.

## Comandos

- Levantar / reconstruir todo: `docker compose up -d --build` **desde la raíz
  del repo**.
- Logs del worker: `docker compose logs -f quantum-worker`.
- Salud: `curl http://localhost:8000/health`. API en `:8000`
- Prueba end-to-end (única forma de verificar el flujo real):
  `POST /execute` con `{"code": "..."}` → `GET /jobs/{job_id}` hasta
  `status` = `finished` | `failed`.
- No hay tests, lint, CI, `requirements.txt` ni `pyproject.toml`. No inventes
  `pytest`/`pip install -r`; el build es solo Docker y es pesado (clona el repo
  de SpinQit y `pip install spinqit`).

## Arquitectura

- Imagen única; `quantum-api` y `quantum-worker` usan el mismo `Dockerfile`.
  El worker solo cambia el comando: `python -m app.worker`.
- El `Dockerfile` fija `PYTHONPATH=/app`; todos los imports son `app.*`
  (`app.main:app`, `app.worker`, `app.jobs`).
- `app/config.py` es la fuente de defaults de las variables de entorno;
  `docker-compose.yml` las repite con `${VAR:-default}`. Al añadir una variable,
  actualiza ambos.
- Cola RQ: `QUEUE_NAME` (default `quantum_jobs`).
- Añadir una dependencia = editar el `Dockerfile` (no hay manifest de Python).

## Gotchas (fáciles de romper)

- **No escales el worker**: un solo proceso y concurrencia 1. No agregues
  réplicas ni `-c`/`--worker-class`; el NMR no admite paralelismo.
- El código del usuario se ejecuta con `exec()` dentro del contenedor. El
  contenedor es el único sandbox; no hay aislamiento adicional.
- Los imports de `spinqit` están envueltos en `try/except` para que `app.main`
  sea importable sin la librería; `app.jobs.execute_circuit` sí la necesita en
  runtime.
- Límites del NMR: solo 0–3 qubits, sin puertas condicionales ni `MEASURE`
  explícito.
- RQ 2.x devuelve un enum `JobStatus`; mantén la normalización
  `getattr(status, "value", status)` en `app/main.py`.
- Contrato del código del usuario (ver `app/static/example*.py`): debe existir
  la variable `circuit` (o una única variable `Circuit`/`QuantumCircuit`);
  opcionales `compiler` (`"native"`/`"qiskit"`, se deduce del tipo) y `shots`
  (default 1024). Optimización fija en 0.

