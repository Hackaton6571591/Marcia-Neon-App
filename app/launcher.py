"""Motor del launcher: máquina de estados + extracción (simulada o con DeepSeek).

La IA solo PROPONE datos; el motor los valida y decide la etapa. Publicar es siempre un clic del usuario.
"""
import json
import logging
import os
import re

import httpx

from .blueprints import BLUEPRINTS, detectar_blueprint

log = logging.getLogger("marcia")

ETAPAS = ["rubro", "dolor", "negocio", "oferta", "horarios", "revision"]


# ---------- motor ----------

def etapa_actual(d: dict) -> str:
    if not d.get("blueprint"):
        return "rubro"
    if not d.get("dolor"):
        return "dolor"
    if not d.get("nombre"):
        return "negocio"
    if not d.get("items"):
        return "oferta"
    if not d.get("horarios"):
        return "horarios"
    return "revision"


def progreso(d: dict) -> int:
    return round(ETAPAS.index(etapa_actual(d)) / (len(ETAPAS) - 1) * 100)


def pregunta(d: dict) -> str:
    e = etapa_actual(d)
    bp = BLUEPRINTS.get(d.get("blueprint") or "", {})
    if e == "rubro":
        return "¡Hola! Soy Marcia 💜 Contame, ¿qué tipo de negocio tenés? (restaurante, peluquería, consultorio, ferretería…)"
    if e == "dolor":
        return f"¡Buenísimo! {bp['emoji']} Te armo una solución de **{'turnos online' if bp['modo']=='turnos' else 'catálogo + pedidos'}**. ¿Cómo te llegan hoy los {'turnos' if bp['modo']=='turnos' else 'pedidos'} y qué es lo que más te complica? (WhatsApp, teléfono, se pierden mensajes…)"
    if e == "negocio":
        return ("Te entiendo, eso es justo lo que vamos a resolver 💪 ¿Cómo se llama tu negocio? Si querés, sumá un teléfono. "
                "Y si tenés **web o Instagram**, pasame el link y uso tu logo e imágenes 📸")
    if e == "oferta":
        return bp["pregunta_oferta"]
    if e == "horarios":
        return "¡Ya casi! ¿Qué días y en qué horario atendés? Ej: *lunes a sábado de 19 a 23:30*"
    return ("¡Listo! 🎉 Mirá la vista previa a la derecha. Si está todo bien, tocá **Publicar** y tu solución queda online. "
            "Si querés cambiar algo, decímelo.")


# ---------- extracción simulada (sin red) ----------

PRECIO_RE = re.compile(r"\$?\s*(\d{1,3}(?:[.,]\d{3})+|\d+)(?:\s*(k|mil))?", re.I)
DUR_RE = re.compile(r"(\d+)\s*(?:min|minutos|')", re.I)
HORA_RE = re.compile(r"(\d+)\s*(?:h|hs|hora|horas)\b", re.I)
TEL_RE = re.compile(r"(\+?\d[\d\s\-]{7,}\d)")


def _precio(txt: str) -> tuple[int | None, str]:
    """Devuelve (precio, texto sin el precio). Ignora números seguidos de min/h."""
    limpio = DUR_RE.sub("", txt)
    limpio = HORA_RE.sub("", limpio)
    m = None
    for m_ in PRECIO_RE.finditer(limpio):
        m = m_
    if not m:
        return None, txt
    n = int(re.sub(r"[.,]", "", m.group(1)))
    if m.group(2):
        n *= 1000
    nombre = limpio[:m.start()].strip(" -:–$,.")
    return n, nombre


def parsear_items(texto: str, servicio: bool) -> list[dict]:
    partes = re.split(r"\n|;|,\s+(?=\D)|\s+y\s+(?=[A-ZÁÉÍÓÚa-z])", texto)
    items = []
    for p in partes:
        p = p.strip(" •-*·\t")
        if not p:
            continue
        precio, nombre = _precio(p)
        if not precio or not nombre or len(nombre) > 60:
            continue
        it = {"nombre": nombre[:1].upper() + nombre[1:], "precio": precio}
        if servicio:
            dm = DUR_RE.search(p)
            hm = HORA_RE.search(p)
            it["duracion_min"] = int(dm.group(1)) if dm else (int(hm.group(1)) * 60 if hm else 30)
        items.append(it)
    return items[:40]


def extraer_simulado(d: dict, texto: str) -> dict:
    e = etapa_actual(d)
    nuevo = {}
    if e == "rubro":
        bp = detectar_blueprint(texto)
        nuevo["blueprint"] = bp or "comercio"
        nuevo["rubro_texto"] = texto[:80]
    elif e == "dolor":
        nuevo["dolor"] = texto[:300]
    elif e == "negocio":
        tel = TEL_RE.search(texto)
        nombre = TEL_RE.sub("", texto)
        nombre = re.sub(r"(?i)^(se llama|el negocio se llama|mi negocio es|somos|es)\s+", "", nombre.strip())
        nombre = re.split(r"(?i)[,.]|\s+y\s+(el|mi)\s+", nombre)[0].strip(" \"'")
        if nombre:
            nuevo["nombre"] = nombre[:60]
        if tel:
            nuevo["telefono"] = tel.group(1).strip()
    elif e == "oferta":
        bp = BLUEPRINTS[d["blueprint"]]
        items = parsear_items(texto, bp["modo"] == "turnos")
        if items:
            nuevo["items"] = items
    elif e == "horarios":
        nuevo["horarios"] = texto[:120]
    return nuevo


# ---------- extracción con DeepSeek ----------

SYSTEM = """Sos Marcia, asistente de Marcia Neon App. Ayudás a dueños de negocios locales argentinos a crear su sistema de pedidos o turnos para no perder clientes por WhatsApp.
Hablás en español rioplatense, cálida, breve (máx 2-3 oraciones), con algún emoji.
Respondé SOLO un objeto JSON: {"respuesta": "<lo que le decís al usuario>", "datos": {<solo los campos que el usuario dio en ESTE mensaje>}}
Campos posibles en "datos":
- "blueprint": uno de "restaurante" (comida/gastronomía), "turnos" (peluquería, consultorio, estética, servicios con cita), "comercio" (ferretería, almacén, tiendas)
- "dolor": texto, cómo recibe pedidos hoy y qué le complica
- "nombre": nombre del negocio; "telefono": teléfono
- "items": lista de {"nombre": str, "precio": int en pesos, "duracion_min": int (solo turnos)}
- "horarios": texto con días y horarios
Nunca inventes datos que el usuario no dio. Tu respuesta debe pedir el siguiente dato de la etapa indicada."""


async def extraer_deepseek(d: dict, texto: str, historia: list[dict]) -> tuple[dict, str] | None:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key or os.getenv("IA_PROVIDER", "deepseek") == "simulado":
        return None
    contexto = {
        "etapa_actual": etapa_actual(d),
        "datos_ya_cargados": {k: v for k, v in d.items() if k in ("blueprint", "dolor", "nombre", "telefono", "items", "horarios")},
        "siguiente_pregunta_sugerida": pregunta(d),
    }
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "system", "content": "Contexto: " + json.dumps(contexto, ensure_ascii=False)}]
    msgs += historia[-6:]
    msgs.append({"role": "user", "content": texto})
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post("https://api.deepseek.com/chat/completions",
                             headers={"Authorization": f"Bearer {key}"},
                             json={"model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), "messages": msgs,
                                   "response_format": {"type": "json_object"}, "temperature": 0.4, "max_tokens": 700})
            r.raise_for_status()
            out = json.loads(r.json()["choices"][0]["message"]["content"])
        return validar(out.get("datos") or {}), str(out.get("respuesta") or "").strip()
    except Exception as ex:  # cae al simulado
        log.warning("DeepSeek falló, uso simulado: %s", ex)
        return None


def validar(datos: dict) -> dict:
    """Solo deja pasar campos conocidos y con el tipo correcto."""
    ok = {}
    if datos.get("blueprint") in BLUEPRINTS:
        ok["blueprint"] = datos["blueprint"]
    for k, n in (("dolor", 300), ("nombre", 60), ("telefono", 30), ("horarios", 120)):
        v = datos.get(k)
        if isinstance(v, str) and v.strip():
            ok[k] = v.strip()[:n]
    items = []
    for it in datos.get("items") or []:
        try:
            nombre = str(it["nombre"]).strip()[:60]
            precio = int(float(str(it["precio"]).replace(".", "").replace(",", ".")))
            if nombre and 0 < precio < 100_000_000:
                x = {"nombre": nombre, "precio": precio}
                if it.get("duracion_min"):
                    x["duracion_min"] = max(5, min(600, int(it["duracion_min"])))
                if isinstance(it.get("categoria"), str) and it["categoria"].strip():
                    x["categoria"] = it["categoria"].strip()[:30]
                items.append(x)
        except (KeyError, ValueError, TypeError):
            continue
    if items:
        ok["items"] = items[:40]
    return ok


# ---------- turno completo ----------

URL_RE = re.compile(r"(https?://[^\s]+|(?:www\.)?(?:instagram\.com|[a-z0-9-]+\.(?:com|com\.ar|ar|net|org|online|site|store|shop))(?:/[^\s]*)?)", re.I)


async def procesar(d: dict, texto: str, historia: list[dict], sesion: str = "") -> tuple[dict, str, str]:
    """Devuelve (datos_actualizados, respuesta, proveedor)."""
    # si comparte su web o Instagram, sacamos logo e imagen de portada
    m = URL_RE.search(texto)
    if m and not d.get("logo"):
        from .importar import extraer_marca
        try:
            marca = await extraer_marca(m.group(1).rstrip(".,)"), "s" + re.sub(r"\W", "", sesion)[:12])
        except Exception as ex:
            log.warning("No se pudo leer la marca: %s", ex)
            marca = {}
        texto = URL_RE.sub("", texto).strip(" ,.") or texto
        if marca.get("logo") or marca.get("portada"):
            d = {**d, **{k: v for k, v in marca.items() if k in ("web", "logo", "portada")}}
            if not URL_RE.sub("", m.string).strip(" ,."):
                return d, "¡Qué lindo! 📸 Ya tomé tu logo e imagen para tu página. " + pregunta(d), "simulado"
        elif not URL_RE.sub("", m.string).strip(" ,."):
            return d, "No pude sacar imágenes de ese link (Instagram a veces lo bloquea) 😕 Igual podés subir tu logo después desde el panel. " + pregunta(d), "simulado"
    res = await extraer_deepseek(d, texto, historia)
    proveedor = "deepseek"
    if res is None:
        nuevo, respuesta, proveedor = extraer_simulado(d, texto), "", "simulado"
    else:
        nuevo, respuesta = res
        # red de seguridad: si la IA no extrajo nada en etapas estructuradas, probamos el parser local
        if not nuevo:
            nuevo = extraer_simulado(d, texto) if etapa_actual(d) in ("rubro", "oferta") else {}
    antes = etapa_actual(d)
    d = {**d, **nuevo}
    if d.get("blueprint") and "turnos" == d["blueprint"]:
        for it in d.get("items", []):
            it.setdefault("duracion_min", 30)
    despues = etapa_actual(d)
    if not respuesta or (despues != antes and proveedor == "simulado"):
        respuesta = pregunta(d)
    elif despues == antes and proveedor == "simulado":
        respuesta = "Mmm, no lo terminé de entender 🤔 " + pregunta(d)
    return d, respuesta, proveedor
