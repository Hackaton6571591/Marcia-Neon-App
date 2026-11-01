"""Vendedor virtual de cada tienda: responde dudas y arma el pedido conversando.

Reglas de oro:
- La IA solo PROPONE acciones (agregar, quitar, datos del cliente, pago, confirmar). El servidor las valida.
- Precios y totales los calcula SIEMPRE el servidor con el catálogo guardado.
- El pedido se crea solo si el cliente confirmó y están todos los datos.
"""
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta


log = logging.getLogger("marcia.vendedor")

NOMBRES_PAGO = {"efectivo": "Efectivo", "mercadopago": "Mercado Pago", "transferencia": "Transferencia"}
NUM = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
       "ocho": 8, "nueve": 9, "diez": 10, "docena": 12, "media": 6}
STOP = {"de", "del", "la", "el", "los", "las", "con", "sin", "y", "a", "en", "x", "por",
        "grande", "grandes", "chica", "chico", "entera", "entero", "mediana", "media", "litro", "litros"}
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def fmt(n: int) -> str:
    return "$" + f"{int(n):,}".replace(",", ".")


# ---------- estado ----------

def estado_inicial() -> dict:
    return {"carrito": {}, "cliente": {}, "pago": None, "cuando": None, "paso": "comprando", "pedido": None}


def resumen(d: dict, e: dict) -> tuple[str, int]:
    lineas, total = [], 0
    for k, c in e["carrito"].items():
        i = int(k)
        if 0 <= i < len(d["items"]):
            it = d["items"][i]
            total += it["precio"] * c
            lineas.append(f"• {c}× {it['nombre']}: {fmt(it['precio'] * c)}")
    return "\n".join(lineas), total


def faltantes(e: dict, modo: str, pagos: dict) -> list[str]:
    f = []
    if not e["carrito"]:
        f.append("productos")
    if not e["cliente"].get("nombre"):
        f.append("nombre")
    if modo == "turnos":
        if not e.get("cuando"):
            f.append("dia_hora")
    elif not e["cliente"].get("direccion"):
        f.append("direccion")
    if not e["cliente"].get("contacto"):
        f.append("contacto")
    if not e.get("pago") or e["pago"] not in pagos:
        f.append("pago")
    return f


# ---------- conocimiento del negocio ----------

def disponible(it: dict) -> bool:
    return it.get("stock") is None or int(it["stock"]) > 0


def ficha(d: dict, bp: dict, pagos: dict) -> str:
    """Ficha COMPACTA (pocos tokens) y ESTABLE (se cachea en DeepSeek). Es la única fuente de verdad del bot."""
    info = d.get("info") or {}
    lineas = []
    for i, it in enumerate(d["items"]):
        st = "" if it.get("stock") is None else (" AGOTADO" if int(it["stock"]) <= 0 else f" stock:{it['stock']}")
        dur = f" {it['duracion_min']}min" if it.get("duracion_min") else ""
        cat = f" [{it['categoria']}]" if it.get("categoria") else ""
        desc = f" ({it['descripcion'][:70]})" if it.get("descripcion") else ""
        lineas.append(f"{i}|{it['nombre']}|{it['precio']}{dur}{cat}{st}{desc}")
    extra = [f"{k}: {v}" for k, v in (("Envío", info.get("envio")), ("Demora", info.get("demora")),
                                        ("Condiciones", info.get("condiciones")), ("FAQ", info.get("faq"))) if v]
    return "\n".join([f"NEGOCIO: {d['nombre']} ({'turnos' if bp['modo'] == 'turnos' else 'pedidos'})",
                      f"Horarios: {d.get('horarios') or '-'}" + (f" | Tel: {d['telefono']}" if d.get("telefono") else ""),
                      "Pagos: " + ", ".join(pagos), *extra,
                      "CATALOGO (indice|nombre|precio en pesos):", *lineas])


# ---------- matching de productos ----------

def _tokens(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9ñ]+", norm(s)) if w not in STOP and len(w) >= 3]


def _match(t: str, w: str) -> bool:
    return w[:4] in t or (len(w) >= 4 and any(x.startswith(w[:4]) for x in t.split()))


def buscar_items(d: dict, texto: str, listar: bool = False) -> list[int]:
    """Índices de productos mencionados.
    - Gana el que coincide en MÁS palabras ("porciones de muzzarella" -> Porción de muzzarella, no la pizza).
    - Al agregar, desempata la proporción de palabras cubiertas ("muzzarella" -> la pizza Muzzarella).
    - listar=True devuelve todos los que coinciden en la mejor cantidad (ej. "empanadas" -> todas).
    """
    t = " ".join(re.findall(r"[a-z0-9ñ]+", norm(texto)))
    scores = []
    for i, it in enumerate(d["items"]):
        tk = _tokens(it["nombre"])
        if not tk:
            continue
        n = sum(1 for w in tk if _match(t, w))
        if n:
            scores.append((n, n / len(tk), i))
    if not scores:
        return []
    mejor = max(n for n, _, _ in scores)
    top = [(r, i) for n, r, i in scores if n == mejor]
    if listar:
        return [i for _, i in top]
    mr = max(r for r, _ in top)
    return [i for r, i in top if r == mr]


def _cantidad(seg: str) -> int:
    n = norm(seg)
    m = re.search(r"\b(\d{1,2})\b", n)
    if m:
        return max(1, min(50, int(m.group(1))))
    if "media docena" in n:
        return 6
    for w, v in NUM.items():
        if re.search(rf"\b{w}\b", n):
            return v
    return 1


# ---------- fechas (turnos) ----------

def parse_cuando(texto: str) -> str | None:
    n = norm(texto)
    hoy = datetime.now()
    fecha = None
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", n):
        fecha = datetime(int(m[1]), int(m[2]), int(m[3]))
    elif m := re.search(r"\b(\d{1,2})/(\d{1,2})\b", n):
        try:
            fecha = datetime(hoy.year, int(m[2]), int(m[1]))
            if fecha.date() < hoy.date():
                fecha = fecha.replace(year=hoy.year + 1)
        except ValueError:
            pass
    elif "pasado manana" in n:
        fecha = hoy + timedelta(days=2)
    elif "manana" in n and not re.search(r"\b(a la|de la|por la) manana\b", n):
        fecha = hoy + timedelta(days=1)
    elif "hoy" in n:
        fecha = hoy
    else:
        for i, dname in enumerate(DIAS):
            if dname in n:
                delta = (i - hoy.weekday()) % 7 or 7
                fecha = hoy + timedelta(days=delta)
                break
    h = re.search(r"\b(\d{1,2})(?::(\d{2})|\s*(?:hs|h|horas?)\b|\s*y\s*media)", n) or re.search(r"\ba las (\d{1,2})\b", n)
    if not fecha or not h:
        return None
    hora = int(h.group(1))
    minutos = int(h.group(2)) if h.lastindex and h.lastindex >= 2 and h.group(2) else (30 if "y media" in n else 0)
    if hora < 8 and "manana" not in n:
        hora += 12  # "a las 4" -> 16 hs
    if hora > 23 or minutos > 59:
        return None
    return f"{fecha:%Y-%m-%d} {hora:02d}:{minutos:02d}"


# ---------- vendedor por reglas (sin red) ----------

SI = re.compile(r"^\s*(si|sí|dale|ok|okey|confirmo|confirmar|confirmado|perfecto|listo|de una|va|correcto|esta bien|está bien)\b", re.I)
NADA_MAS = re.compile(r"\b(nada mas|eso es todo|eso nomas|eso solo|solo eso|es todo|nada|no gracias|terminar|cerrar|confirm\w*|listo)\b", re.I)
PREGUNTA = re.compile(r"(\?|^\s*(que|qué|cual|cuál|cuanto|cuánto|tienen|tenes|tenés|hay|hacen|como|cómo|donde|dónde|a que|hasta))", re.I)


def _faq(d: dict, bp: dict, pagos: dict, n: str) -> str | None:
    info = d.get("info") or {}
    if re.search(r"envio|delivery|envian|mandan|llevan|zona|reparto|costo de env", n):
        return f"🛵 {info['envio']}" if info.get("envio") else "🛵 El costo de envío te lo confirma el local según tu zona. También podés retirar sin cargo."
    if re.search(r"demora|tarda|cuanto tiempo|en cuanto", n):
        return f"⏱️ {info['demora']}" if info.get("demora") else "⏱️ La demora depende del momento; el local te la confirma al recibir el pedido."
    if re.search(r"pag|tarjeta|efectivo|mercado|transfer|debito|credito", n):
        return "💳 Podés pagar con: " + ", ".join(NOMBRES_PAGO[k] for k in pagos) + "."
    if re.search(r"horario|abren|abierto|atienden|cierran", n):
        return f"🕒 Atendemos {d.get('horarios')}."
    if re.search(r"condicion|devolu|cambio|garantia|minimo|factura", n):
        return f"📋 {info['condiciones']}" if info.get("condiciones") else "📋 Para condiciones especiales consultá directo con el local" + (f" al {d['telefono']}." if d.get("telefono") else ".")
    if re.search(r"menu|carta|que tenes|que tienen|que venden|productos|servicios|precios|lista", n):
        return "Esto es lo que tenemos 👇\n" + "\n".join(f"• {it['nombre']}: {fmt(it['precio'])}" + ("" if disponible(it) else " (agotado)") for it in d["items"][:30])
    return None


def vendedor_simulado(d: dict, bp: dict, pagos: dict, e: dict, texto: str) -> str:
    n = norm(texto)
    turnos = bp["modo"] == "turnos"
    paso = e["paso"]

    # --- etapas de cierre ---
    if paso == "confirmar":
        if SI.search(texto):
            e["paso"] = "datos"
            return _pedir_dato(e, bp, pagos)
        e["paso"] = "comprando"  # quiere cambiar algo: sigue comprando
    if paso == "datos":
        _capturar_dato(e, bp, pagos, texto)
        return _pedir_dato(e, bp, pagos)

    # --- comprando ---
    saludo = "¡Hola! 👋 " if re.search(r"^\s*(hola|buenas|buen dia|que tal)", n) else ""
    # respuesta corta a una sugerencia previa: "3", "sí, 2", "dale"
    if e.get("sugerido") is not None and (re.fullmatch(r"\s*(si|sí|dale|ok|bueno)?[\s,]*(\d{1,2}|una?|dos|tres|cuatro|cinco|seis|media docena|docena)?\s*(por favor|porfa)?\s*", n) and n.strip()):
        i = e.pop("sugerido")
        c = 1 if turnos else _cantidad(texto)
        if turnos:
            e["carrito"] = {}
        e["carrito"][str(i)] = (0 if turnos else e["carrito"].get(str(i), 0)) + c
        return f"¡Anotado! {c}× {d['items'][i]['nombre']}. " + _post_carrito(d, e)
    e.pop("sugerido", None)
    if re.search(r"olvid|agreg|sum[aá]|otra cosa|algo mas|una cosa mas|me falto|tambien quiero", n) and not buscar_items(d, texto):
        return "¡Claro! 😊 ¿Qué te sumo?" + ("\n\n" + _post_carrito(d, e) if e["carrito"] else "")
    # quitar productos: "sacá la coca", "sin las empanadas", "borrá 1 porción"
    if re.search(r"\b(sac|quit|borr|elimin|cancel)|\bsin (la|el|los|las)\b|\bno quiero\b", n):
        quitados = []
        for seg in re.split(r",|\by\b", texto):
            for i in buscar_items(d, seg)[:1]:
                if str(i) in e["carrito"]:
                    m = re.search(r"\b(\d{1,2})\b", norm(seg))
                    if m and int(m.group(1)) < e["carrito"][str(i)]:
                        e["carrito"][str(i)] -= int(m.group(1))
                    else:
                        e["carrito"].pop(str(i))
                    quitados.append(d["items"][i]["nombre"])
        if quitados:
            return f"Listo, saqué {', '.join(quitados)} 👍 " + _post_carrito(d, e)
        if e["carrito"]:
            return "¿Qué querés sacar? Decime el producto 🙂\n\n" + _post_carrito(d, e)
    if re.search(r"\b(cambi|modific|correg)", n) and not buscar_items(d, texto):
        return "¡Dale! ¿Qué querés cambiar? Podés decirme *sacá …* o *sumá …* 😉\n\n" + _post_carrito(d, e)
    faq = _faq(d, bp, pagos, n)
    agregados = []
    es_pregunta = PREGUNTA.search(re.sub(r"^\s*(hola|buenas|buen dia)[,!. ]*", "", texto, flags=re.I))
    if not es_pregunta:
        ctx = ""  # contexto: "2 porciones de muzza y 1 de fugazzeta" -> la 2da también es porción
        for seg in re.split(r",|\by\b|\n|\+", texto):
            idx = buscar_items(d, seg + " " + ctx) if ctx and not re.search(r"pizza|entera|grande", norm(seg)) else buscar_items(d, seg)
            if len(idx) != 1:
                idx = buscar_items(d, seg)
            if len(idx) == 1 and not disponible(d["items"][idx[0]]):
                agregados.append(f"⚠️ {d['items'][idx[0]]['nombre']} está agotado")
                continue
            if len(idx) == 1:
                c = 1 if turnos else _cantidad(seg)
                st = d["items"][idx[0]].get("stock")
                if st is not None:
                    c = min(c, int(st) - e["carrito"].get(str(idx[0]), 0))
                    if c <= 0:
                        agregados.append(f"⚠️ no quedan más {d['items'][idx[0]]['nombre']}")
                        continue
                if turnos:
                    e["carrito"] = {}
                e["carrito"][str(idx[0])] = (0 if turnos else e["carrito"].get(str(idx[0]), 0)) + c
                agregados.append(f"{c}× {d['items'][idx[0]]['nombre']}")
                tk = _tokens(d['items'][idx[0]]['nombre'])
                ctx = tk[0] if len(tk) > 1 else ""
    if agregados:
        return saludo + ("¡Anotado! " if not turnos else "¡Perfecto! ") + ", ".join(agregados) + ". " + _post_carrito(d, e)
    if faq:
        return saludo + faq + ("\n\n" + _post_carrito(d, e) if e["carrito"] else "\n\n¿Qué te gustaría " + ("reservar?" if turnos else "pedir?"))
    # pregunta por un producto o categoría ("¿tenés empanadas de carne?", "¿qué empanadas tenés?")
    exacto = buscar_items(d, texto)
    if len(exacto) == 1 and len(_tokens(d["items"][exacto[0]]["nombre"])) > 0 and \
            sum(1 for w in _tokens(d["items"][exacto[0]]["nombre"]) if _match(n, w)) == len(_tokens(d["items"][exacto[0]]["nombre"])):
        it = d["items"][exacto[0]]
        if not disponible(it):
            return saludo + f"Uy, hoy **{it['nombre']}** está agotado 😕 ¿Te ofrezco otra cosa del menú?"
        e["sugerido"] = exacto[0]
        return saludo + f"¡Sí! Tenemos **{it['nombre']}** a {fmt(it['precio'])}" + \
               (f" ({it['duracion_min']} min). ¿Te lo reservo?" if turnos else ". ¿Cuántas te anoto?")
    idx = buscar_items(d, texto, listar=True)
    if idx:
        return saludo + "Tenemos 👇\n" + "\n".join(f"• {d['items'][i]['nombre']}: {fmt(d['items'][i]['precio'])}" + ("" if disponible(d["items"][i]) else " (agotado)") for i in idx) + \
               "\n\n¿Cuál te " + ("reservo?" if turnos else "anoto y cuántas?")
    if e["carrito"] and NADA_MAS.search(n):
        e["paso"] = "confirmar"
        r, tot = resumen(d, e)
        return f"Te resumo {'la reserva' if turnos else 'el pedido'} 📝\n{r}\n**Total: {fmt(tot)}**\n\n¿Te lo confirmo o querés cambiar algo?"
    if saludo:
        return f"¡Hola! 👋 Soy el asistente de {d['nombre']}. Te ayudo a {'reservar un turno' if turnos else 'hacer tu pedido'} o con cualquier duda. ¿Qué buscás?"
    if re.search(r"gracias|genial|buenisimo|perfecto", n):
        return "¡De nada! 😊 ¿Te ayudo con algo más?"
    cats = sorted({it.get("categoria") for it in d["items"] if it.get("categoria")})
    return ("Perdón, no te entendí 🤔 " + (f"Tenemos {', '.join(c.lower() for c in cats)}. " if cats else "") +
            "Podés pedirme, por ejemplo: *" + (f"un turno de {d['items'][0]['nombre'].lower()}" if turnos else f"2 {d['items'][0]['nombre'].lower()}") +
            "*, o preguntarme por envíos, pagos u horarios.")


def _post_carrito(d, e):
    r, tot = resumen(d, e)
    if not e["carrito"]:
        return "¿Qué te gustaría pedir?"
    return f"Llevás:\n{r}\nTotal parcial: **{fmt(tot)}**\n\n¿Algo más o te lo confirmo?"


def _pedir_dato(e, bp, pagos):
    f = faltantes(e, bp["modo"], pagos)
    if "nombre" in f:
        return "¡Genial! 🙌 ¿A nombre de quién lo dejo?"
    if "dia_hora" in f:
        return "¿Para qué día y horario querés el turno? (ej: *viernes 16:30* o *mañana a las 10*)"
    if "direccion" in f:
        return "¿Te lo enviamos? Pasame la **dirección** de entrega, o escribí *retiro* si lo pasás a buscar."
    if "contacto" in f:
        return "¿Un **teléfono o WhatsApp** por si necesitamos avisarte algo?"
    if "pago" in f:
        return "¿Cómo vas a pagar? " + " / ".join(NOMBRES_PAGO[k] for k in pagos)
    return ""


TEL_RE = re.compile(r"(\+?\d[\d\s\-]{7,}\d)")


def _completar_datos(e, bp, pagos, texto):
    """Detecta en un mensaje con varios datos juntos: teléfono, retiro/dirección, medio de pago y nombre."""
    n = norm(texto)
    if not e["cliente"].get("contacto") and (m := TEL_RE.search(texto)):
        e["cliente"]["contacto"] = m.group(1).strip()
    if bp["modo"] != "turnos" and not e["cliente"].get("direccion"):
        if re.search(r"\bretir|paso a buscar|lo busco", n):
            e["cliente"]["direccion"] = "Retira en el local"
        elif m := re.search(r"((?:av\.?|avenida|calle)?\s*[a-záéíóúñ.]+(?:\s+[a-záéíóúñ.]+)*\s+\d{1,5}(?:\s*\w{1,4})?)", texto, re.I):
            if not TEL_RE.fullmatch(m.group(1).strip()):
                e["cliente"]["direccion"] = m.group(1).strip()[:120]
    if not e.get("pago"):
        for k, kw in (("mercadopago", "mercado"), ("transferencia", "transf"), ("efectivo", "efect")):
            if k in pagos and kw in n:
                e["pago"] = k
    if not e["cliente"].get("nombre"):
        primero = re.split(r"[,;\n]", texto)[0].strip()
        primero = re.sub(r"(?i)^(soy|me llamo|a nombre de)\s+", "", primero)
        if 1 < len(primero) <= 30 and not re.search(r"\d", primero) and not SI.search(primero):
            e["cliente"]["nombre"] = primero


def _capturar_dato(e, bp, pagos, texto):
    f = faltantes(e, bp["modo"], pagos)
    t = texto.strip()[:120]
    if "nombre" in f:
        e["cliente"]["nombre"] = re.sub(r"(?i)^(a nombre de|soy|me llamo|es)\s+", "", t)[:60]
    elif "dia_hora" in f:
        e["cuando"] = parse_cuando(t)
        if not e["cuando"]:
            e["_aviso"] = "No pude entender la fecha 🤔 "
    elif "direccion" in f:
        e["cliente"]["direccion"] = "Retira en el local" if re.search(r"retir|paso a buscar|busco", norm(t)) else t
    elif "contacto" in f:
        e["cliente"]["contacto"] = t[:40]
    elif "pago" in f:
        nn = norm(t)
        for k, kw in (("mercadopago", "mercado"), ("transferencia", "transf"), ("efectivo", "efect")):
            if k in pagos and (kw in nn or (k == "mercadopago" and re.search(r"\bmp\b", nn))):
                e["pago"] = k
        if not e.get("pago") and len(pagos) == 1:
            e["pago"] = next(iter(pagos))


# ---------- vendedor con DeepSeek ----------

SYSTEM = """Sos el vendedor virtual de un negocio local argentino. Español rioplatense, cálido y MUY breve (1-3 oraciones), algún emoji.
REGLAS ESTRICTAS:
- Tu ÚNICA fuente es la FICHA (catálogo, stock, precios, info). Si algo no está en la ficha, NO existe: decí que no lo tenés o que el local lo confirma. Nunca inventes productos, precios, promos, envíos ni condiciones.
- Productos AGOTADO: no se venden; ofrecé una alternativa del catálogo. No vendas más unidades que el stock.
- NO escribas resúmenes del carrito ni totales: el sistema los agrega solo con los precios reales.
- "agregar" y "quitar": SOLO lo que el cliente pide en ESTE mensaje (lo anterior ya está en ESTADO.carrito; no lo repitas).
- Proceso: agregá lo que pide y preguntá si quiere algo más. Cuando termina, pedí confirmación o cambios. Con la confirmación pedí de a un dato: nombre, {entrega}, teléfono y medio de pago (solo los de la ficha). "confirmado": true SOLO si el cliente confirmó explícitamente el pedido completo.
Respondé SOLO JSON: {{"respuesta":"...","agregar":[{{"indice":0,"cantidad":1}}],"quitar":[0],"cliente":{{"nombre":"","direccion":"","contacto":""}},"cuando":"","pago":"","confirmado":false}}
Usá índices del catálogo. Omití campos vacíos."""


def _precios_ok(texto: str, d: dict, e: dict) -> bool:
    """Anti-alucinación: todo precio que mencione la IA debe existir (catálogo, subtotales, total o info del negocio)."""
    vistos = {int(x.replace(".", "")) for x in re.findall(r"\$\s?(\d{1,3}(?:\.\d{3})+|\d+)", texto)}
    if not vistos:
        return True
    ok = {it["precio"] for it in d["items"]}
    ok |= {d["items"][int(k)]["precio"] * c for k, c in e["carrito"].items() if int(k) < len(d["items"])}
    ok.add(resumen(d, e)[1])
    info = " ".join(str(v) for v in (d.get("info") or {}).values())
    ok |= {int(x.replace(".", "")) for x in re.findall(r"(\d{1,3}(?:\.\d{3})+|\d+)", info)}
    return vistos <= ok


async def vendedor_ia(d, bp, pagos, e, texto, historia, cred) -> tuple[str, dict] | None:
    """Devuelve (respuesta, estado_nuevo) o None si no hay IA, falla, o la respuesta no pasa los controles."""
    from . import ia
    if not cred or not ia.cupo_disponible():
        return None
    turnos = bp["modo"] == "turnos"
    hoy = datetime.now()
    estado = {"hoy": hoy.strftime("%a %Y-%m-%d %H:%M"), "carrito": {d["items"][int(k)]["nombre"]: c for k, c in e["carrito"].items()
              if int(k) < len(d["items"])}, "cliente": e["cliente"], "cuando": e.get("cuando"), "pago": e.get("pago"),
              "faltan": faltantes(e, bp["modo"], pagos)}
    msgs = [{"role": "system", "content": SYSTEM.format(entrega="día y hora (YYYY-MM-DD HH:MM en 'cuando')" if turnos else "dirección o si retira")},
            {"role": "system", "content": "FICHA:\n" + ficha(d, bp, pagos)}]      # fijo -> cacheado
    msgs += ia.historia_json(historia[-6:])
    msgs += [{"role": "system", "content": "ESTADO:" + json.dumps(estado, ensure_ascii=False, separators=(",", ":"))},
             {"role": "user", "content": texto[:500]}]
    try:
        out = await ia.chat_json(cred, msgs, max_tokens=300, temperature=0.3)
    except Exception as ex:
        log.warning("IA (vendedor) falló, uso reglas: %s", ex)
        return None
    e2 = json.loads(json.dumps(e))  # se aplica sobre una copia: solo se acepta si pasa los controles
    avisos = []
    cierre = bool(NADA_MAS.search(norm(texto)) or SI.search(texto)) and not re.search(r"\d+\s+\w", texto)
    if cierre or e.get("paso") == "datos":
        out["agregar"], out["quitar"] = [], []  # en mensajes de cierre o de datos no se tocan productos
    for q in out.get("quitar") or []:
        e2["carrito"].pop(str(q), None)
    for a in out.get("agregar") or []:
        try:
            i, c = int(a["indice"]), max(1, min(50, int(a.get("cantidad", 1))))
        except (KeyError, ValueError, TypeError):
            continue
        if not 0 <= i < len(d["items"]):
            continue
        it = d["items"][i]
        if not disponible(it):
            avisos.append(f"⚠️ {it['nombre']} está agotado.")
            continue
        if turnos:
            e2["carrito"] = {str(i): 1}
            continue
        nueva = e2["carrito"].get(str(i), 0) + c
        if it.get("stock") is not None and nueva > int(it["stock"]):
            nueva = int(it["stock"])
            avisos.append(f"⚠️ De {it['nombre']} solo quedan {it['stock']}.")
        e2["carrito"][str(i)] = nueva
    for k in ("nombre", "direccion", "contacto"):
        v = (out.get("cliente") or {}).get(k)
        if isinstance(v, str) and v.strip():
            e2["cliente"][k] = v.strip()[:120]
    if turnos and out.get("cuando"):
        try:
            datetime.strptime(str(out["cuando"]), "%Y-%m-%d %H:%M")
            e2["cuando"] = str(out["cuando"])
        except ValueError:
            pass
    if out.get("pago") in pagos:
        e2["pago"] = out["pago"]
    resp = str(out.get("respuesta") or "").strip()
    resp = re.split(r"\n\s*(?:🛒|Llevás|Te resumo|Total parcial)", resp)[0].strip()  # el resumen lo pone el servidor
    if not resp or not _precios_ok(resp, d, e2):
        log.warning("Respuesta de IA descartada (vacía o con precios inexistentes): %r", resp[:200])
        return None
    termina = bool(NADA_MAS.search(norm(texto))) and e.get("paso") != "confirmar"
    if e2["carrito"] and not e.get("resumen_ok") and (termina or (out.get("confirmado") and e2["carrito"] == e["carrito"])):
        # el cliente SIEMPRE ve el resumen con el total real y confirma antes de pedirle datos
        r, tot = resumen(d, e2)
        e2.update(paso="confirmar", resumen_ok=True)
        return (f"Te resumo {'la reserva' if turnos else 'el pedido'} 📝\n{r}\n**Total: {fmt(tot)}**\n\n"
                "¿Te lo confirmo o querés cambiar algo?"), e2
    if e2["carrito"] != e["carrito"]:
        e2["resumen_ok"] = False
        e2["paso"] = "comprando"  # cambió el pedido: hay que volver a mostrar el resumen y confirmar
    if e2.get("resumen_ok") and e.get("paso") in ("confirmar", "datos"):
        _completar_datos(e2, bp, pagos, texto)  # respaldo del servidor por si la IA no extrajo algún dato
    if e.get("paso") == "confirmar" and SI.search(texto):
        e2["paso"] = "datos"  # confirmó el resumen: ahora se piden los datos
    if (out.get("confirmado") and e2.get("resumen_ok")) or \
            (e2.get("paso") == "datos" and e2.get("resumen_ok") and not faltantes(e2, bp["modo"], pagos)):
        e2["paso"] = "final"  # ya confirmó el pedido y están todos los datos: se crea sin volver a preguntar
    elif e2["carrito"] != e["carrito"]:
        r, tot = resumen(d, e2)
        resp += f"\n\n🛒 Llevás:\n{r}\nTotal parcial: **{fmt(tot)}**" if r else ""
    if avisos:
        resp = " ".join(avisos) + "\n" + resp
    return resp, e2


async def responder(d, bp, pagos, e, texto, historia, cred=None) -> tuple[str, str]:
    """Devuelve (respuesta, proveedor). Si el pedido queda listo para crear, e['paso'] == 'final'."""
    res = await vendedor_ia(d, bp, pagos, e, texto, historia, cred)
    if res is not None:
        resp, e2 = res
        e.clear()
        e.update(e2)
        return resp, cred["proveedor"]
    resp = vendedor_simulado(d, bp, pagos, e, texto)
    if e["paso"] == "datos" and not faltantes(e, bp["modo"], pagos):
        e["paso"] = "final"
    if e.pop("_aviso", None):
        resp = "No pude entender la fecha 🤔 " + resp
    return resp, "simulado"
