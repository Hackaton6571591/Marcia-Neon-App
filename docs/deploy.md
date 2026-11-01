# Deploy

## URLs
| URL | Estado | Uso |
|---|---|---|
| https://66-97-32-220.sslip.io | ✅ activa, HTTPS (Let's Encrypt) | Vista previa mientras se configura el DNS |
| https://dwday-38964763.online | ✅ activa, HTTPS (Let's Encrypt) | Dominio oficial de la hackatón |
| https://www.dwday-38964763.online | ✅ activa | Alias (CNAME) |
| http://66.97.32.220 | redirige a sslip.io | Acceso por IP |

**sslip.io** es un DNS público que resuelve `66-97-32-220.sslip.io` → `66.97.32.220`. Permite tener HTTPS real sin dominio propio. Cuando el dominio oficial funcione, se puede quitar del Caddyfile.

## Esquema
```
Internet → Caddy :80/:443 (TLS automático, zstd/gzip, HTTP/3)
             ├── /           → app/static/index.html   (archivo, sin Python)
             ├── /static/*   → app/static/*
             └── resto       → 127.0.0.1:8000 (Uvicorn, servicio "marcia", usuario hackaton)
```

## Piezas instaladas (como root)
| Pieza | Detalle |
|---|---|
| Caddy 2.6.2 | `apt install caddy`. Config: `/etc/caddy/Caddyfile` → **symlink** a `deploy/Caddyfile` del repo. Original guardado en `/etc/caddy/Caddyfile.orig`. |
| Permiso de lectura | `usermod -aG hackaton caddy`: Caddy lee `app/static`. `~/.ssh` (700) y `.env` (600) siguen inaccesibles para Caddy. |
| Servicio `marcia` | `deploy/marcia.service` copiado a `/etc/systemd/system/`. Uvicorn solo en `127.0.0.1:8000`, con sandbox systemd (`ProtectSystem=strict`, `ProtectHome=read-only`, escritura solo en `data/`). |

## Seguridad de la vista previa
- `root` de Caddy apunta **solo** a `app/static`. Código, `.env`, base de datos y `.git` no son accesibles (verificado: `/.env` → 404).
- Uvicorn no se expone a internet.
- `/docs` y `/openapi.json` de FastAPI están desactivados.
- Ninguna API key existe todavía. Cuando exista, irá en `.env` (permisos 600) y solo la lee el backend.
- Headers: `nosniff`, `X-Frame-Options DENY`, `Referrer-Policy`, sin header `Server`.

## Comandos útiles
```bash
# actualizar después de un git pull
sudo systemctl restart marcia          # backend
sudo systemctl reload caddy            # si cambió el Caddyfile
# estado y logs
systemctl status marcia caddy
journalctl -u marcia -f
journalctl -u caddy -f
```
Los cambios en `app/static/` se ven al instante, sin reiniciar nada.

## Vincular el dominio de DonWeb (pendiente, lo hace el equipo)

**Diagnóstico (2026-11-01):** el dominio `dwday-38964763.online` está registrado (30/10/2026) y delegado a `ns1.donweb.com` / `ns2.donweb.com`, pero esos nameservers responden SERVFAIL: **todavía no existe la zona DNS**. Hay que crearla.

Pasos según la [ayuda oficial de DonWeb](https://soporte.donweb.com/es/articles/15901641-dominios-y-zona-dns-gestionar-la-zona-dns-de-tu-dominio):
1. Entrar a **Mi cuenta** (micuenta.donweb.com) → **Mis Servicios → Dominios**.
2. Junto a `dwday-38964763.online`, **Gestionar**.
3. **Nameservers y Zona DNS** → **Crear zona DNS**.
4. En el registro **A**, poner la IP del VPS: **`66.97.32.220`** (no la IP temporal que sugiere DonWeb).
5. Revisar los registros generados y verificar/crear:

   | Tipo | Nombre | Valor |
   |---|---|---|
   | A | `dwday-38964763.online` | `66.97.32.220` |
   | A | `www.dwday-38964763.online` | `66.97.32.220` |
   | AAAA (opcional) | `dwday-38964763.online` | `2800:6c0:3::2e1` |

   Si se crean registros para `www` como CNAME al dominio raíz, también sirve. Borrar cualquier otro A de `@` o `www` que apunte a otra IP.
6. **Guardar**. La propagación tarda de minutos a 24 h. Se verifica en whatsmydns.net.

Cuando resuelva, Caddy saca el certificado HTTPS solo (no hay que tocar nada en el server).

## Dominio oficial activado (2026-11-01)
- En DonWeb se creó la zona DNS: `A dwday-38964763.online → 66.97.32.220` y `CNAME www → dwday-38964763.online`. Verificado en Google DNS, Cloudflare y en `ns1/ns2.donweb.com`.
- Caddy había quedado en espera de reintento (los intentos previos fallaron porque el dominio no existía y ZeroSSL respondía 429). Se reinició Caddy y obtuvo los certificados de **Let's Encrypt** para ambos nombres al instante.
- `BASE_URL=https://dwday-38964763.online` en `.env`: links de seguimiento, WhatsApp, webhooks de Mercado Pago y callback de Google usan el dominio oficial.
- **Si el certificado no se emite después de un cambio de DNS:** `sudo systemctl restart caddy` (fuerza un reintento inmediato).
