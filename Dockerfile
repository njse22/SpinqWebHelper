# Entorno SpinQit (base proporcionada por el usuario)
FROM python:3.10

RUN apt update
RUN apt install git -y
RUN git clone https://github.com/SpinQTech/SpinQit.git

WORKDIR /SpinQit

RUN pip install -r requirements.txt
RUN pip install qiskit==2.5.2
RUN pip install spinqit

# ---------------------------------------------------------------------------
# Servicio web (FastAPI) + cola (Redis/RQ)
# ---------------------------------------------------------------------------
# Nota: si "pip install spinqit" intentara compilar la extensión nativa desde
# el código fuente, descomenta la siguiente línea para instalar las
# herramientas de compilación:
#   RUN apt install -y build-essential cmake
RUN pip install fastapi uvicorn redis "rq>=2.0,<3.0"

WORKDIR /app
ENV PYTHONPATH=/app

COPY app /app/app

EXPOSE 8000

# Por defecto arranca la API; el worker usa el mismo build con otro comando.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

