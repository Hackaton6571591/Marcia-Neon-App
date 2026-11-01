"""Integración con Mercado Pago (Checkout Pro), lista para activar.

Se activa sola si existe MERCADOPAGO_ACCESS_TOKEN en .env. Sin token, la tienda muestra el
link/alias manual que cargó el negocio en su panel (modo demo de la hackatón).

Flujo con token:
1. Al confirmar un pedido con pago "mercadopago" se crea una *preferencia* (POST /checkout/preferences).
2. El cliente es redirigido a `init_point` (checkout de Mercado Pago).
3. Mercado Pago notifica a /api/mp/webhook; consultamos el pago (GET /v1/payments/{id}) y si está
   `approved` marcamos el pedido como `pagado`. Nunca se confía en el contenido del webhook: siempre se re-consulta.
"""
import logging
import os

import httpx

log = logging.getLogger("marcia.mp")
API = "https://api.mercadopago.com"


def activo() -> bool:
    return bool(os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip())


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.getenv('MERCADOPAGO_ACCESS_TOKEN', '').strip()}"}


async def crear_preferencia(pedido_id: int, negocio: str, detalle: list[dict], base_url: str, slug: str) -> str | None:
    """Devuelve la URL de pago (init_point) o None si falla o no está configurado."""
    if not activo():
        return None
    body = {
        "items": [{"title": f"{x['nombre']} ({negocio})"[:250], "quantity": int(x["cantidad"]),
                   "unit_price": float(x["precio"]), "currency_id": "ARS"} for x in detalle],
        "external_reference": str(pedido_id),
        "statement_descriptor": negocio[:22],
        "back_urls": {k: f"{base_url}/n/{slug}?pago={k}&pedido={pedido_id}" for k in ("success", "failure", "pending")},
        "auto_return": "approved",
        "notification_url": f"{base_url}/api/mp/webhook",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{API}/checkout/preferences", json=body, headers=_headers())
            r.raise_for_status()
            j = r.json()
        # con credenciales de prueba conviene usar sandbox_init_point
        return j.get("sandbox_init_point") if os.getenv("MERCADOPAGO_SANDBOX") == "1" else j.get("init_point")
    except Exception as ex:
        log.warning("Mercado Pago: no se pudo crear la preferencia: %s", ex)
        return None


async def consultar_pago(payment_id: str) -> tuple[str | None, str | None]:
    """Devuelve (status, external_reference) consultando la API (fuente de verdad)."""
    if not activo() or not payment_id.isdigit():
        return None, None
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{API}/v1/payments/{payment_id}", headers=_headers())
            r.raise_for_status()
            j = r.json()
        return j.get("status"), j.get("external_reference")
    except Exception as ex:
        log.warning("Mercado Pago: no se pudo consultar el pago %s: %s", payment_id, ex)
        return None, None
