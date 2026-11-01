"""Copiar un menú desde una URL: descarga la página y extrae productos y precios.

Seguridad (SSRF): solo http/https, puertos 80/443, el host debe resolver a IPs públicas,
redirecciones verificadas una por una, máx. 2 MB y 10 s.
"""
import html
import ipaddress
import json
import logging
import os
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

from .launcher import parsear_items, validar

log = logging.getLogger("marcia.importar")


def _segura(url: str) -> bool:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname or (u.port and u.port not in (80, 443)):
        return False
    try:
        ips = {ai[4][0] for ai in socket.getaddrinfo(u.hostname, None)}
    except socket.gaierror:
        return False
    return bool(ips) and all(ipaddress.ip_address(ip).is_global for ip in ips)


async def descargar(url: str) -> str:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    async with httpx.AsyncClient(timeout=10, follow_redirects=False,
                                 headers={"User-Agent": "Mozilla/5.0 (MarciaNeon menu importer)"}) as c:
        for _ in range(5):
            if not _segura(url):
                raise ValueError("Esa URL no está permitida.")
            r = await c.get(url)
            if r.is_redirect and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            r.raise_for_status()
            return r.content[:2_000_000].decode(r.encoding or "utf-8", errors="replace")
    raise ValueError("Demasiadas redirecciones.")


def a_texto(page: str) -> str:
    page = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d|td|span)>", "\n", page)
    page = html.unescape(re.sub(r"<[^>]+>", " ", page))
    lineas = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in page.splitlines()]
    return "\n".join(l for l in lineas if l)


def heuristica(texto: str, servicio: bool) -> list[dict]:
    lineas = texto.splitlines()
    # une "Nombre" + "$ precio" en líneas consecutivas (formato común de menús web)
    unidas = []
    for i, l in enumerate(lineas):
        if re.fullmatch(r"\$?\s*[\d.,]+", l) and unidas:
            unidas[-1] = unidas[-1] + " " + l
        else:
            unidas.append(l)
    cand = [l for l in unidas if "$" in l or re.search(r"\d{3,}", l)]
    return parsear_items("\n".join(cand), servicio)


async def con_ia(texto: str, servicio: bool) -> list[dict] | None:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key or os.getenv("IA_PROVIDER", "deepseek") == "simulado":
        return None
    prompt = ("Extraé el menú/catálogo de este texto de una página web. Respondé SOLO JSON: "
              '{"items":[{"nombre":str,"precio":int (pesos, sin puntos),"categoria":str' +
              (',"duracion_min":int' if servicio else "") + "}]}. No inventes productos ni precios.\n\n" + texto[:12000])
    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {key}"},
                             json={"model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                                   "messages": [{"role": "user", "content": prompt}],
                                   "response_format": {"type": "json_object"}, "temperature": 0, "max_tokens": 4000})
            r.raise_for_status()
            return validar(json.loads(r.json()["choices"][0]["message"]["content"])).get("items", [])
    except Exception as ex:
        log.warning("DeepSeek (importar) falló: %s", ex)
        return None


async def importar(url: str, servicio: bool) -> tuple[list[dict], str]:
    texto = a_texto(await descargar(url))
    items = await con_ia(texto, servicio)
    if items:
        return items, "deepseek"
    return heuristica(texto, servicio), "simulado"


# ---------- marca: logo e imagen desde la web o Instagram ----------

MEDIA = __import__("pathlib").Path(__file__).parent.parent / "data" / "media"
TIPOS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif", "image/svg+xml": "svg",
         "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico"}


def _metas(page: str, base: str) -> dict:
    def meta(*names):
        for n in names:
            m = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(n)}["\'][^>]*content=["\']([^"\']+)', page, re.I) or \
                re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{re.escape(n)}["\']', page, re.I)
            if m:
                return urljoin(base, html.unescape(m.group(1)))
        return None
    icono = None
    for rel in ("apple-touch-icon", "icon", "shortcut icon"):
        m = re.search(rf'<link[^>]+rel=["\']{rel}["\'][^>]*href=["\']([^"\']+)', page, re.I) or \
            re.search(rf'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']{rel}["\']', page, re.I)
        if m:
            icono = urljoin(base, html.unescape(m.group(1)))
            break
    titulo = meta("og:title", "twitter:title")
    if not titulo and (m := re.search(r"<title[^>]*>([^<]{1,120})", page, re.I)):
        titulo = html.unescape(m.group(1)).strip()
    return {"imagen": meta("og:image", "og:image:url", "twitter:image"), "icono": icono,
            "titulo": titulo, "descripcion": meta("og:description", "description")}


async def _bajar_imagen(url: str, nombre: str) -> str | None:
    """Descarga una imagen (con los mismos controles SSRF) y devuelve la ruta pública /media/..."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"}) as c:
            for _ in range(5):
                if not _segura(url):
                    return None
                r = await c.get(url)
                if r.is_redirect and r.headers.get("location"):
                    url = urljoin(url, r.headers["location"])
                    continue
                r.raise_for_status()
                tipo = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if tipo not in TIPOS or len(r.content) > 3_000_000 or len(r.content) < 100:
                    return None
                MEDIA.mkdir(parents=True, exist_ok=True)
                f = MEDIA / f"{nombre}.{TIPOS[tipo]}"
                f.write_bytes(r.content)
                return f"/media/{f.name}"
    except Exception as ex:
        log.warning("No se pudo bajar la imagen %s: %s", url, ex)
    return None


async def extraer_marca(url: str, prefijo: str) -> dict:
    """Lee la web o el perfil de Instagram y guarda logo + imagen de portada. Devuelve lo que encontró."""
    if not re.match(r"^https?://", url):
        url = "https://" + url
    page = await descargar(url)
    m = _metas(page, url)
    out = {"web": url}
    if m.get("titulo"):
        out["titulo_web"] = m["titulo"][:120]
    # Instagram / redes: og:image es la foto de perfil -> logo. En webs: ícono = logo, og:image = portada.
    es_red = re.search(r"instagram\.com|facebook\.com|tiktok\.com", url, re.I)
    if es_red and m.get("imagen"):
        if logo := await _bajar_imagen(m["imagen"], prefijo + "-logo"):
            out["logo"] = logo
    else:
        if m.get("icono") and (logo := await _bajar_imagen(m["icono"], prefijo + "-logo")):
            out["logo"] = logo
        if m.get("imagen") and (portada := await _bajar_imagen(m["imagen"], prefijo + "-portada")):
            out["portada"] = portada
            out.setdefault("logo", portada)
    return out
