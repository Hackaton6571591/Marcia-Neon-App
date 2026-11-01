# Servidor

| Dato | Valor |
|---|---|
| Host | `vps-6571591-x` |
| SO | Ubuntu 24.04.5 LTS |
| IPv6 | `2800:6c0:3::2e1` |
| Dominio | pendiente (lo asigna DonWeb) |

## Usuario del proyecto
- Usuario: `hackaton` (uid 1000), con home `/home/hackaton`.
- **Sin sudo** y sin contraseña. No se copiaron claves SSH de root.
- Repo local: `/home/hackaton/creador-ia`.

## Software al inicio
Instalado: `git`, `python3`. Faltan: `gh`, docker, node/npm, nginx/caddy. Se instalan cuando se defina el stack (ver `bitacora.md`).

## Pendiente
- Acceso SSH para `hackaton` (agregar clave pública a `~/.ssh/authorized_keys`).
- Reverse proxy + HTTPS cuando llegue el dominio.
