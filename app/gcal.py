"""Integración con Google Calendar (API oficial, OAuth 2.0). Se activa con GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET en .env.

- El negocio conecta su cuenta desde el panel ("Conectar con Google Calendar").
- Cada turno reservado se crea como evento en su calendario (y se borra si se cancela).
- Lo que el negocio tiene ocupado en su calendario (FreeBusy) bloquea esos horarios en la agenda pública.
La base de datos propia sigue siendo la fuente de verdad: si Google no responde, los turnos se siguen tomando.
"""
import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import urlencode

import httpx

log = logging.getLogger("marcia.gcal")
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.freebusy https://www.googleapis.com/auth/userinfo.email"
TZ = "America/Argentina/Buenos_Aires"
_cache: dict = {}  # (negocio_id, fecha) -> (ts, ocupados)


def activo() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID", "").strip() and os.getenv("GOOGLE_CLIENT_SECRET", "").strip())


def _redirect() -> str:
    return os.getenv("BASE_URL", "").rstrip("/") + "/oauth/google/callback"


def firmar(slug: str, token_admin: str) -> str:
    return slug + "." + hmac.new(token_admin.encode(), ("gcal:" + slug).encode(), hashlib.sha256).hexdigest()[:32]


def verificar(state: str, token_admin: str) -> bool:
    slug = state.split(".", 1)[0]
    return hmac.compare_digest(state, firmar(slug, token_admin))


def url_conexion(slug: str, token_admin: str) -> str:
    return AUTH + "?" + urlencode({"client_id": os.getenv("GOOGLE_CLIENT_ID"), "redirect_uri": _redirect(),
                                   "response_type": "code", "scope": SCOPES, "access_type": "offline",
                                   "prompt": "consent", "state": firmar(slug, token_admin)})


def canjear_codigo(code: str) -> dict:
    r = httpx.post(TOKEN, data={"code": code, "client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                                "redirect_uri": _redirect(), "grant_type": "authorization_code"}, timeout=15)
    r.raise_for_status()
    j = r.json()
    email = ""
    try:
        u = httpx.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {j['access_token']}"}, timeout=10)
        email = u.json().get("email", "")
    except Exception:
        pass
    return {"refresh_token": j.get("refresh_token", ""), "access_token": j["access_token"],
            "expira": int(time.time()) + int(j.get("expires_in", 3600)) - 60, "email": email}


def _access(db, negocio_id: int) -> str | None:
    """Devuelve un access_token válido (lo renueva con el refresh_token si venció)."""
    with db() as c:
        r = c.execute("SELECT * FROM google WHERE negocio_id=?", (negocio_id,)).fetchone()
    if not r or not r["refresh_token"]:
        return None
    if r["access_token"] and r["expira"] > time.time():
        return r["access_token"]
    try:
        t = httpx.post(TOKEN, data={"client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                                    "refresh_token": r["refresh_token"], "grant_type": "refresh_token"}, timeout=10)
        t.raise_for_status()
        j = t.json()
    except Exception as ex:
        log.warning("Google: no se pudo renovar el token del negocio %s: %s", negocio_id, ex)
        return None
    with db() as c:
        c.execute("UPDATE google SET access_token=?, expira=? WHERE negocio_id=?",
                  (j["access_token"], int(time.time()) + int(j.get("expires_in", 3600)) - 60, negocio_id))
    return j["access_token"]


def ocupados(db, negocio_id: int, fecha: str) -> list[tuple]:
    """Bloques ocupados del calendario del negocio ese día: [(YYYY-MM-DD HH:MM, minutos, '_')]. Cache 60 s."""
    if not activo():
        return []
    k = (negocio_id, fecha)
    if k in _cache and time.time() - _cache[k][0] < 60:
        return _cache[k][1]
    tok = _access(db, negocio_id)
    if not tok:
        return []
    out = []
    try:
        r = httpx.post(f"{API}/freeBusy", headers={"Authorization": f"Bearer {tok}"}, timeout=4,
                       json={"timeMin": f"{fecha}T00:00:00-03:00", "timeMax": f"{fecha}T23:59:59-03:00", "timeZone": TZ,
                             "items": [{"id": "primary"}]})
        r.raise_for_status()
        from datetime import datetime
        for b in r.json().get("calendars", {}).get("primary", {}).get("busy", []):
            ini = datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone()
            fin = datetime.fromisoformat(b["end"].replace("Z", "+00:00")).astimezone()
            out.append((ini.strftime("%Y-%m-%d %H:%M"), max(5, int((fin - ini).total_seconds() // 60)), "_"))
    except Exception as ex:
        log.warning("Google FreeBusy falló (se usa solo la agenda propia): %s", ex)
    _cache[k] = (time.time(), out)
    return out


def crear_evento(db, negocio_id: int, pedido: dict, duracion: int, negocio: str) -> str | None:
    if not activo() or not pedido.get("cuando"):
        return None
    tok = _access(db, negocio_id)
    if not tok:
        return None
    from datetime import datetime, timedelta
    ini = datetime.strptime(pedido["cuando"], "%Y-%m-%d %H:%M")
    fin = ini + timedelta(minutes=duracion)
    servicios = ", ".join(x["nombre"] for x in pedido["detalle"])
    try:
        r = httpx.post(f"{API}/calendars/primary/events", headers={"Authorization": f"Bearer {tok}"}, timeout=8, json={
            "summary": f"{servicios} · {pedido['cliente']}",
            "description": f"Turno #{pedido['id']} reservado con Marcia Neon\nCliente: {pedido['cliente']}\nContacto: {pedido.get('contacto') or '-'}\nNota: {pedido.get('nota') or '-'}",
            "start": {"dateTime": ini.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": TZ},
            "end": {"dateTime": fin.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": TZ},
            "source": {"title": negocio, "url": os.getenv("BASE_URL", "")}})
        r.raise_for_status()
        _cache.pop((negocio_id, pedido["cuando"][:10]), None)
        return r.json().get("id")
    except Exception as ex:
        log.warning("Google: no se pudo crear el evento del turno %s: %s", pedido.get("id"), ex)
        return None


def borrar_evento(db, negocio_id: int, evento_id: str):
    if not activo() or not evento_id:
        return
    tok = _access(db, negocio_id)
    if tok:
        try:
            httpx.delete(f"{API}/calendars/primary/events/{evento_id}", headers={"Authorization": f"Bearer {tok}"}, timeout=8)
        except Exception as ex:
            log.warning("Google: no se pudo borrar el evento %s: %s", evento_id, ex)
