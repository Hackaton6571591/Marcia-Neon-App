"""Marcia Neon App: punto de entrada FastAPI."""
import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import launcher, mercadopago
from .blueprints import ALIAS_CHIPS, BLUEPRINTS

BASE = Path(__file__).parent
DATA = BASE.parent / "data"
DB_PATH = DATA / "marcia.db"


def _cargar_env():
    f = BASE.parent / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_cargar_env()
app = FastAPI(title="Marcia Neon App", docs_url=None, redoc_url=None, openapi_url=None)
tpl = Jinja2Templates(directory=BASE / "templates")


# ---------- base de datos ----------

def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.row_factory = sqlite3.Row
    return c


@app.on_event("startup")
def init_db():
    DATA.mkdir(exist_ok=True)
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sesiones(id TEXT PRIMARY KEY, datos TEXT NOT NULL, historia TEXT NOT NULL,
            mensajes INT DEFAULT 0, creado INT);
        CREATE TABLE IF NOT EXISTS negocios(id INTEGER PRIMARY KEY, slug TEXT UNIQUE, datos TEXT NOT NULL,
            token_admin TEXT NOT NULL, creado INT);
        CREATE TABLE IF NOT EXISTS pedidos(id INTEGER PRIMARY KEY, negocio_id INT NOT NULL, tipo TEXT,
            cliente TEXT, contacto TEXT, detalle TEXT NOT NULL, total INT, cuando TEXT, nota TEXT,
            estado TEXT DEFAULT 'nuevo', creado INT);
        CREATE INDEX IF NOT EXISTS ix_pedidos_negocio ON pedidos(negocio_id, creado);
        """)
        cols = [r[1] for r in c.execute("PRAGMA table_info(pedidos)")]
        if "pago" not in cols:
            c.execute("ALTER TABLE pedidos ADD COLUMN pago TEXT")


# ---------- rate limit simple en memoria ----------

_hits: dict[str, deque] = defaultdict(deque)


def limitar(req: Request, por_min: int = 20, bucket: str = "chat"):
    # Caddy agrega la IP real al final de X-Forwarded-For: tomamos la última (no se puede falsear)
    ip = req.headers.get("x-forwarded-for", req.client.host if req.client else "?").split(",")[-1].strip()
    q, ahora = _hits[f"{ip}:{bucket}"], time.time()
    while q and q[0] < ahora - 60:
        q.popleft()
    if len(q) >= por_min:
        raise HTTPException(429, "Muchos mensajes seguidos, esperá un minuto 🙏")
    q.append(ahora)


# ---------- páginas ----------

@app.get("/salud")
def salud():
    ia = "deepseek" if os.getenv("DEEPSEEK_API_KEY") and os.getenv("IA_PROVIDER") != "simulado" else "simulado"
    return {"ok": True, "ia": ia, "mercadopago": "checkout" if mercadopago.activo() else "manual"}


@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/crear", response_class=HTMLResponse)
def crear(request: Request, rubro: str = Query("", max_length=40), msg: str = Query("", max_length=200)):
    inicial = msg
    if not inicial and rubro in ALIAS_CHIPS:
        inicial = {"restaurante": "Tengo un restaurante", "peluqueria": "Tengo una peluquería",
                   "consultorio": "Tengo un consultorio", "ferreteria": "Tengo una ferretería"}.get(rubro, "")
    return tpl.TemplateResponse(request, "crear.html", {"inicial": inicial})


# ---------- API launcher ----------

class Mensaje(BaseModel):
    sesion: str | None = Field(None, max_length=40)
    texto: str = Field(..., min_length=1, max_length=1000)


def _cargar_sesion(c, sid):
    row = c.execute("SELECT * FROM sesiones WHERE id=?", (sid,)).fetchone() if sid else None
    if not row:
        sid = uuid.uuid4().hex
        c.execute("INSERT INTO sesiones(id,datos,historia,creado) VALUES(?,?,?,?)", (sid, "{}", "[]", int(time.time())))
        return sid, {}, [], 0
    return sid, json.loads(row["datos"]), json.loads(row["historia"]), row["mensajes"]


def _estado(sid, d, proveedor=None, respuesta=None):
    bp = BLUEPRINTS.get(d.get("blueprint") or "")
    return {"sesion": sid, "etapa": launcher.etapa_actual(d), "progreso": launcher.progreso(d), "datos": d,
            "modo": bp["modo"] if bp else None, "rubro": bp["nombre"] if bp else None,
            "emoji": bp["emoji"] if bp else "✨", "respuesta": respuesta, "ia": proveedor}


@app.post("/api/launcher/mensaje")
async def mensaje(m: Mensaje, request: Request):
    limitar(request)
    with db() as c:
        sid, d, hist, n = _cargar_sesion(c, m.sesion)
    if n >= 40:
        raise HTTPException(429, "Llegaste al límite de mensajes de esta sesión.")
    d, respuesta, proveedor = await launcher.procesar(d, m.texto.strip(), hist)
    hist = (hist + [{"role": "user", "content": m.texto[:1000]}, {"role": "assistant", "content": respuesta}])[-12:]
    with db() as c:
        c.execute("UPDATE sesiones SET datos=?, historia=?, mensajes=mensajes+1 WHERE id=?",
                  (json.dumps(d, ensure_ascii=False), json.dumps(hist, ensure_ascii=False), sid))
    return _estado(sid, d, proveedor, respuesta)


@app.get("/api/launcher/sesion/{sid}")
def ver_sesion(sid: str):
    with db() as c:
        row = c.execute("SELECT datos, historia FROM sesiones WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(404)
    e = _estado(sid, json.loads(row["datos"]))
    e["historia"] = json.loads(row["historia"])
    return e


def _slug(nombre: str) -> str:
    s = unicodedata.normalize("NFD", nombre.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "negocio"


@app.post("/api/launcher/sesion/{sid}/publicar")
def publicar(sid: str, request: Request):
    limitar(request, 10, "publicar")
    with db() as c:
        row = c.execute("SELECT datos FROM sesiones WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404)
        d = json.loads(row["datos"])
        if launcher.etapa_actual(d) != "revision":
            raise HTTPException(400, "Todavía faltan datos para publicar.")
        base = slug = _slug(d["nombre"])
        i = 2
        while c.execute("SELECT 1 FROM negocios WHERE slug=?", (slug,)).fetchone():
            slug, i = f"{base}-{i}", i + 1
        token = secrets.token_urlsafe(16)
        c.execute("INSERT INTO negocios(slug,datos,token_admin,creado) VALUES(?,?,?,?)",
                  (slug, json.dumps(d, ensure_ascii=False), token, int(time.time())))
    return {"slug": slug, "url": f"/n/{slug}", "url_panel": f"/panel/{slug}?t={token}"}


# ---------- solución publicada ----------

def _negocio(slug):
    with db() as c:
        row = c.execute("SELECT * FROM negocios WHERE slug=?", (slug,)).fetchone()
    if not row:
        raise HTTPException(404, "Negocio no encontrado")
    d = json.loads(row["datos"])
    return row, d, BLUEPRINTS[d["blueprint"]]


@app.get("/n/{slug}", response_class=HTMLResponse)
def ver_negocio(request: Request, slug: str):
    row, d, bp = _negocio(slug)
    return tpl.TemplateResponse(request, "negocio.html", {"slug": slug, "d": d, "bp": bp, "pagos": _pagos(d)})


@app.get("/n/{slug}/manifest.webmanifest")
def manifest_negocio(slug: str):
    """Cada tienda se instala como app propia del negocio (Agregar a inicio)."""
    from fastapi.responses import JSONResponse
    row, d, bp = _negocio(slug)
    return JSONResponse({"name": d["nombre"], "short_name": d["nombre"][:12], "start_url": f"/n/{slug}",
                         "scope": f"/n/{slug}", "display": "standalone", "background_color": "#07060f",
                         "theme_color": "#07060f", "lang": "es",
                         "icons": [{"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}]},
                        media_type="application/manifest+json")


class Pedido(BaseModel):
    cliente: str = Field(..., min_length=1, max_length=60)
    contacto: str = Field("", max_length=40)
    items: dict[int, int] = Field(default_factory=dict)  # índice -> cantidad
    cuando: str = Field("", max_length=40)
    nota: str = Field("", max_length=300)
    pago: str = Field("efectivo", max_length=20)


@app.post("/api/n/{slug}/pedido")
async def crear_pedido(slug: str, p: Pedido, request: Request):
    limitar(request, 10, "pedido")
    row, d, bp = _negocio(slug)
    detalle, total = [], 0
    for idx, cant in p.items.items():
        if 0 <= idx < len(d["items"]) and 0 < cant <= 50:
            it = d["items"][idx]
            detalle.append({"nombre": it["nombre"], "cantidad": cant, "precio": it["precio"]})
            total += it["precio"] * cant
    if not detalle:
        raise HTTPException(400, "Elegí al menos un producto o servicio.")
    if bp["modo"] == "turnos" and not p.cuando:
        raise HTTPException(400, "Elegí día y horario para el turno.")
    if bp["modo"] == "turnos":
        _validar_turno(row["id"], d, detalle, p.cuando)
    pagos = _pagos(d)
    if p.pago not in pagos:
        raise HTTPException(400, "Medio de pago no disponible.")
    with db() as c:
        cur = c.execute("INSERT INTO pedidos(negocio_id,tipo,cliente,contacto,detalle,total,cuando,nota,pago,creado) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (row["id"], bp["modo"], p.cliente, p.contacto, json.dumps(detalle, ensure_ascii=False),
                         total, p.cuando, p.nota, p.pago, int(time.time())))
    numero = cur.lastrowid
    pago_url = None
    if p.pago == "mercadopago" and mercadopago.activo():
        base = os.getenv("BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/").replace("http://", "https://")
        pago_url = await mercadopago.crear_preferencia(numero, d["nombre"], detalle, base, slug)
    return {"numero": numero, "total": total, "detalle": detalle, "pago": p.pago,
            "pago_info": pagos[p.pago], "pago_url": pago_url}


@app.post("/api/mp/webhook")
async def mp_webhook(request: Request):
    """Notificación de Mercado Pago. Re-consulta el pago a la API antes de marcar nada."""
    q = dict(request.query_params)
    try:
        body = await request.json()
    except Exception:
        body = {}
    tipo = q.get("type") or q.get("topic") or body.get("type") or body.get("topic")
    pid = str(q.get("data.id") or q.get("id") or (body.get("data") or {}).get("id") or "")
    if tipo == "payment" and pid:
        status, ref = await mercadopago.consultar_pago(pid)
        if status == "approved" and ref and ref.isdigit():
            with db() as c:
                c.execute("UPDATE pedidos SET estado='pagado' WHERE id=? AND pago='mercadopago'", (int(ref),))
    return {"ok": True}


def _duracion(d: dict, detalle: list[dict]) -> int:
    dur = {it["nombre"]: it.get("duracion_min", 30) for it in d["items"]}
    return sum(dur.get(x["nombre"], 30) * x["cantidad"] for x in detalle)


def _validar_turno(negocio_id: int, d: dict, detalle: list[dict], cuando: str):
    """Banco de tiempo: rechaza turnos en el pasado o superpuestos con otro turno del negocio."""
    from datetime import datetime, timedelta
    try:
        ini = datetime.strptime(cuando.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(400, "Fecha u hora inválida.")
    if ini < datetime.now() - timedelta(minutes=5):
        raise HTTPException(400, "Ese horario ya pasó.")
    fin = ini + timedelta(minutes=_duracion(d, detalle))
    with db() as c:
        for r in c.execute("SELECT cuando, detalle FROM pedidos WHERE negocio_id=? AND tipo='turnos' AND cuando LIKE ?",
                           (negocio_id, ini.strftime("%Y-%m-%d") + "%")):
            try:
                oi = datetime.strptime(r["cuando"], "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            of = oi + timedelta(minutes=_duracion(d, json.loads(r["detalle"])))
            if ini < of and oi < fin:
                raise HTTPException(409, f"Ese horario ya está reservado ({oi:%H:%M}–{of:%H:%M}). Elegí otro.")


@app.get("/api/n/{slug}/ocupados")
def ocupados(slug: str, dia: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")):
    """Franjas ocupadas de un día (sin datos personales), para mostrarlas en la tienda."""
    from datetime import datetime, timedelta
    row, d, bp = _negocio(slug)
    out = []
    with db() as c:
        for r in c.execute("SELECT cuando, detalle FROM pedidos WHERE negocio_id=? AND tipo='turnos' AND cuando LIKE ?",
                           (row["id"], dia + "%")):
            try:
                oi = datetime.strptime(r["cuando"], "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            out.append({"desde": f"{oi:%H:%M}", "hasta": f"{oi + timedelta(minutes=_duracion(d, json.loads(r['detalle']))):%H:%M}"})
    return sorted(out, key=lambda x: x["desde"])


@app.get("/agenda/{slug}.ics")
def agenda_ics(slug: str, t: str = ""):
    """Feed iCalendar privado: se suscribe desde Google Calendar / Apple / Outlook."""
    from datetime import datetime, timedelta
    from fastapi.responses import Response
    row, d, bp = _negocio(slug)
    if not secrets.compare_digest(t, row["token_admin"]):
        raise HTTPException(403)
    esc = lambda x: str(x or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Marcia Neon//Turnos//ES", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:Turnos {esc(d['nombre'])}", "X-WR-TIMEZONE:America/Argentina/Buenos_Aires"]
    with db() as c:
        rows = c.execute("SELECT * FROM pedidos WHERE negocio_id=? AND tipo='turnos' ORDER BY id DESC LIMIT 500",
                         (row["id"],)).fetchall()
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for r in rows:
        try:
            ini = datetime.strptime(r["cuando"], "%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            continue
        det = json.loads(r["detalle"])
        fin = ini + timedelta(minutes=_duracion(d, det))
        serv = ", ".join(x["nombre"] for x in det)
        lines += ["BEGIN:VEVENT", f"UID:turno-{r['id']}@marcia-neon", f"DTSTAMP:{stamp}",
                  f"DTSTART;TZID=America/Argentina/Buenos_Aires:{ini:%Y%m%dT%H%M%S}",
                  f"DTEND;TZID=America/Argentina/Buenos_Aires:{fin:%Y%m%dT%H%M%S}",
                  f"SUMMARY:{esc(serv + ' · ' + r['cliente'])}",
                  f"DESCRIPTION:{esc('Contacto: ' + (r['contacto'] or '-') + chr(10) + 'Nota: ' + (r['nota'] or '-'))}",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar; charset=utf-8")


def _pagos(d: dict) -> dict:
    """Medios de pago habilitados: {id: dato a mostrar al cliente}. Efectivo por defecto."""
    cfg = d.get("pagos") or {"efectivo": True}
    out = {}
    if cfg.get("efectivo"):
        out["efectivo"] = ""
    if cfg.get("mercadopago") or (mercadopago.activo() and cfg.get("mp_checkout")):
        out["mercadopago"] = cfg.get("mercadopago", "")
    if cfg.get("transferencia"):
        out["transferencia"] = cfg["transferencia"]
    return out or {"efectivo": ""}


@app.get("/panel/{slug}", response_class=HTMLResponse)
def panel(request: Request, slug: str, t: str = ""):
    row, d, bp = _negocio(slug)
    if not secrets.compare_digest(t, row["token_admin"]):
        raise HTTPException(403, "Link de panel inválido")
    with db() as c:
        peds = [dict(r) | {"detalle": json.loads(r["detalle"])} for r in
                c.execute("SELECT * FROM pedidos WHERE negocio_id=? ORDER BY id DESC LIMIT 200", (row["id"],))]
    return tpl.TemplateResponse(request, "panel.html", {"slug": slug, "d": d, "bp": bp, "pedidos": peds,
                                                         "token": t, "pagos_cfg": d.get("pagos") or {"efectivo": True},
                                                         "mp_activo": mercadopago.activo()})


# ---------- panel: productos, CSV, medios de pago ----------

def _auth(slug, t):
    row, d, bp = _negocio(slug)
    if not secrets.compare_digest(t, row["token_admin"]):
        raise HTTPException(403, "Link de panel inválido")
    return row, d, bp


def _guardar(row_id, d):
    with db() as c:
        c.execute("UPDATE negocios SET datos=? WHERE id=?", (json.dumps(d, ensure_ascii=False), row_id))


class Items(BaseModel):
    items: list[dict] = Field(default_factory=list, max_length=200)


@app.put("/api/panel/{slug}/items")
def guardar_items(slug: str, body: Items, t: str = ""):
    row, d, bp = _auth(slug, t)
    items = launcher.validar({"items": body.items}).get("items", []) if body.items else []
    if not items:
        raise HTTPException(400, "Cargá al menos un producto con nombre y precio.")
    d["items"] = items
    _guardar(row["id"], d)
    return {"items": items}


@app.post("/api/panel/{slug}/csv")
async def importar_csv(slug: str, request: Request, t: str = "", reemplazar: bool = False):
    import csv
    import io
    row, d, bp = _auth(slug, t)
    raw = (await request.body())[:200_000].decode("utf-8-sig", errors="replace")
    if not raw.strip():
        raise HTTPException(400, "El archivo está vacío.")
    try:
        dialect = csv.Sniffer().sniff(raw[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    filas = list(csv.reader(io.StringIO(raw), dialect))
    cab = [h.strip().lower() for h in filas[0]] if filas else []
    idx = lambda *ns: next((cab.index(n) for n in ns if n in cab), None)
    i_n, i_p, i_d = idx("nombre", "producto", "servicio", "name"), idx("precio", "price", "valor"), idx("duracion", "duracion_min", "minutos")
    if i_n is None or i_p is None:  # sin encabezado: columna 1 nombre, 2 precio
        i_n, i_p, i_d, datos = 0, 1, 2 if bp["modo"] == "turnos" else None, filas
    else:
        datos = filas[1:]
    nuevos = []
    for f in datos:
        if len(f) <= max(i_n, i_p):
            continue
        it = {"nombre": f[i_n], "precio": re.sub(r"[^\d]", "", f[i_p].split(",")[0])}
        if i_d is not None and len(f) > i_d and re.sub(r"\D", "", f[i_d]):
            it["duracion_min"] = re.sub(r"\D", "", f[i_d])
        nuevos.append(it)
    nuevos = launcher.validar({"items": nuevos}).get("items", [])
    if not nuevos:
        raise HTTPException(400, "No encontré productos válidos. Formato: nombre,precio")
    d["items"] = (nuevos if reemplazar else (d.get("items", []) + nuevos))[:200]
    _guardar(row["id"], d)
    return {"importados": len(nuevos), "items": d["items"]}


class Pagos(BaseModel):
    efectivo: bool = True
    mercadopago: str = Field("", max_length=120)
    transferencia: str = Field("", max_length=120)


@app.put("/api/panel/{slug}/pagos")
def guardar_pagos(slug: str, p: Pagos, t: str = ""):
    row, d, bp = _auth(slug, t)
    if not (p.efectivo or p.mercadopago.strip() or p.transferencia.strip()):
        raise HTTPException(400, "Dejá al menos un medio de pago activo.")
    d["pagos"] = {"efectivo": p.efectivo, "mercadopago": p.mercadopago.strip(), "transferencia": p.transferencia.strip()}
    _guardar(row["id"], d)
    return d["pagos"]
