# Bitácora

Registro cronológico. Cada acción relevante se agrega acá.

## 2026-11-01
- Se relevó el server: Ubuntu 24.04, solo `git` y `python3`.
- Se definió la idea: creador de soluciones con IA para negocios locales (ver `idea-y-evaluacion.md`).
- Se creó el usuario `hackaton` (sin sudo) con `useradd -m -s /bin/bash hackaton`.
- Se creó el repo git local `/home/hackaton/creador-ia` (rama `main`) con `README.md` y `docs/`.
- Pendiente: desafío completo de DonWeb, dominio, stack, repo público en GitHub.
- Se relevaron recursos del server (2 vCPU, 3.8 GB RAM, 22 GB libres) y se eligió el stack: Python + FastAPI + SQLite + Caddy. Ver `arquitectura.md`.
- Se instalaron como root `python3-venv` y `python3-pip` (apt).
- Como `hackaton`, se creó `.venv` y se instalaron `fastapi`, `uvicorn[standard]`, `httpx`, `jinja2`, `python-multipart`.
- Se agregó `.gitignore` (`.venv/`, `.env`, `*.db`, `__pycache__/`).
- Se confirmó que DonWeb no impone stack. Se documentó el criterio de máxima optimización en `arquitectura.md` (streaming SSE, SQLite WAL, frontend sin build, Caddy con compresión, rate limit).
- Repo privado en GitHub: `Hackaton6571591/Marcia-Neon-App` (se pasa a público antes de la entrega, tras revisar el historial en busca de secretos).
- Se generó una deploy key ed25519 para `hackaton` (`~/.ssh/deploy_marcia_neon`, sin passphrase, permisos 600). Solo la clave pública se comparte. Se configuró `~/.ssh/config` y `known_hosts` (huella de GitHub verificada).
- Se configuró `origin` = `git@github.com:Hackaton6571591/Marcia-Neon-App.git`. Pendiente: que se cargue la deploy key en GitHub y hacer el primer push.
- Deploy key cargada en GitHub (huella mctLeY6w…Mlq4 verificada, acceso read/write). Primer commit y push a `main`.
