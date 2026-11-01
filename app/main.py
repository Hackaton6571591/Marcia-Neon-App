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

from . import ia, importar, launcher, mercadopago, vendedor
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
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
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
        c.execute("CREATE TABLE IF NOT EXISTS secretos(negocio_id INT PRIMARY KEY, proveedor TEXT, api_key TEXT, modelo TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, negocio_id INT, estado TEXT, historia TEXT, mensajes INT DEFAULT 0, creado INT)")
        cols = [r[1] for r in c.execute("PRAGMA table_info(pedidos)")]
        if "pago" not in cols:
            c.execute("ALTER TABLE pedidos ADD COLUMN pago TEXT")
        for col, tipo in (("pagado", "INT DEFAULT 0"), ("seguimiento", "TEXT"), ("historial", "TEXT"), ("actualizado", "INT")):
            if col not in cols:
                c.execute(f"ALTER TABLE pedidos ADD COLUMN {col} {tipo}")
        c.execute("UPDATE pedidos SET pagado=1, estado='nuevo' WHERE estado='pagado'")


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
    d, respuesta, proveedor = await launcher.procesar(d, m.texto.strip(), hist, sid)
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


ILUS = [  # (palabras clave, emoji): ilustración automática cuando no hay foto
    (("porcion", "porción"), "🍕"), (("pizza", "muzza", "napolit", "fugaz", "calabres", "especial", "jamon", "provolone", "cuatro queso", "rucula"), "🍕"),
    (("empanada",), "🥟"), (("faina", "fainá"), "🫓"), (("coca", "sprite", "fanta", "gaseosa", "pepsi", "seven", "7up", "agua", "jugo", "bebida"), "🥤"),
    (("cerveza", "birra", "quilmes", "stella"), "🍺"), (("vino",), "🍷"), (("flan", "postre", "tiramisu"), "🍮"), (("helado",), "🍨"),
    (("hamburg", "burger"), "🍔"), (("papas", "fritas"), "🍟"), (("milanesa",), "🥩"), (("sushi", "roll"), "🍣"), (("cafe", "café"), "☕"),
    (("combo", "promo"), "🎁"), (("corte",), "✂️"), (("color", "tintura", "mechas"), "🎨"), (("barba",), "🧔"), (("manicur", "uñas", "unas"), "💅"),
    (("consulta", "control", "turno"), "🩺"), (("masaje",), "💆"), (("martillo",), "🔨"), (("tornillo", "clavo", "bulon"), "🔩"),
    (("cinta",), "🧻"), (("pintura",), "🖌️"), (("llave", "pinza", "herramienta"), "🔧"),
]


def ilus(it: dict, defecto: str = "✨") -> dict:
    texto = (it.get("categoria", "") + " " + it["nombre"]).lower()
    emoji = next((e for kws, e in ILUS if any(k in texto for k in kws)), defecto)
    return {"emoji": emoji, "hue": sum(map(ord, it["nombre"])) % 360}


@app.get("/n/{slug}", response_class=HTMLResponse)
def ver_negocio(request: Request, slug: str):
    row, d, bp = _negocio(slug)
    grupos: dict[str, list] = {}
    for i, it in enumerate(d["items"]):
        cat = it.get("categoria") or ("Servicios" if bp["modo"] == "turnos" else "Productos")
        grupos.setdefault(cat, []).append((i, it, ilus(it, bp["emoji"])))
    nombres = [it["nombre"] for it in d["items"]]
    return tpl.TemplateResponse(request, "negocio.html", {"slug": slug, "d": d, "bp": bp, "pagos": _pagos(d),
                                                           "grupos": grupos, "ej": nombres[0] if nombres else ""})


@app.get("/n/{slug}/manifest.webmanifest")
def manifest_negocio(slug: str):
    """Cada tienda se instala como app propia del negocio (Agregar a inicio)."""
    from fastapi.responses import JSONResponse
    row, d, bp = _negocio(slug)
    return JSONResponse({"name": d["nombre"], "short_name": d["nombre"][:12], "start_url": f"/n/{slug}",
                         "scope": f"/n/{slug}", "display": "standalone", "background_color": "#07060f",
                         "theme_color": "#07060f", "lang": "es",
                         "icons": [{"src": d.get("logo") or "/static/icon.svg", "sizes": "any"}]},
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
    return await _registrar_pedido(request, slug, row, d, bp, p.items, p.cliente, p.contacto, p.cuando, p.nota, p.pago)


async def _registrar_pedido(request, slug, row, d, bp, items: dict, cliente, contacto, cuando, nota, pago) -> dict:
    """Única vía para crear pedidos/turnos (formulario y vendedor virtual). Total calculado acá."""
    detalle, total = [], 0
    for idx, cant in items.items():
        idx, cant = int(idx), int(cant)
        if 0 <= idx < len(d["items"]) and 0 < cant <= 50:
            it = d["items"][idx]
            if it.get("stock") is not None and cant > int(it["stock"]):
                raise HTTPException(409, f"De {it['nombre']} " + ("no queda stock." if int(it["stock"]) <= 0 else f"solo quedan {it['stock']}."))
            detalle.append({"nombre": it["nombre"], "cantidad": cant, "precio": it["precio"]})
            total += it["precio"] * cant
    if not detalle:
        raise HTTPException(400, "Elegí al menos un producto o servicio.")
    if bp["modo"] == "turnos" and not cuando:
        raise HTTPException(400, "Elegí día y horario para el turno.")
    if bp["modo"] == "turnos":
        _validar_turno(row["id"], d, detalle, cuando)
    pagos = _pagos(d)
    if pago not in pagos:
        raise HTTPException(400, "Medio de pago no disponible.")
    with db() as c:
        ahora = int(time.time())
        seg = secrets.token_urlsafe(10)
        cur = c.execute("INSERT INTO pedidos(negocio_id,tipo,cliente,contacto,detalle,total,cuando,nota,pago,creado,"
                        "estado,seguimiento,historial,actualizado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (row["id"], bp["modo"], cliente[:60], (contacto or "")[:40], json.dumps(detalle, ensure_ascii=False),
                         total, cuando or "", (nota or "")[:300], pago, ahora, "nuevo", seg,
                         json.dumps([{"estado": "nuevo", "ts": ahora}]), ahora))
    numero = cur.lastrowid
    _webhook(d, "pedido.creado", _pedido_publico(numero))
    if any(d["items"][int(k)].get("stock") is not None for k in items if 0 <= int(k) < len(d["items"])):
        for k, cant in items.items():  # descontar stock
            it = d["items"][int(k)]
            if it.get("stock") is not None:
                it["stock"] = max(0, int(it["stock"]) - int(cant))
        _guardar(row["id"], d)
    pago_url = None
    if pago == "mercadopago" and mercadopago.activo():
        base = os.getenv("BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/").replace("http://", "https://")
        pago_url = await mercadopago.crear_preferencia(numero, d["nombre"], detalle, base, slug)
    return {"numero": numero, "total": total, "detalle": detalle, "pago": pago,
            "pago_info": pagos[pago], "pago_url": pago_url, "seguimiento": f"/n/{slug}/pedido/{numero}?k={seg}"}


class ChatMsg(BaseModel):
    chat: str | None = Field(None, max_length=40)
    texto: str = Field(..., min_length=1, max_length=500)


@app.post("/api/n/{slug}/chat")
async def chat_vendedor(slug: str, m: ChatMsg, request: Request):
    """Vendedor virtual de la tienda."""
    limitar(request, 30, "vendedor")
    row, d, bp = _negocio(slug)
    pagos = _pagos(d)
    with db() as c:
        r = c.execute("SELECT * FROM chats WHERE id=? AND negocio_id=?", (m.chat, row["id"])).fetchone() if m.chat else None
        if r:
            cid, e, hist, n = r["id"], json.loads(r["estado"]), json.loads(r["historia"]), r["mensajes"]
        else:
            cid, e, hist, n = uuid.uuid4().hex, vendedor.estado_inicial(), [], 0
            c.execute("INSERT INTO chats(id,negocio_id,estado,historia,creado) VALUES(?,?,?,?,?)",
                      (cid, row["id"], json.dumps(e), "[]", int(time.time())))
    if n >= 60:
        raise HTTPException(429, "Llegaste al límite de mensajes de esta charla.")
    if e["paso"] == "hecho":  # pedido ya hecho: empieza uno nuevo manteniendo los datos del cliente
        e = {**vendedor.estado_inicial(), "cliente": e["cliente"]}
    respuesta, proveedor = await vendedor.responder(d, bp, pagos, e, m.texto.strip(), hist, ia.credenciales(_secreto(row["id"])))
    pedido = None
    if e["paso"] == "final":
        falta = vendedor.faltantes(e, bp["modo"], pagos)
        if falta:
            e["paso"] = "datos"
            respuesta = vendedor._pedir_dato(e, bp, pagos)
        else:
            try:
                pedido = await _registrar_pedido(request, slug, row, d, bp, e["carrito"], e["cliente"]["nombre"],
                                                 e["cliente"].get("contacto", ""), e.get("cuando") or "",
                                                 ("Entrega: " + e["cliente"]["direccion"]) if e["cliente"].get("direccion") else "",
                                                 e["pago"])
                e["paso"], e["pedido"] = "hecho", pedido["numero"]
                respuesta = _mensaje_confirmacion(d, bp, e, pedido)
            except HTTPException as ex:
                if ex.status_code == 409:
                    e["cuando"], e["paso"] = None, "datos"
                respuesta = f"😕 {ex.detail} " + vendedor._pedir_dato(e, bp, pagos)
    hist = (hist + [{"role": "user", "content": m.texto[:500]}, {"role": "assistant", "content": respuesta}])[-16:]
    with db() as c:
        c.execute("UPDATE chats SET estado=?, historia=?, mensajes=mensajes+1 WHERE id=?",
                  (json.dumps(e, ensure_ascii=False), json.dumps(hist, ensure_ascii=False), cid))
    resumen, total = vendedor.resumen(d, e)
    return {"chat": cid, "respuesta": respuesta, "ia": proveedor, "carrito": e["carrito"], "total": total,
            "paso": e["paso"], "pedido": pedido}


def _mensaje_confirmacion(d, bp, e, p) -> str:
    turnos = bp["modo"] == "turnos"
    lineas = "\n".join(f"• {x['cantidad']}× {x['nombre']}" for x in p["detalle"])
    msg = (f"✅ **¡{'Turno reservado' if turnos else 'Pedido confirmado'}! #{p['numero']}**\n{lineas}\n"
           f"**Total: {vendedor.fmt(p['total'])}**\n")
    if turnos:
        msg += f"📅 {e['cuando'].replace(' ', ' a las ')}\n"
    elif e["cliente"].get("direccion"):
        msg += f"🛵 {e['cliente']['direccion']}\n"
    if p["pago"] == "mercadopago":
        msg += ("🔵 Pagá acá: " + p["pago_url"]) if p.get("pago_url") else \
               ("🔵 Pagá con Mercado Pago: " + p["pago_info"]) if p["pago_info"] else "🔵 Te enviamos el link de Mercado Pago por WhatsApp."
    elif p["pago"] == "transferencia":
        msg += f"🏦 Transferí a: {p['pago_info']}"
    else:
        retira = "retira" in (e["cliente"].get("direccion") or "").lower()
        msg += "💵 Pagás en efectivo " + ("en el local." if turnos or retira else "al recibir.")
    base = os.getenv("BASE_URL", "").rstrip("/")
    return msg + f"\n\n📍 Seguí tu pedido en vivo: {base}{p['seguimiento']}\n\n¡Gracias, {e['cliente']['nombre']}! {d['nombre']} ya lo tiene en su panel 💜"


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
                c.execute("UPDATE pedidos SET pagado=1 WHERE id=? AND pago='mercadopago'", (int(ref),))
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
    """Medios de pago habilitados: {id: dato a mostrar al cliente}. Por defecto: efectivo + Mercado Pago."""
    cfg = d.get("pagos") or {"efectivo": True, "mp": True}
    out = {}
    if cfg.get("efectivo"):
        out["efectivo"] = ""
    if cfg.get("mp", True) or cfg.get("mercadopago"):
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
                                                         "token": t, "pagos_cfg": d.get("pagos") or {"efectivo": True, "mp": True},
                                                         "mp_activo": mercadopago.activo(),
                                                         "despacho": d.get("despacho") or {}, "webhook": d.get("webhook") or {}})


# ---------- gestión profesional de pedidos ----------

ESTADOS = {
    "pedidos": ["nuevo", "confirmado", "preparando", "listo", "en_camino", "entregado", "cancelado"],
    "turnos": ["nuevo", "confirmado", "completado", "ausente", "cancelado"],
}
ETIQUETAS = {"nuevo": "Nuevo", "confirmado": "Confirmado", "preparando": "En preparación", "listo": "Listo",
             "en_camino": "En camino", "entregado": "Entregado", "cancelado": "Cancelado",
             "completado": "Completado", "ausente": "No asistió"}


def _pedido_publico(pid: int) -> dict:
    with db() as c:
        r = c.execute("SELECT * FROM pedidos WHERE id=?", (pid,)).fetchone()
    p = dict(r)
    p["detalle"] = json.loads(p["detalle"])
    p["historial"] = json.loads(p.get("historial") or "[]")
    p["estado_txt"] = ETIQUETAS.get(p["estado"], p["estado"])
    return p


def _webhook(d: dict, evento: str, pedido: dict):
    """Envía el pedido al sistema del negocio (cocina, ERP, delivery). Firmado con HMAC-SHA256. No bloquea."""
    cfg = d.get("webhook") or {}
    if not cfg.get("url"):
        return
    import asyncio
    import hashlib
    import hmac

    async def enviar():
        cuerpo = json.dumps({"evento": evento, "negocio": d["nombre"], "pedido":
                             {k: pedido.get(k) for k in ("id", "estado", "cliente", "contacto", "detalle", "total", "cuando",
                                                         "nota", "pago", "pagado", "creado")}}, ensure_ascii=False).encode()
        firma = hmac.new(cfg.get("secreto", "").encode(), cuerpo, hashlib.sha256).hexdigest()
        try:
            if not importar._segura(cfg["url"]):
                return
            import httpx
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as cl:
                await cl.post(cfg["url"], content=cuerpo, headers={"Content-Type": "application/json",
                                                                  "X-Marcia-Evento": evento, "X-Marcia-Firma": firma})
        except Exception as ex:
            logging.getLogger("marcia.webhook").warning("Webhook falló: %s", ex)

    try:
        asyncio.get_running_loop().create_task(enviar())
    except RuntimeError:
        pass


@app.get("/api/panel/{slug}/pedidos")
def listar_pedidos(slug: str, t: str = ""):
    row, d, bp = _auth(slug, t)
    with db() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM pedidos WHERE negocio_id=? ORDER BY id DESC LIMIT 200", (row["id"],))]
    return {"pedidos": [_pedido_publico(i) for i in ids], "estados": ESTADOS[bp["modo"]], "etiquetas": ETIQUETAS}


class CambioEstado(BaseModel):
    estado: str = Field(..., max_length=20)


@app.put("/api/panel/{slug}/pedidos/{pid}/estado")
def cambiar_estado(slug: str, pid: int, body: CambioEstado, t: str = ""):
    row, d, bp = _auth(slug, t)
    if body.estado not in ESTADOS[bp["modo"]]:
        raise HTTPException(400, "Estado inválido.")
    with db() as c:
        r = c.execute("SELECT historial, detalle, estado FROM pedidos WHERE id=? AND negocio_id=?", (pid, row["id"])).fetchone()
        if not r:
            raise HTTPException(404)
        ahora = int(time.time())
        hist = json.loads(r["historial"] or "[]") + [{"estado": body.estado, "ts": ahora}]
        c.execute("UPDATE pedidos SET estado=?, historial=?, actualizado=? WHERE id=?",
                  (body.estado, json.dumps(hist), ahora, pid))
        if body.estado == "cancelado" and r["estado"] != "cancelado":  # devolver stock
            cambio = False
            for x in json.loads(r["detalle"]):
                for it in d["items"]:
                    if it["nombre"] == x["nombre"] and it.get("stock") is not None:
                        it["stock"] = int(it["stock"]) + int(x["cantidad"])
                        cambio = True
            if cambio:
                c.execute("UPDATE negocios SET datos=? WHERE id=?", (json.dumps(d, ensure_ascii=False), row["id"]))
    p = _pedido_publico(pid)
    _webhook(d, "pedido.estado", p)
    return p


@app.put("/api/panel/{slug}/pedidos/{pid}/pagado")
def marcar_pagado(slug: str, pid: int, t: str = ""):
    row, d, bp = _auth(slug, t)
    with db() as c:
        c.execute("UPDATE pedidos SET pagado=1-COALESCE(pagado,0) WHERE id=? AND negocio_id=?", (pid, row["id"]))
    return _pedido_publico(pid)


class Webhook(BaseModel):
    url: str = Field("", max_length=300)
    cocina_whatsapp: str = Field("", max_length=30)
    cocina_email: str = Field("", max_length=120)


@app.put("/api/panel/{slug}/despacho")
def guardar_despacho(slug: str, w: Webhook, t: str = ""):
    """A dónde mandar cada pedido: WhatsApp/email de cocina y webhook (API) del sistema del negocio."""
    row, d, bp = _auth(slug, t)
    url = w.url.strip()
    if url and (not url.startswith("https://") or not importar._segura(url)):
        raise HTTPException(400, "El webhook debe ser una URL https pública.")
    actual = d.get("webhook") or {}
    d["webhook"] = {"url": url, "secreto": actual.get("secreto") or secrets.token_hex(16)}
    d["despacho"] = {"whatsapp": re.sub(r"[^\d]", "", w.cocina_whatsapp), "email": w.cocina_email.strip()}
    _guardar(row["id"], d)
    return {"webhook": url, "secreto": d["webhook"]["secreto"], **d["despacho"]}


# ---------- seguimiento del pedido (cliente) ----------

def _pedido_cliente(slug, pid, k):
    row, d, bp = _negocio(slug)
    with db() as c:
        r = c.execute("SELECT seguimiento FROM pedidos WHERE id=? AND negocio_id=?", (pid, row["id"])).fetchone()
    if not r or not r["seguimiento"] or not secrets.compare_digest(k, r["seguimiento"]):
        raise HTTPException(404, "Pedido no encontrado")
    p = _pedido_publico(pid)
    for campo in ("contacto", "seguimiento", "negocio_id"):
        p.pop(campo, None)
    return row, d, bp, p


@app.get("/api/n/{slug}/pedido/{pid}")
def seguimiento_json(slug: str, pid: int, k: str = ""):
    row, d, bp, p = _pedido_cliente(slug, pid, k)
    return {"pedido": p, "estados": [e for e in ESTADOS[bp["modo"]] if e not in ("cancelado", "ausente")],
            "etiquetas": ETIQUETAS}


@app.get("/n/{slug}/pedido/{pid}", response_class=HTMLResponse)
def seguimiento(request: Request, slug: str, pid: int, k: str = ""):
    row, d, bp, p = _pedido_cliente(slug, pid, k)
    return tpl.TemplateResponse(request, "seguimiento.html", {"slug": slug, "d": d, "bp": bp, "p": p, "k": k})


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
    i_c = idx("categoria", "categoría", "rubro", "seccion")
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
        if i_c is not None and len(f) > i_c and f[i_c].strip():
            it["categoria"] = f[i_c].strip()
        nuevos.append(it)
    nuevos = launcher.validar({"items": nuevos}).get("items", [])
    if not nuevos:
        raise HTTPException(400, "No encontré productos válidos. Formato: nombre,precio")
    d["items"] = (nuevos if reemplazar else (d.get("items", []) + nuevos))[:200]
    _guardar(row["id"], d)
    return {"importados": len(nuevos), "items": d["items"]}


@app.get("/media/{archivo}")
def media(archivo: str):
    if not re.fullmatch(r"[a-z0-9-]{1,60}\.(png|jpg|webp|gif|svg|ico)", archivo):
        raise HTTPException(404)
    f = DATA / "media" / archivo
    if not f.is_file():
        raise HTTPException(404)
    headers = {"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"}
    if archivo.endswith(".svg"):  # un SVG podría traer scripts: se sirve aislado
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return FileResponse(f, headers=headers)


class MarcaURL(BaseModel):
    url: str = Field(..., min_length=4, max_length=500)


@app.post("/api/panel/{slug}/marca-url")
async def marca_url(slug: str, body: MarcaURL, request: Request, t: str = ""):
    limitar(request, 5, "marca")
    row, d, bp = _auth(slug, t)
    try:
        marca = await importar.extraer_marca(body.url.strip(), f"n{row['id']}-{secrets.token_hex(3)}")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except Exception:
        raise HTTPException(400, "No pude abrir esa página.")
    if not (marca.get("logo") or marca.get("portada")):
        raise HTTPException(400, "No encontré imágenes en esa página (Instagram a veces lo bloquea). Probá subir el logo.")
    d.update({k: v for k, v in marca.items() if k in ("web", "logo", "portada")})
    _guardar(row["id"], d)
    return {"logo": d.get("logo"), "portada": d.get("portada")}


@app.post("/api/panel/{slug}/logo")
async def subir_logo(slug: str, request: Request, t: str = ""):
    """Sube el logo a mano (cuerpo = imagen PNG/JPG/WEBP, máx 3 MB)."""
    limitar(request, 10, "marca")
    row, d, bp = _auth(slug, t)
    tipo = request.headers.get("content-type", "").split(";")[0].lower()
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(tipo)
    data = await request.body()
    if not ext or not (100 < len(data) <= 3_000_000):
        raise HTTPException(400, "Subí una imagen PNG, JPG o WEBP de hasta 3 MB.")
    (DATA / "media").mkdir(exist_ok=True)
    nombre = f"n{row['id']}-logo-{secrets.token_hex(3)}.{ext}"
    (DATA / "media" / nombre).write_bytes(data)
    d["logo"] = f"/media/{nombre}"
    _guardar(row["id"], d)
    return {"logo": d["logo"]}


def _secreto(negocio_id: int) -> dict | None:
    with db() as c:
        r = c.execute("SELECT proveedor, api_key, modelo FROM secretos WHERE negocio_id=?", (negocio_id,)).fetchone()
    return dict(r) if r else None


class IAConfig(BaseModel):
    proveedor: str = Field("plataforma", pattern="^(plataforma|deepseek|openai)$")
    api_key: str = Field("", max_length=200)
    modelo: str = Field("", max_length=60)


@app.get("/api/panel/{slug}/ia")
def ver_ia(slug: str, t: str = ""):
    """Nunca devuelve la clave: solo los últimos 4 caracteres."""
    row, d, bp = _auth(slug, t)
    s = _secreto(row["id"])
    if not s:
        return {"proveedor": "plataforma", "modelo": "", "clave": ""}
    return {"proveedor": s["proveedor"], "modelo": s["modelo"] or "", "clave": "••••" + s["api_key"][-4:]}


@app.put("/api/panel/{slug}/ia")
async def guardar_ia(slug: str, cfg: IAConfig, request: Request, t: str = ""):
    limitar(request, 5, "ia")
    row, d, bp = _auth(slug, t)
    if cfg.proveedor == "plataforma":
        with db() as c:
            c.execute("DELETE FROM secretos WHERE negocio_id=?", (row["id"],))
        return {"proveedor": "plataforma", "clave": ""}
    actual = _secreto(row["id"]) or {}
    key = cfg.api_key.strip() or (actual.get("api_key") if actual.get("proveedor") == cfg.proveedor else "")
    if not key:
        raise HTTPException(400, "Pegá tu API key.")
    cred = ia.credenciales({"proveedor": cfg.proveedor, "api_key": key, "modelo": cfg.modelo.strip()})
    if not cred:
        raise HTTPException(400, "La IA está desactivada en el servidor.")
    if err := await ia.probar(cred):
        raise HTTPException(400, err)
    with db() as c:
        c.execute("INSERT OR REPLACE INTO secretos(negocio_id, proveedor, api_key, modelo) VALUES(?,?,?,?)",
                  (row["id"], cfg.proveedor, key, cfg.modelo.strip()))
    return {"proveedor": cfg.proveedor, "clave": "••••" + key[-4:], "modelo": cred["modelo"]}


@app.post("/api/panel/{slug}/imagen")
async def subir_imagen_producto(slug: str, request: Request, t: str = ""):
    """Foto de un producto (cuerpo = PNG/JPG/WEBP, máx 3 MB). Devuelve la URL para guardarla en el producto."""
    limitar(request, 30, "imagen")
    row, d, bp = _auth(slug, t)
    tipo = request.headers.get("content-type", "").split(";")[0].lower()
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(tipo)
    data = await request.body()
    if not ext or not (100 < len(data) <= 3_000_000):
        raise HTTPException(400, "Subí una imagen PNG, JPG o WEBP de hasta 3 MB.")
    (DATA / "media").mkdir(exist_ok=True)
    nombre = f"n{row['id']}-p-{secrets.token_hex(4)}.{ext}"
    (DATA / "media" / nombre).write_bytes(data)
    return {"url": f"/media/{nombre}"}


async def _leer_foto(request: Request) -> tuple[bytes, str]:
    tipo = request.headers.get("content-type", "").split(";")[0].lower()
    if tipo not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(400, "Subí una foto PNG, JPG o WEBP.")
    data = await request.body()
    if not (100 < len(data) <= 6_000_000):
        raise HTTPException(400, "La foto debe pesar menos de 6 MB.")
    return data, tipo


@app.post("/api/launcher/sesion/{sid}/foto")
async def launcher_foto(sid: str, request: Request):
    """Foto del menú en el launcher: DeepSeek la lee y carga los productos."""
    limitar(request, 4, "foto")
    data, tipo = await _leer_foto(request)
    with db() as c:
        row = c.execute("SELECT datos, historia FROM sesiones WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(404)
    d = json.loads(row["datos"])
    try:
        items = await importar.desde_foto(data, tipo, d.get("blueprint") == "turnos", ia.credenciales())
    except Exception:
        raise HTTPException(400, "No pude leer la foto 😕 Probá con una más nítida o pasame los productos escritos.")
    if not items:
        raise HTTPException(400, "No encontré productos con precio en la foto.")
    d["items"] = items
    d.setdefault("blueprint", "comercio")
    resp = f"📷 ¡Leí tu menú! Cargué **{len(items)} productos**. Revisalos en la vista previa. " + launcher.pregunta(d)
    hist = (json.loads(row["historia"]) + [{"role": "user", "content": "[foto del menú]"}, {"role": "assistant", "content": resp}])[-12:]
    with db() as c:
        c.execute("UPDATE sesiones SET datos=?, historia=? WHERE id=?", (json.dumps(d, ensure_ascii=False), json.dumps(hist, ensure_ascii=False), sid))
    return _estado(sid, d, "deepseek", resp)


@app.post("/api/panel/{slug}/foto-menu")
async def panel_foto_menu(slug: str, request: Request, t: str = "", reemplazar: bool = False):
    limitar(request, 4, "foto")
    row, d, bp = _auth(slug, t)
    data, tipo = await _leer_foto(request)
    try:
        items = await importar.desde_foto(data, tipo, bp["modo"] == "turnos", ia.credenciales(_secreto(row["id"])))
    except Exception:
        raise HTTPException(400, "No pude leer la foto. Probá con una más nítida.")
    if not items:
        raise HTTPException(400, "No encontré productos con precio en la foto.")
    d["items"] = (items if reemplazar else d.get("items", []) + items)[:200]
    _guardar(row["id"], d)
    return {"importados": len(items), "items": d["items"]}


@app.get("/api/panel/{slug}/exportar")
def exportar_menu(slug: str, t: str = "", formato: str = Query("csv", pattern="^(csv|json)$")):
    """Menú exportable para cargar en PedidosYa / Uber Eats / Rappi u otros sistemas."""
    import csv
    import io
    from fastapi.responses import Response
    row, d, bp = _auth(slug, t)
    base = os.getenv("BASE_URL", "").rstrip("/")
    filas = [{"nombre": it["nombre"], "precio": it["precio"], "categoria": it.get("categoria", ""),
              "descripcion": it.get("descripcion", ""), "stock": "" if it.get("stock") is None else it["stock"],
              "imagen": (base + it["imagen"]) if it.get("imagen") else ""} for it in d["items"]]
    nombre = f"menu-{slug}"
    if formato == "json":
        return Response(json.dumps({"negocio": d["nombre"], "productos": filas}, ensure_ascii=False, indent=2),
                        media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{nombre}.json"'})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(filas[0].keys()) if filas else ["nombre", "precio"])
    w.writeheader()
    w.writerows(filas)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.csv"'})


class ImportarURL(BaseModel):
    url: str = Field(..., min_length=4, max_length=500)
    reemplazar: bool = False


@app.post("/api/panel/{slug}/importar-url")
async def importar_url(slug: str, body: ImportarURL, request: Request, t: str = ""):
    limitar(request, 5, "importar")
    row, d, bp = _auth(slug, t)
    try:
        nuevos, ia = await importar.importar(body.url.strip(), bp["modo"] == "turnos", f"n{row['id']}-i{secrets.token_hex(2)}")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except Exception:
        raise HTTPException(400, "No pude abrir esa página. Probá con otra URL o subí un CSV.")
    if not nuevos:
        raise HTTPException(400, "No encontré productos con precio en esa página (las que cargan con JavaScript, como Instagram, no se pueden leer todavía).")
    d["items"] = (nuevos if body.reemplazar else d.get("items", []) + nuevos)[:200]
    _guardar(row["id"], d)
    return {"importados": len(nuevos), "items": d["items"], "ia": ia}


class Info(BaseModel):
    envio: str = Field("", max_length=300)
    demora: str = Field("", max_length=200)
    condiciones: str = Field("", max_length=500)
    faq: str = Field("", max_length=1500)


@app.put("/api/panel/{slug}/info")
def guardar_info(slug: str, info: Info, t: str = ""):
    """Lo que sabe el vendedor virtual: envíos, demoras, condiciones, preguntas frecuentes."""
    row, d, bp = _auth(slug, t)
    d["info"] = {k: v.strip() for k, v in info.model_dump().items()}
    _guardar(row["id"], d)
    return d["info"]


class Pagos(BaseModel):
    efectivo: bool = True
    mp: bool = True
    mercadopago: str = Field("", max_length=120)
    transferencia: str = Field("", max_length=120)


@app.put("/api/panel/{slug}/pagos")
def guardar_pagos(slug: str, p: Pagos, t: str = ""):
    row, d, bp = _auth(slug, t)
    if not (p.efectivo or p.mp or p.transferencia.strip()):
        raise HTTPException(400, "Dejá al menos un medio de pago activo.")
    d["pagos"] = {"efectivo": p.efectivo, "mp": p.mp, "mercadopago": p.mercadopago.strip() if p.mp else "",
                  "transferencia": p.transferencia.strip()}
    _guardar(row["id"], d)
    return d["pagos"]
