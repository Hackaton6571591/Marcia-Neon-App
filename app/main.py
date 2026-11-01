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

from . import launcher
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
    return {"ok": True, "ia": ia}


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
    return tpl.TemplateResponse(request, "negocio.html", {"slug": slug, "d": d, "bp": bp})


class Pedido(BaseModel):
    cliente: str = Field(..., min_length=1, max_length=60)
    contacto: str = Field("", max_length=40)
    items: dict[int, int] = Field(default_factory=dict)  # índice -> cantidad
    cuando: str = Field("", max_length=40)
    nota: str = Field("", max_length=300)


@app.post("/api/n/{slug}/pedido")
def crear_pedido(slug: str, p: Pedido, request: Request):
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
    with db() as c:
        cur = c.execute("INSERT INTO pedidos(negocio_id,tipo,cliente,contacto,detalle,total,cuando,nota,creado) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (row["id"], bp["modo"], p.cliente, p.contacto, json.dumps(detalle, ensure_ascii=False),
                         total, p.cuando, p.nota, int(time.time())))
    return {"numero": cur.lastrowid, "total": total, "detalle": detalle}


@app.get("/panel/{slug}", response_class=HTMLResponse)
def panel(request: Request, slug: str, t: str = ""):
    row, d, bp = _negocio(slug)
    if not secrets.compare_digest(t, row["token_admin"]):
        raise HTTPException(403, "Link de panel inválido")
    with db() as c:
        peds = [dict(r) | {"detalle": json.loads(r["detalle"])} for r in
                c.execute("SELECT * FROM pedidos WHERE negocio_id=? ORDER BY id DESC LIMIT 200", (row["id"],))]
    return tpl.TemplateResponse(request, "panel.html", {"slug": slug, "d": d, "bp": bp, "pedidos": peds})
