"""Cliente de IA único (APIs compatibles con OpenAI: DeepSeek, OpenAI).

- Credenciales: las propias del negocio (Panel → Integraciones → IA) o, si no tiene, las de la plataforma (.env).
- Modo económico: modelo más barato por defecto (deepseek-chat), temperatura baja, pocos tokens de salida.
- Caché de contexto de DeepSeek: los mensajes fijos (reglas + ficha del negocio) van PRIMERO y no cambian entre
  turnos; así DeepSeek cobra esa parte como "cache hit", bastante más barata.
"""
import json
import logging
import os

import httpx

log = logging.getLogger("marcia.ia")

# Tope diario de tokens de la clave de la PLATAFORMA (protege el saldo de la demo). Al superarlo: modo reglas.
_uso = {"dia": None, "tokens": 0}


def cupo_disponible() -> bool:
    from datetime import date
    if _uso["dia"] != date.today():
        _uso.update(dia=date.today(), tokens=0)
    return _uso["tokens"] < int(os.getenv("IA_TOPE_TOKENS_DIA", "400000"))


def _sumar(tokens: int):
    cupo_disponible()
    _uso["tokens"] += tokens

PROVEEDORES = {
    "deepseek": {"url": "https://api.deepseek.com/chat/completions", "modelo": "deepseek-chat"},
    "openai": {"url": "https://api.openai.com/v1/chat/completions", "modelo": "gpt-4o-mini"},
}


def credenciales(propias: dict | None = None) -> dict | None:
    """Devuelve {proveedor, api_key, modelo, url, origen} o None si no hay IA disponible."""
    if os.getenv("IA_PROVIDER", "deepseek") == "simulado":
        return None
    if propias and propias.get("api_key") and propias.get("proveedor") in PROVEEDORES:
        p = PROVEEDORES[propias["proveedor"]]
        return {"proveedor": propias["proveedor"], "api_key": propias["api_key"],
                "modelo": propias.get("modelo") or p["modelo"], "url": p["url"], "origen": "negocio"}
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return None
    return {"proveedor": "deepseek", "api_key": key, "modelo": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "url": PROVEEDORES["deepseek"]["url"], "origen": "plataforma"}


def historia_json(historia: list[dict]) -> list[dict]:
    """Las respuestas previas del asistente se pasan en el MISMO formato JSON que se le pide al modelo.
    Si van como texto plano, DeepSeek en modo JSON a veces devuelve contenido vacío."""
    return [{"role": h["role"], "content": json.dumps({"respuesta": h["content"]}, ensure_ascii=False)}
            if h["role"] == "assistant" else h for h in historia]


async def chat_json(cred: dict, messages: list[dict], max_tokens: int = 400, temperature: float = 0.3,
                    timeout: float = 25) -> dict:
    """Llama al modelo pidiendo JSON (1 reintento si viene vacío). Lanza excepción si falla."""
    try:
        return await _chat_json(cred, messages, max_tokens, temperature, timeout)
    except json.JSONDecodeError:
        return await _chat_json(cred, messages, max_tokens, min(1.0, temperature + 0.3), timeout)


async def _chat_json(cred, messages, max_tokens, temperature, timeout) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(cred["url"], headers={"Authorization": f"Bearer {cred['api_key']}"},
                         json={"model": cred["modelo"], "messages": messages, "max_tokens": max_tokens,
                               "temperature": temperature, "response_format": {"type": "json_object"}})
        r.raise_for_status()
        j = r.json()
    u = j.get("usage") or {}
    if cred.get("origen") == "plataforma":
        _sumar(int(u.get("total_tokens") or 0))
    log.info("IA %s/%s (%s) tokens in=%s (cache %s) out=%s", cred["proveedor"], cred["modelo"], cred["origen"],
             u.get("prompt_tokens"), u.get("prompt_cache_hit_tokens", "-"), u.get("completion_tokens"))
    raw = j["choices"][0]["message"]["content"] or ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("JSON inválido de la IA: %r", raw[:400])
        raise


async def probar(cred: dict) -> str | None:
    """Prueba barata de una clave (1 token). Devuelve None si anda o el mensaje de error."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(cred["url"], headers={"Authorization": f"Bearer {cred['api_key']}"},
                             json={"model": cred["modelo"], "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1})
        if r.status_code == 401:
            return "La clave no es válida."
        if r.status_code == 402:
            return "La cuenta no tiene saldo."
        if r.status_code >= 400:
            return f"El proveedor respondió con error {r.status_code}."
        return None
    except Exception:
        return "No se pudo conectar con el proveedor."
