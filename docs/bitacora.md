# Bitácora

Registro cronológico. Cada acción relevante se agrega acá.

## 2026-11-01
- Se relevó el server: Ubuntu 24.04, solo `git` y `python3`.
- Se definió la idea: creador de soluciones con IA para negocios locales (ver `idea-y-evaluacion.md`).
- Se creó el usuario `hackaton` (sin sudo) con `useradd -m -s /bin/bash hackaton`.
- Se creó el repo git local `/home/hackaton/creador-ia` (rama `main`) con `README.md` y `docs/`.
- Pendiente (en ese momento): desafío completo de DonWeb, dominio, stack, repo en GitHub.
- Se relevaron recursos del server (2 vCPU, 3.8 GB RAM, 22 GB libres) y se eligió el stack: Python + FastAPI + SQLite + Caddy. Ver `arquitectura.md`.
- Se instalaron como root `python3-venv` y `python3-pip` (apt).
- Como `hackaton`, se creó `.venv` y se instalaron `fastapi`, `uvicorn[standard]`, `httpx`, `jinja2`, `python-multipart`.
- Se agregó `.gitignore` (`.venv/`, `.env`, `*.db`, `__pycache__/`).
- Se confirmó que DonWeb no impone stack. Se documentó el criterio de máxima optimización en `arquitectura.md` (streaming SSE, SQLite WAL, frontend sin build, Caddy con compresión, rate limit).
- Repo privado en GitHub: `Hackaton6571591/Marcia-Neon-App` (se pasa a público antes de la entrega, tras revisar el historial en busca de secretos).
- Se generó una deploy key ed25519 para `hackaton` (`~/.ssh/deploy_marcia_neon`, sin passphrase, permisos 600). Solo la clave pública se comparte. Se configuró `~/.ssh/config` y `known_hosts` (huella de GitHub verificada).
- Se configuró `origin` = `git@github.com:Hackaton6571591/Marcia-Neon-App.git`. Pendiente: que se cargue la deploy key en GitHub y hacer el primer push.
- Deploy key cargada en GitHub (huella mctLeY6w…Mlq4 verificada, acceso read/write). Primer commit y push a `main`.
- Commit inicial `25f8aaa` subido a `origin/main`. Revisión de secretos sin coincidencias. Identidad git del repo: `hackaton@users.noreply.github.com` (para no exponer emails personales).
- El proyecto pasa a llamarse **Marcia Neon App** (repo `Marcia-Neon-App`). Se actualizó el README.
- Se diseñó la arquitectura de la landing y el launcher en `arquitectura-landing-launcher.md`: máquina de estados por etapas, blueprints JSON por rubro, capa de IA intercambiable (DeepSeek + simulado de respaldo), extractor JSON y respuesta en streaming en paralelo, eventos SSE, modelo de datos SQLite, API, estructura de carpetas y plan de construcción.
- Se construyó la **landing** (`app/static/index.html`, ~23 KB, sin dependencias): estética neon, chat animado de demo, secciones de problema, cómo funciona, rubros y CTA. Los rubros y el input llevan a `/crear?rubro=…&msg=…`.
- Backend mínimo FastAPI (`app/main.py`): `/salud`, `/crear` (placeholder del launcher con escape de HTML). Docs automáticas desactivadas.
- Se instaló **Caddy 2.6.2** (apt) como root. `/etc/caddy/Caddyfile` es symlink a `deploy/Caddyfile`. Se agregó `caddy` al grupo `hackaton` para leer `app/static`.
- Servicio systemd **`marcia`** (`deploy/marcia.service`): Uvicorn en `127.0.0.1:8000`, usuario `hackaton`, con sandbox.
- **Vista previa pública con HTTPS:** https://66-97-32-220.sslip.io. Verificado: landing 200, `/.env` 404, compresión zstd, HTTP/3.
- DonWeb asignó el dominio **`dwday-38964763.online`**. Diagnóstico: delegado a `ns1/ns2.donweb.com` pero sin zona DNS (SERVFAIL). Se documentaron los pasos oficiales de DonWeb para crearla en `deploy.md`. Caddy ya está configurado para el dominio y sacará el certificado solo cuando el DNS resuelva.
- ⏱️ Queda 1 hora: se prioriza el flujo de punta a punta.
- Se implementó el **launcher** (`app/launcher.py`, `app/blueprints.py`, `templates/crear.html`): máquina de estados, extracción con DeepSeek (JSON mode + validación) y fallback simulado por reglas, vista previa en vivo, publicar.
- Se implementó la **página pública del negocio** (`/n/{slug}`, pedidos o turnos con total calculado en servidor) y el **panel privado** (`/panel/{slug}?t=token`).
- Se creó `.env` (600) con `IA_PROVIDER=deepseek` y clave vacía → funciona en modo demo hasta cargar la key.
- Pruebas de punta a punta OK para restaurante y peluquería. Se corrigió: límites por endpoint, IP real desde el último `X-Forwarded-For`, texto de Marcia.
- DNS de `dwday-38964763.online` sigue sin zona (SERVFAIL). Detalle en `launcher.md`.
