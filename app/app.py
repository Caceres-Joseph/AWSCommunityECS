import os
import json
import socket
import time
import threading
import multiprocessing
from urllib.request import urlopen

from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Estado de la carga de CPU (por contenedor / tarea ECS) ---
_procs = []          # procesos que están quemando CPU
_deadline = 0.0      # timestamp en el que la carga se apaga sola
_gen = 0             # generación: invalida timers viejos
_lock = threading.Lock()

TASK_ID = socket.gethostname()

# --- Lectura de CPU/RAM del contenedor vía cgroups (v2 y v1) ---
_cpu_sample = {"t": None, "usage": None}
_cpu_sample_lock = threading.Lock()


def _read_int(path):
    with open(path) as f:
        return int(f.read().strip())


_quota_cache = None


def _task_vcpu_from_metadata():
    """vCPUs reservadas al task, leídas del endpoint de metadata de ECS.

    Es el MISMO denominador que usa la métrica CPUUtilization de CloudWatch,
    así el % de la app coincide con el de AWS. Devuelve None fuera de ECS.
    """
    uri = (os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
           or os.environ.get("ECS_CONTAINER_METADATA_URI"))
    if not uri:
        return None
    try:
        with urlopen(uri + "/task", timeout=1) as r:
            data = json.load(r)
    except Exception:
        return None
    cpu = (data.get("Limits") or {}).get("CPU")
    return float(cpu) if cpu else None


def _cpu_quota():
    """vCPUs asignadas al task (denominador del % de CPU). Se cachea 1 vez.

    Prioridad: metadata de ECS (== CloudWatch) → cgroup v2 → cgroup v1 →
    núcleos del host (impreciso en Fargate, era la causa del bug de 50% vs 100%).
    """
    global _quota_cache
    if _quota_cache is not None:
        return _quota_cache

    q = _task_vcpu_from_metadata()
    if q is None:
        try:  # cgroup v2
            with open("/sys/fs/cgroup/cpu.max") as f:
                parts = f.read().split()
            if parts[0] != "max":
                q = int(parts[0]) / int(parts[1])
        except (FileNotFoundError, ValueError, IndexError):
            pass
    if q is None:
        try:  # cgroup v1
            quota = _read_int("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
            period = _read_int("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
            if quota > 0 and period > 0:
                q = quota / period
        except (FileNotFoundError, ValueError):
            pass
    if q is None:
        q = float(os.cpu_count() or 1)

    _quota_cache = q
    return q


def _cpu_usage_usec():
    """Uso acumulado de CPU del contenedor en microsegundos."""
    try:  # cgroup v2
        with open("/sys/fs/cgroup/cpu.stat") as f:
            for line in f:
                if line.startswith("usage_usec"):
                    return int(line.split()[1])
    except FileNotFoundError:
        pass
    for path in ("/sys/fs/cgroup/cpuacct/cpuacct.usage",
                 "/sys/fs/cgroup/cpu,cpuacct/cpuacct.usage"):
        try:  # cgroup v1 (nanosegundos)
            return _read_int(path) // 1000
        except (FileNotFoundError, ValueError):
            continue
    return None


def _cpu_percent():
    """% de CPU relativo a la vCPU asignada (igual criterio que CloudWatch)."""
    usage = _cpu_usage_usec()
    if usage is None:
        return None
    now = time.monotonic()
    with _cpu_sample_lock:
        last_t, last_u = _cpu_sample["t"], _cpu_sample["usage"]
        _cpu_sample["t"], _cpu_sample["usage"] = now, usage
    if last_t is None:  # primer muestreo: ventana corta
        time.sleep(0.1)
        usage2 = _cpu_usage_usec()
        now2 = time.monotonic()
        with _cpu_sample_lock:
            _cpu_sample["t"], _cpu_sample["usage"] = now2, usage2
        delta_u, delta_t = usage2 - usage, (now2 - now) * 1e6
    else:
        delta_u, delta_t = usage - last_u, (now - last_t) * 1e6
    if delta_t <= 0:
        return None
    pct = (delta_u / delta_t) / _cpu_quota() * 100.0
    return round(max(0.0, min(pct, 100.0)), 1)


def _mem():
    """(usado_MB, limite_MB, porcentaje) del contenedor."""
    used = limit = None
    try:  # cgroup v2
        used = _read_int("/sys/fs/cgroup/memory.current")
        with open("/sys/fs/cgroup/memory.max") as f:
            raw = f.read().strip()
        limit = None if raw == "max" else int(raw)
    except (FileNotFoundError, ValueError):
        try:  # cgroup v1
            used = _read_int("/sys/fs/cgroup/memory/memory.usage_in_bytes")
            limit = _read_int("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            if limit > (1 << 62):
                limit = None
        except (FileNotFoundError, ValueError):
            return None, None, None
    used_mb = round(used / 1048576, 1) if used is not None else None
    limit_mb = round(limit / 1048576, 1) if limit else None
    pct = round(used / limit * 100, 1) if (used and limit) else None
    return used_mb, limit_mb, pct


def _burn(load):
    """Duty-cycle: ocupa `load` (0-1) de un núcleo y descansa el resto.

    Dejar headroom (~20%) evita que el health check del ALB se caiga
    mientras la tarea está bajo carga.
    """
    os.nice(10)  # baja prioridad: primero responde el health check
    period = 0.1
    busy = period * max(0.0, min(1.0, load))
    idle = period - busy
    while True:
        start = time.perf_counter()
        while time.perf_counter() - start < busy:
            pass  # bucle ocupado
        if idle > 0:
            time.sleep(idle)


def _stop():
    """Detiene toda la carga en esta tarea e invalida timers pendientes."""
    global _procs, _deadline, _gen
    with _lock:
        _gen += 1
        for p in _procs:
            if p.is_alive():
                p.terminate()
        _procs = []
        _deadline = 0.0


def _start(workers, seconds, load):
    """Arranca `workers` procesos quemando CPU durante `seconds`."""
    global _procs, _deadline, _gen
    _stop()  # limpia cualquier carga previa
    with _lock:
        gen = _gen
        _procs = [
            multiprocessing.Process(target=_burn, args=(load,), daemon=True)
            for _ in range(workers)
        ]
        for p in _procs:
            p.start()
        _deadline = time.time() + seconds

    # Apagado automático: solo actúa si nadie reinició la carga entretanto.
    def _expire():
        if _gen == gen:
            _stop()

    t = threading.Timer(seconds, _expire)
    t.daemon = True
    t.start()


def _state():
    mem_used, mem_limit, mem_pct = _mem()
    return {
        "task": TASK_ID,
        "burning": len(_procs) > 0,
        "workers": len(_procs),
        "seconds_left": max(0, int(_deadline - time.time())),
        "cpu_percent": _cpu_percent(),
        "mem_used_mb": mem_used,
        "mem_limit_mb": mem_limit,
        "mem_percent": mem_pct,
    }


@app.get("/")
def home():
    s = _state()
    estado = "🔥 quemando CPU" if s["burning"] else "😴 en reposo"
    cpu = f"{s['cpu_percent']}%" if s["cpu_percent"] is not None else "n/d"
    ram = (f"{s['mem_used_mb']} / {s['mem_limit_mb']} MB ({s['mem_percent']}%)"
           if s["mem_percent"] is not None else "n/d")
    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Demo Escalado ECS</title>
<meta http-equiv="refresh" content="3"></head>
<body style="font-family:sans-serif;text-align:center;margin-top:6%">
  <h1>Hola Universidad 👋</h1>
  <p>Respondió la tarea: <b>{s['task']}</b></p>
  <p>Estado: <b>{estado}</b></p>
  <p>CPU: <b>{cpu}</b></p>
  <p>RAM: <b>{ram}</b></p>
</body></html>"""
    return html, 200


@app.get("/health")
def health():
    return jsonify(status="ok", **_state())


@app.get("/status")
def status():
    return jsonify(_state())


@app.post("/burn")
def burn():
    """Sube la CPU de la tarea que reciba este request.

    Body JSON (opcional): {"seconds": 120, "workers": 1, "load": 0.85}
    """
    data = request.get_json(silent=True) or {}
    seconds = int(data.get("seconds", 120))
    workers = int(data.get("workers", 1))
    load = float(data.get("load", 0.85))
    _start(workers, seconds, load)
    return jsonify(message="Subiendo CPU", **_state())


@app.post("/stop")
def stop():
    """Baja la CPU de la tarea que reciba este request."""
    _stop()
    return jsonify(message="Carga detenida", **_state())


if __name__ == "__main__":
    # threaded=True: el health check sigue respondiendo mientras hay carga.
    app.run(host="0.0.0.0", port=80, threaded=True)
