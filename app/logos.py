"""Asistente de logos: genera logos vectoriales (SVG) a partir del nombre y el rubro.

Sin IA de imágenes (rápido y gratis). DeepSeek, si está disponible, solo sugiere paleta y lema (~200 tokens).
Seguridad: todo texto se escapa para XML y los colores se validan como #hex. El SVG no lleva scripts.
"""
import json
import re
import unicodedata
from xml.sax.saxutils import escape

PALETAS = {  # por palabra clave del rubro: (color 1, color 2, fondo)
    "pizz": ("#ff4d2e", "#ffb020", "#1a0d08"), "resto": ("#ff4d2e", "#ffb020", "#1a0d08"), "comida": ("#ff4d2e", "#ffb020", "#1a0d08"),
    "empan": ("#e8902a", "#ffd166", "#1d1208"), "cafe": ("#a0522d", "#f4c27a", "#1b120c"), "helad": ("#ff7eb6", "#7afcff", "#140d1f"),
    "ropa": ("#ff3dcb", "#8b5cff", "#12081c"), "lencer": ("#ff3d8b", "#ffb3d1", "#1c0812"), "tienda": ("#ff3dcb", "#00e5ff", "#0d0b1a"),
    "pelu": ("#00c2b8", "#8b5cff", "#081816"), "barber": ("#e0b04a", "#222222", "#111111"), "estetic": ("#ff8fab", "#c77dff", "#1a0c14"),
    "consult": ("#2e86ff", "#2ee6a6", "#071322"), "ferret": ("#ffcc00", "#ff7a00", "#141414"), "kiosco": ("#00b4ff", "#ffdd00", "#0b1220"),
}
DEFECTO = ("#ff3dcb", "#00e5ff", "#0d0b1a")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def paleta(rubro: str) -> tuple[str, str, str]:
    r = _norm(rubro)
    return next((p for k, p in PALETAS.items() if k in r), DEFECTO)


def iniciales(nombre: str) -> str:
    palabras = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ0-9]+", nombre) if w.lower() not in ("de", "la", "el", "los", "las", "y", "the")]
    if not palabras:
        return "M"
    return (palabras[0][0] + (palabras[1][0] if len(palabras) > 1 else "")).upper()


def _txt(nombre: str, n: int = 22) -> str:
    return escape(nombre.strip()[:n])


def opciones(nombre: str, emoji: str, c1: str, c2: str, fondo: str, lema: str = "") -> list[str]:
    ini, nom, lem, em = escape(iniciales(nombre)), _txt(nombre), escape(lema[:34]), escape(emoji or "✨")
    largo = len(nombre.strip()[:22])
    fs = 64 if largo <= 8 else 52 if largo <= 12 else 40 if largo <= 16 else 32
    grad = f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
    font = "font-family=\"Poppins,Montserrat,'Segoe UI',Arial,sans-serif\""
    return [
        # 1) insignia circular con iniciales
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{grad}<circle cx="256" cy="256" r="240" fill="url(#g)"/>'
        f'<circle cx="256" cy="256" r="200" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="6"/>'
        f'<text x="256" y="300" text-anchor="middle" {font} font-size="150" font-weight="800" fill="#fff">{ini}</text></svg>',
        # 2) cuadrado redondeado con el ícono del rubro + nombre
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{grad}<rect width="512" height="512" rx="112" fill="{fondo}"/>'
        f'<rect x="16" y="16" width="480" height="480" rx="100" fill="none" stroke="url(#g)" stroke-width="10"/>'
        f'<text x="256" y="250" text-anchor="middle" font-size="170">{em}</text>'
        f'<text x="256" y="390" text-anchor="middle" {font} font-size="{min(fs, 56)}" font-weight="800" fill="url(#g)">{nom}</text></svg>',
        # 3) logotipo horizontal (nombre + lema)
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 320">{grad}<rect width="640" height="320" rx="48" fill="#ffffff"/>'
        f'<text x="320" y="{175 if lem else 190}" text-anchor="middle" {font} font-size="{fs + 14}" font-weight="900" fill="url(#g)" letter-spacing="-2">{nom}</text>'
        f'<rect x="220" y="{200 if lem else 215}" width="200" height="8" rx="4" fill="url(#g)"/>'
        + (f'<text x="320" y="250" text-anchor="middle" {font} font-size="26" fill="#555">{lem}</text>' if lem else "") + "</svg>",
        # 4) monograma neón
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{grad}<rect width="512" height="512" rx="120" fill="#07060f"/>'
        f'<text x="256" y="300" text-anchor="middle" {font} font-size="170" font-weight="900" fill="none" stroke="url(#g)" stroke-width="10">{ini}</text>'
        f'<text x="256" y="420" text-anchor="middle" {font} font-size="{min(fs - 14, 40)}" font-weight="700" fill="{c2}" letter-spacing="4">{escape(nombre.strip()[:18].upper())}</text></svg>',
    ]


async def sugerir(nombre: str, rubro: str, cred: dict | None) -> tuple[str, str, str, str]:
    """(c1, c2, fondo, lema). Paleta por rubro; si hay IA, pide colores y lema (consulta mínima)."""
    c1, c2, fondo = paleta(rubro)
    lema = ""
    if cred:
        from . import ia
        try:
            out = await ia.chat_json(cred, [{"role": "user", "content":
                f'Negocio "{nombre[:40]}", rubro "{rubro[:40]}". Proponé 2 colores de marca que combinen y un lema de 2 a 4 palabras en español rioplatense. '
                'JSON: {"c1":"#rrggbb","c2":"#rrggbb","lema":"..."}'}], max_tokens=60, temperature=0.7)
            if HEX.match(str(out.get("c1", ""))) and HEX.match(str(out.get("c2", ""))):
                c1, c2 = out["c1"], out["c2"]
            if isinstance(out.get("lema"), str):
                lema = out["lema"].strip().strip('"')[:34]
        except Exception:
            pass
    return c1, c2, fondo, lema


def params_json(nombre, emoji, c1, c2, fondo, lema) -> str:
    return json.dumps({"nombre": nombre, "emoji": emoji, "c1": c1, "c2": c2, "fondo": fondo, "lema": lema}, ensure_ascii=False)
