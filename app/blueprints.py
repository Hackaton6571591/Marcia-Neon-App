"""Blueprints por rubro: qué solución corresponde a cada tipo de negocio."""

BLUEPRINTS = {
    "restaurante": {
        "nombre": "Restaurante / Rotisería",
        "emoji": "🍕",
        "modo": "pedidos",
        "sinonimos": ["restaurante", "resto", "pizzeria", "pizza", "rotiseria", "hamburgues", "bar", "delivery",
                      "comida", "empanada", "sushi", "cafeteria", "cafe", "heladeria", "panaderia", "parrilla"],
        "item": "producto",
        "pregunta_oferta": "Pasame tu menú con precios, como lo tengas. Ej: *Muzzarella 8000, Napolitana 9500, Fugazzeta 9000*",
        "demo": "Muzzarella 8000\nNapolitana 9500\nFugazzeta 9000",
    },
    "turnos": {
        "nombre": "Peluquería / Consultorio / Estética",
        "emoji": "💇",
        "modo": "turnos",
        "sinonimos": ["peluqueria", "pelu", "barberia", "barber", "consultorio", "medico", "dentista", "odontolog",
                      "estetica", "manicura", "uñas", "spa", "masaje", "kinesio", "psicolog", "nutricion", "veterinaria",
                      "tatuaje", "gimnasio", "clases", "turno"],
        "item": "servicio",
        "pregunta_oferta": "¿Qué servicios ofrecés, con precio y duración? Ej: *Corte 6000 30min, Color 15000 90min, Barba 4000 20min*",
        "demo": "Corte 6000 30min\nColor 15000 90min\nBarba 4000 20min",
    },
    "comercio": {
        "nombre": "Comercio / Tienda",
        "emoji": "🛍️",
        "modo": "pedidos",
        "sinonimos": ["ferreteria", "almacen", "kiosco", "comercio", "tienda", "negocio", "libreria", "farmacia",
                      "verduleria", "carniceria", "dietetica", "pintureria", "corralon", "bazar", "local", "venta",
                      "ropa", "indumentaria", "lenceria", "zapateria", "calzado", "jugueteria", "cosmetica", "perfumeria",
                      "regaleria", "accesorios", "joyeria", "optica", "electronica", "celulares", "mascotas", "vivero"],
        "item": "producto",
        "pregunta_oferta": "Pasame algunos productos con precio. Ej: *Martillo 12000, Caja de tornillos 3500, Cinta aisladora 1500*",
        "demo": "Martillo 12000\nCaja de tornillos 3500\nCinta aisladora 1500",
    },
}

ALIAS_CHIPS = {"restaurante": "restaurante", "peluqueria": "turnos", "consultorio": "turnos",
               "ferreteria": "comercio", "otro": None}


def detectar_blueprint(texto: str) -> str | None:
    t = _norm(texto)
    for bid, bp in BLUEPRINTS.items():
        if any(s in t for s in bp["sinonimos"]):
            return bid
    return None


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")
