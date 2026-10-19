"""Configuración centralizada leída desde variables de entorno."""

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# --- Conexión al equipo NMR (nunca hardcodear en el código del usuario) ---
NMR_IP = os.getenv("NMR_IP", "10.10.94.171")
NMR_PORT = _int("NMR_PORT", 8989)
NMR_USER = os.getenv("NMR_USER", "SpinQ001")
NMR_PASS = os.getenv("NMR_PASS", "123456")
NMR_TASK = os.getenv("NMR_TASK", "task2")

# --- Redis / RQ ---
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "quantum_jobs")

# --- Jobs ---
JOB_TIMEOUT = _int("JOB_TIMEOUT", 600)   # segundos totales por job
RESULT_TTL = _int("RESULT_TTL", 3600)    # segundos que se conserva el resultado
CALLBACK_TIMEOUT = _int("CALLBACK_TIMEOUT", 15)

# --- Host interno con el que el contenedor Python alcanza a n8n ---
# Se usa para reescribir "localhost"/"127.0.0.1" en la resume-URL de n8n.
N8N_INTERNAL_HOST = os.getenv("N8N_INTERNAL_HOST", "n8n")
