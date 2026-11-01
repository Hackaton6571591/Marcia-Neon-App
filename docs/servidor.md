# Servidor

| Dato | Valor |
|---|---|
| Host | `vps-6571591-x` |
| SO | Ubuntu 24.04.5 LTS |
| IPv4 | `66.97.32.220` |
| IPv6 | `2800:6c0:3::2e1` |
| Dominio | `dwday-38964763.online` (asignado por DonWeb; falta zona DNS, ver `deploy.md`) |
| Vista previa | https://66-97-32-220.sslip.io |

## Usuario del proyecto
- Usuario: `hackaton` (uid 1000), con home `/home/hackaton`.
- **Sin sudo** y sin contraseña. No se copiaron claves SSH de root.
- Repo local: `/home/hackaton/creador-ia`.

## Software al inicio
Al inicio: solo `git` y `python3`. Instalado después: `python3-venv`, `python3-pip`, `caddy` (ver `bitacora.md`).

## Servicios
- `caddy` (reverse proxy + HTTPS) y `marcia` (app). Detalle en `deploy.md`.

## Pendiente
- Acceso SSH para `hackaton` (agregar clave pública a `~/.ssh/authorized_keys`).
- Zona DNS del dominio en DonWeb.
