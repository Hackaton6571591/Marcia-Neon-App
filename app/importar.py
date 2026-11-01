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


# ---------- tiendas con API JSON (headless, Shopify, WooCommerce, etc.) ----------

def _num(v) -> int | None:
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        t = re.sub(r"[^\d.,]", "", v)
        if not t:
            return None
        if re.search(r",\d{1,2}$", t):          # 12.345,50 -> 12345
            t = t.rsplit(",", 1)[0].replace(".", "")
        elif re.search(r"\.\d{1,2}$", t):      # 12345.00 -> 12345
            t = t.rsplit(".", 1)[0].replace(",", "")
        else:
            t = t.replace(".", "").replace(",", "")
        return int(t) if t else None
    return None


def _primero(it: dict, *keys):
    for k in keys:
        v = it.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _img(v) -> str | None:
    if isinstance(v, str):
        return v
    if isinstance(v, list) and v:
        return _img(v[0])
    if isinstance(v, dict):
        return _primero(v, "src", "url", "thumbnail", "large", "medium")
    return None


def _producto(it: dict) -> dict | None:
    nombre = _primero(it, "name", "nombre", "title", "titulo")
    if not isinstance(nombre, str) or not nombre.strip():
        return None
    precio = None
    if isinstance(it.get("prices"), dict):  # WooCommerce Store API (unidades menores)
        pr = it["prices"]
        precio = _num(pr.get("price"))
        if precio is not None and pr.get("currency_minor_unit"):
            precio //= 10 ** int(pr["currency_minor_unit"])
    if precio is None:
        precio = _num(_primero(it, "price", "precio", "sale_price", "final_price", "salePrice", "finalPrice",
                               "regular_price", "regularPrice", "amount", "price_min"))
    if precio is None and isinstance(it.get("variants"), list) and it["variants"]:  # Shopify
        precio = _num(it["variants"][0].get("price"))
    if not precio or precio <= 0:
        return None
    cat = _primero(it, "category", "categoria", "product_type", "productType")
    if cat is None and isinstance(it.get("categories"), list) and it["categories"]:
        c0 = it["categories"][0]
        cat = c0.get("name") if isinstance(c0, dict) else c0
    desc = _primero(it, "short_description", "shortDescription", "description", "descripcion", "body_html")
    out = {"nombre": html.unescape(nombre.strip())[:60], "precio": precio}
    if isinstance(cat, str) and cat.strip():
        out["categoria"] = html.unescape(cat.strip())[:30]
    if isinstance(desc, str) and desc.strip():
        out["descripcion"] = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", desc))).strip()[:200]
    if (u := _img(_primero(it, "image", "imagen", "images", "thumbnail", "image_url", "imageUrl", "featured_image", "photo", "foto"))):
        out["_img"] = u
    return out


def _buscar_listas(obj, prof=0) -> list[list[dict]]:
    """Recorre el JSON buscando listas de objetos que parezcan productos."""
    res = []
    if prof > 5:
        return res
    if isinstance(obj, list) and len(obj) >= 2 and all(isinstance(x, dict) for x in obj[:5]):
        prods = [p for p in (_producto(x) for x in obj) if p]
        if len(prods) >= 2:
            res.append(prods)
    if isinstance(obj, dict):
        for v in obj.values():
            res += _buscar_listas(v, prof + 1)
    elif isinstance(obj, list):
        for v in obj[:50]:
            if isinstance(v, (dict, list)):
                res += _buscar_listas(v, prof + 1)
    return res


async def _get_json(c: httpx.AsyncClient, url: str):
    if not _segura(url):
        return None
    try:
        r = await c.get(url)
        if r.status_code == 200 and "json" in r.headers.get("content-type", "") and len(r.content) < 5_000_000:
            return r.json()
    except Exception:
        pass
    return None


async def desde_apis(url: str, page: str) -> list[dict]:
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    cand = []
    for m in re.findall(r"""["'`]((?:https?://[^"'`\s]+)?/[^"'`\s]*product[^"'`\s]*)["'`]""", page, re.I):
        full = urljoin(base, m.split("?")[0].rstrip("/"))
        if urlparse(full).netloc == u.netloc and full not in cand and not re.search(r"\.(js|css|png|jpg|webp|svg)$", full):
            cand.append(full)
    cand = cand[:6] + [base + "/products.json?limit=250", base + "/wp-json/wc/store/v1/products?per_page=100",
                       base + "/wp-json/wc/store/products?per_page=100"]
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}) as c:
        for cu in cand:
            j = await _get_json(c, cu)
            if j is None:
                continue
            listas = _buscar_listas(j)
            if listas:
                prods = max(listas, key=len)
                log.info("Productos encontrados en %s: %d", cu, len(prods))
                return prods
    return []


def _filtrar_categoria(prods: list[dict], url: str) -> list[dict]:
    from urllib.parse import parse_qs
    q = parse_qs(urlparse(url).query)
    cat = (q.get("category") or q.get("categoria") or q.get("cat") or [None])[0]
    if not cat:
        return prods
    f = [p for p in prods if p.get("categoria", "").lower() == cat.lower()]
    return f or prods


async def _bajar_fotos(prods: list[dict], prefijo: str, maximo: int = 40):
    import asyncio
    sem = asyncio.Semaphore(6)

    async def una(i, p):
        async with sem:
            if p.get("_img"):
                ruta = await _bajar_imagen(urljoin("https://x/", p["_img"]) if p["_img"].startswith("//") else p["_img"],
                                           f"{prefijo}-{i}")
                if ruta and not ruta.endswith((".svg", ".ico", ".gif")):
                    p["imagen"] = ruta
    await asyncio.gather(*(una(i, p) for i, p in enumerate(prods[:maximo])))
    for p in prods:
        p.pop("_img", None)


async def importar(url: str, servicio: bool, prefijo: str = "imp") -> tuple[list[dict], str]:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    page = await descargar(url)
    prods = await desde_apis(url, page)
    origen = "api"
    if not prods:
        texto = a_texto(page)
        prods = await con_ia(texto, servicio) or []
        origen = "deepseek" if prods else "simulado"
        if not prods:
            prods = heuristica(texto, servicio)
    prods = _filtrar_categoria(prods, url)[:200]
    if origen == "api":
        await _bajar_fotos(prods, prefijo)
    return validar({"items": prods}).get("items", []), origen


# ---------- foto del menú (DeepSeek lee imágenes) ----------

async def desde_foto(datos: bytes, mime: str, servicio: bool, cred: dict | None) -> list[dict]:
    import base64
    from . import ia
    if not cred:
        raise ValueError("La lectura de fotos necesita la IA activa.")
    prompt = ("Esta es la foto de un menú/lista de precios de un negocio. Extraé TODOS los productos con su precio. "
              'Respondé SOLO JSON: {"items":[{"nombre":str,"precio":int (pesos, sin puntos),"categoria":str'
              + (',"duracion_min":int' if servicio else "") + "}]}. No inventes nada que no esté en la imagen.")
    msgs = [{"role": "user", "content": [{"type": "text", "text": prompt},
             {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(datos).decode()}"}}]}]
    out = await ia.chat_json(cred, msgs, max_tokens=2500, temperature=0, timeout=60)
    return validar(out).get("items", [])


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
