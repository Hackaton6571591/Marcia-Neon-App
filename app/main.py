"""Marcia Neon App: punto de entrada FastAPI.

Etapa actual: landing (servida como estático por Caddy) + placeholder del launcher.
"""
from html import escape
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, FileResponse

BASE = Path(__file__).parent
app = FastAPI(title="Marcia Neon App", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/salud")
def salud():
    return {"ok": True}


@app.get("/", include_in_schema=False)
def landing():
    # En producción Caddy sirve este archivo directo; esto es respaldo para desarrollo local.
    return FileResponse(BASE / "static" / "index.html")


@app.get("/crear", response_class=HTMLResponse)
def crear(rubro: str = Query("", max_length=40), msg: str = Query("", max_length=200)):
    plantilla = (BASE / "templates" / "crear.html").read_text(encoding="utf-8")
    pedido = msg or rubro or "tu negocio"
    return plantilla.replace("{{pedido}}", escape(pedido))
