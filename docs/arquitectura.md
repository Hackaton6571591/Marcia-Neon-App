# Arquitectura y stack

## Recursos del server (relevados 2026-11-01)
- 2 vCPU, 3.8 GB RAM, 22 GB de disco libres, Ubuntu 24.04, Python 3.12.
- Puertos 80/443 libres (en uso: 22, 25, 5583).

## Decisión: Python + FastAPI + SQLite + Caddy
**Por qué esto y no Next.js:**
- Python ya está instalado; no hace falta sumar Node ni un paso de build.
- Next.js consume bastante RAM al compilar y en ejecución; con 4 GB y todo en la misma máquina conviene algo liviano.
- FastAPI maneja bien llamadas async a la API de DeepSeek (el cuello de botella real).
- SQLite alcanza para una demo de hackatón, sin servicio extra. Un solo archivo, fácil de respaldar.
- Caddy da HTTPS automático (Let's Encrypt) con 3 líneas de config, apenas tengamos el dominio.
- Sin Docker: menos consumo y menos piezas. Se ejecuta con `systemd`.

## Piezas
| Capa | Tecnología |
|---|---|
| Backend / API | FastAPI + Uvicorn |
| Frontend | HTML + JS, plantillas Jinja2 (sin build) |
| Base de datos | SQLite (multi-negocio con columna `negocio_id`) |
| IA | DeepSeek vía API (httpx), clave en `.env` |
| Proxy / HTTPS | Caddy (pendiente: instalar con el dominio) |
| Proceso | systemd, usuario `hackaton` |

## Entorno
- Virtualenv en `/home/hackaton/creador-ia/.venv` (fuera del repo vía `.gitignore`).
- Dependencias: `fastapi`, `uvicorn[standard]`, `httpx`, `jinja2`, `python-multipart`.

## Criterio: máxima optimización (decidido 2026-11-01)
DonWeb no impone stack, así que se prioriza rendimiento y bajo consumo en 2 vCPU / 4 GB.

- **Un solo proceso Uvicorn** (1–2 workers) detrás de Caddy; la carga es I/O (API de IA), no CPU.
- **Respuestas de IA en streaming (SSE)**: el usuario ve texto al instante, sin esperar la respuesta completa.
- **SQLite en modo WAL** (`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`) con índices por `negocio_id`.
- **Frontend sin framework ni build**: HTML + CSS + JS nativo (htmx opcional). Páginas de pocos KB.
- **Caddy** con compresión (zstd/gzip), HTTP/2-3 y caché de estáticos.
- **IA económica**: DeepSeek con prompts cortos, `temperature` baja para extracción JSON y caché de respuestas repetidas (FAQ del negocio).
- **Sin Docker, sin Node, sin servicios extra**: solo `systemd`.
- Límite de tasa por IP en el chat para proteger el costo de la API.
