"""Motor de turnos (banco de tiempo): horarios por día, profesionales y horarios libres.

Estructura en los datos del negocio:
  d["agenda"] = {"dias": {"0": [["09:00","13:00"],["16:00","20:00"]], ...},   # 0 = lunes ... 6 = domingo
                 "intervalo": 15,        # cada cuántos minutos puede empezar un turno
                 "anticipacion": 60,     # minutos mínimos desde ahora para reservar
                 "dias_adelante": 30}    # hasta cuántos días adelante se puede reservar
  d["profesionales"] = [{"id": "p1", "nombre": "Juli", "servicios": [0, 2]}]   # servicios vacíos = hace todos
Los turnos son filas de `pedidos` con tipo='turnos', `cuando`='YYYY-MM-DD HH:MM' y `profesional`.
"""
import re
import unicodedata
from datetime import datetime, timedelta

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
ABREV = {"lun": 0, "mar": 1, "mie": 2, "mier": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
DEFECTO = {"dias": {str(i): [["09:00", "18:00"]] for i in range(0, 5)} | {"5": [["09:00", "13:00"]]},
           "intervalo": 15, "anticipacion": 60, "dias_adelante": 30}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _dia(tok: str) -> int | None:
    tok = _norm(tok).rstrip("s.")
    for i, d in enumerate(DIAS):
        if tok == d or tok == d.rstrip("s"):
            return i
    return ABREV.get(tok[:4]) if tok[:4] in ABREV else ABREV.get(tok[:3])


def _hora(t: str) -> str | None:
    m = re.fullmatch(r"(\d{1,2})(?:[:.h](\d{2}))?", t.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h == 24:
        h, mi = 23, 59
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def parse_horarios(texto: str) -> dict | None:
    """'Martes a sábado de 10 a 20', 'lun a vie 9 a 13 y 16 a 20, sábados 9 a 13', 'lun-sab 19:00-23:30'."""
    if not texto:
        return None
    t = _norm(texto).replace("hs", "").replace("hrs", "")
    dias: dict[str, list] = {}
    partes = []
    for bloque in re.split(r"[;,\n]", t):
        # "lun a vie 9 a 13 y sábados 9 a 13" -> se corta en " y <día>" solo si lo anterior ya tiene horario
        ini = 0
        for m in re.finditer(r"\s+y\s+(?=(?:lun|mar|mie|jue|vie|sab|dom))", bloque):
            if re.search(r"\d", bloque[ini:m.start()]):
                partes.append(bloque[ini:m.start()])
                ini = m.end()
        partes.append(bloque[ini:])
    for parte in partes:
        # días: rango "lunes a viernes" / "lun-vie" o lista "martes y jueves"
        rango = re.search(r"(lun\w*|mar\w*|mie\w*|jue\w*|vie\w*|sab\w*|dom\w*)\s*(?:a|-|al|hasta)\s*(lun\w*|mar\w*|mie\w*|jue\w*|vie\w*|sab\w*|dom\w*)", parte)
        sel = []
        if rango and _dia(rango.group(1)) is not None and _dia(rango.group(2)) is not None:
            a, b = _dia(rango.group(1)), _dia(rango.group(2))
            sel = list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
        else:
            sel = [x for x in (_dia(w) for w in re.findall(r"(lun\w*|mar\w*|mie\w*|jue\w*|vie\w*|sab\w*|dom\w*)", parte)) if x is not None]
        if "todos los dias" in parte or "lunes a lunes" in parte:
            sel = list(range(7))
        franjas = []
        for h1, h2 in re.findall(r"(\d{1,2}(?:[:.h]\d{2})?)\s*(?:a|-|al|hasta)\s*(\d{1,2}(?:[:.h]\d{2})?)", parte):
            a, b = _hora(h1), _hora(h2)
            if a and b and a < b:
                franjas.append([a, b])
        if sel and franjas:
            for x in sel:
                dias[str(x)] = franjas
    return {**DEFECTO, "dias": dias} if dias else None


def config(d: dict) -> dict:
    ag = d.get("agenda") or parse_horarios(d.get("horarios", "")) or DEFECTO
    return {**DEFECTO, **ag}


def profesionales(d: dict) -> list[dict]:
    return d.get("profesionales") or []


def hace(p: dict, servicio: int) -> bool:
    return not p.get("servicios") or servicio in p["servicios"]


def _min(h: str) -> int:
    return int(h[:2]) * 60 + int(h[3:5])


def libres(d: dict, ocupados: list[tuple[str, int, str]], servicio: int, fecha: str, prof: str | None = None,
           ahora: datetime | None = None) -> list[dict]:
    """Horarios libres de un día. `ocupados`: [(cuando, duracion_min, profesional)] de turnos no cancelados.
    Devuelve [{"hora": "HH:MM", "profesionales": [ids libres]}]."""
    cfg = config(d)
    try:
        dia = datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        return []
    ahora = ahora or datetime.now()
    if dia.date() < ahora.date() or dia.date() > (ahora + timedelta(days=int(cfg["dias_adelante"]))).date():
        return []
    franjas = cfg["dias"].get(str(dia.weekday())) or []
    dur = int(d["items"][servicio].get("duracion_min") or 30) if 0 <= servicio < len(d["items"]) else 30
    paso = max(5, int(cfg.get("intervalo") or 15))
    pros = [p for p in profesionales(d) if hace(p, servicio)]
    ids = [p["id"] for p in pros] if pros else ["_"]
    if prof and prof in ids:
        ids = [prof]
    # ocupación por profesional ese día
    occ = {i: [] for i in ids}
    for cuando, dmin, pr in ocupados:
        if not cuando or not cuando.startswith(fecha):
            continue
        ini = _min(cuando[11:16])
        for i in ids:
            if pr in (i, "_", None, "") or i == "_":
                occ[i].append((ini, ini + int(dmin or 30)))
    limite = ahora + timedelta(minutes=int(cfg.get("anticipacion") or 0))
    out = []
    for a, b in franjas:
        t = _min(a)
        while t + dur <= _min(b):
            inicio = dia.replace(hour=t // 60, minute=t % 60)
            if inicio >= limite:
                disp = [i for i in ids if all(not (t < f and s < t + dur) for s, f in occ[i])]
                if disp:
                    out.append({"hora": f"{t // 60:02d}:{t % 60:02d}", "profesionales": disp})
            t += paso
    return out


def proximos_dias(d: dict, ocupados, servicio: int, prof: str | None = None, n: int = 14) -> list[dict]:
    hoy = datetime.now()
    res = []
    for k in range(n):
        f = (hoy + timedelta(days=k)).strftime("%Y-%m-%d")
        res.append({"fecha": f, "libres": len(libres(d, ocupados, servicio, f, prof))})
    return res


def primeros_libres(d: dict, ocupados, servicio: int, cantidad: int = 6, prof: str | None = None) -> list[str]:
    """Los próximos horarios libres ('YYYY-MM-DD HH:MM'), para sugerir en el chat."""
    out = []
    hoy = datetime.now()
    for k in range(int(config(d)["dias_adelante"])):
        f = (hoy + timedelta(days=k)).strftime("%Y-%m-%d")
        for s in libres(d, ocupados, servicio, f, prof):
            out.append(f"{f} {s['hora']}")
            if len(out) >= cantidad:
                return out
    return out


def legible(cuando: str) -> str:
    try:
        dt = datetime.strptime(cuando, "%Y-%m-%d %H:%M")
    except ValueError:
        return cuando
    hoy = datetime.now().date()
    dia = "hoy" if dt.date() == hoy else "mañana" if dt.date() == hoy + timedelta(days=1) else \
        f"{DIAS[dt.weekday()].replace('miercoles', 'miércoles').replace('sabado', 'sábado')} {dt.day}/{dt.month}"
    return f"{dia} {dt:%H:%M}"
