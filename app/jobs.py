"""Job de RQ: compila y ejecuta un circuito definido por el usuario sobre el NMR.

Contrato del código de usuario
------------------------------
El usuario solo define el circuito (y, opcionalmente, el compilador y los
shots). Las credenciales y la IP del equipo las aporta el servidor.

    circuit = ...        # Circuit (nativa) o QuantumCircuit (qiskit)
    compiler = "native"  # opcional, default: "native" / "qiskit"
    shots = 1024         # opcional, default: 1024

Si no existe una variable llamada "circuit", se busca automáticamente una
única variable de tipo Circuit/QuantumCircuit en el código.
"""

import base64
import os
import requests
from urllib.parse import urlparse

from . import config

try:
    from spinqit import Circuit, get_compiler, get_nmr, NMRConfig
except Exception:  # pragma: no cover
    Circuit = None

try:
    from spinqit import view
except Exception:  # pragma: no cover
    try:
        import spinqit.view as view
    except Exception:  # pragma: no cover
        view = None

try:
    from spinqit.qiskit.circuit import QuantumCircuit
except Exception:  # pragma: no cover
    QuantumCircuit = None


def _is_circuit(obj) -> bool:
    if Circuit is not None and isinstance(obj, Circuit):
        return True
    if QuantumCircuit is not None and isinstance(obj, QuantumCircuit):
        return True
    return False


def _is_qiskit_circuit(obj) -> bool:
    return QuantumCircuit is not None and isinstance(obj, QuantumCircuit)


def extract_circuit(code: str):
    """Ejecuta el código del usuario y devuelve (circuit, compiler, shots)."""
    namespace = {"__name__": "user_circuit"}
    exec(compile(code, "<user-circuit>", "exec"), namespace)

    circuit = namespace.get("circuit")
    if circuit is None:
        candidates = [
            (name, obj)
            for name, obj in namespace.items()
            if not name.startswith("__") and _is_circuit(obj)
        ]
        if not candidates:
            raise ValueError(
                "No se encontró ningún circuito. Asigna el circuito a una "
                "variable llamada 'circuit' (o deja una única variable de tipo "
                "Circuit/QuantumCircuit en el código)."
            )
        if len(candidates) > 1:
            names = ", ".join(name for name, _ in candidates)
            raise ValueError(
                f"Se encontraron varios circuitos ({names}). Asigna el "
                "circuito a una única variable llamada 'circuit'."
            )
        circuit = candidates[0][1]

    compiler = namespace.get("compiler")
    if compiler is None:
        compiler = "qiskit" if _is_qiskit_circuit(circuit) else "native"

    shots = int(namespace.get("shots", 1024))

    return circuit, compiler, shots


def _to_jsonable(obj):
    """Convierte el resultado (dicts/numpy scalars) a tipos serializables."""
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    return str(obj)


def _rewrite_resume_url(url):
    """Reescribe localhost/127.0.0.1 por el host interno de n8n."""
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        netloc = parsed.netloc.replace(parsed.hostname, config.N8N_INTERNAL_HOST)
        return parsed._replace(netloc=netloc).geturl()
    return url


def execute_circuit(code: str, job_id: str, resume_url: str = None):
    """Compila y ejecuta el circuito sobre el NMR y notifica a n8n."""
    circuit, compiler, shots = extract_circuit(code)

    exe = get_compiler(compiler).compile(circuit, 0)

    circuit_image = None
    if view is not None and hasattr(view, "draw"):
        img_path = f"/tmp/circuit_{job_id}.png"
        try:
            view.draw(exe, img_path)
            if os.path.exists(img_path):
                with open(img_path, "rb") as f:
                    img_bytes = f.read()
                if img_bytes:
                    circuit_image = f"data:image/png;base64,{base64.b64encode(img_bytes).decode('utf-8')}"
                try:
                    import shutil
                    shutil.copyfile(img_path, "./circuit.png")
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except Exception:
                    pass
            try:
                import matplotlib.pyplot as plt
                plt.close("all")
            except Exception:
                pass

    engine = get_nmr()
    nmr_config = NMRConfig()
    nmr_config.configure_shots(shots)
    nmr_config.configure_ip(config.NMR_IP)
    nmr_config.configure_port(config.NMR_PORT)
    nmr_config.configure_account(config.NMR_USER, config.NMR_PASS)
    nmr_config.configure_task(config.NMR_TASK, f"job-{job_id}")

    result = engine.execute(exe, nmr_config)

    payload = {
        "job_id": job_id,
        "compiler": compiler,
        "shots": shots,
        "counts": _to_jsonable(getattr(result, "counts", None)),
        "probabilities": _to_jsonable(getattr(result, "probabilities", None)),
        "circuit_image": circuit_image,
    }

    if resume_url:
        target = _rewrite_resume_url(resume_url)
        try:
            requests.post(target, json=payload, timeout=config.CALLBACK_TIMEOUT)
        except Exception:
            # El resultado sigue disponible vía GET /jobs/{job_id}.
            pass

    return payload
