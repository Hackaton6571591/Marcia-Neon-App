# Google Calendar (API oficial, tiempo real)

**Decisión:** la base de datos propia es la fuente de verdad de la agenda (rápida y funciona aunque Google no responda). Encima, cada negocio puede **conectar su Google Calendar** con OAuth:

| Qué pasa | Cómo |
|---|---|
| Se reserva un turno → **evento en su Google Calendar** al instante | `POST /calendars/primary/events` (`app/gcal.py: crear_evento`) |
| Se cancela un turno (cliente o panel) → **se borra el evento** | `DELETE /calendars/primary/events/{id}` |
| El negocio tiene algo ocupado en su calendario → **ese horario se bloquea** en la agenda online | `POST /freeBusy` (cache 60 s; se suma a la ocupación propia) |

El feed `.ics` sigue disponible como opción simple, pero Google refresca las suscripciones cada varias horas (no sirve para tiempo real).

## Activarlo (administrador de la plataforma, ~10 minutos)
1. Entrá a **https://console.cloud.google.com** → creá un proyecto (ej. "Marcia Neon").
2. **APIs y servicios → Biblioteca** → habilitá **Google Calendar API**.
3. **Pantalla de consentimiento de OAuth** → tipo *Externo* → nombre de la app, email de soporte → scopes: `calendar.events`, `calendar.freebusy`, `userinfo.email`. En modo *Testing*, agregá como *usuarios de prueba* las cuentas de Google de los negocios (hasta 100). Para producción hay que enviar la app a verificación de Google.
4. **Credenciales → Crear credenciales → ID de cliente de OAuth** → tipo *Aplicación web* → URI de redireccionamiento autorizado:
   `https://<tu-dominio>/oauth/google/callback` (ej. `https://dwday-38964763.online/oauth/google/callback`).
5. En `/home/hackaton/creador-ia/.env` (nunca al repo):
   ```
   GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=xxxxx
   BASE_URL=https://<tu-dominio>
   ```
6. `sudo deploy/reiniciar.sh`.

## Para cada negocio
Panel → 🔌 Integraciones → **🗓️ Google Calendar en tiempo real** → **Conectar con Google Calendar** → elegir la cuenta y aceptar. Listo: muestra "✅ Conectado con tu@email". Se puede desconectar cuando quieras.

## Seguridad
- El `state` de OAuth va firmado con HMAC (clave privada del negocio): no se puede conectar un calendario a un negocio ajeno (probado: state falso → 400).
- El *refresh token* se guarda en la tabla `google`, separada de los datos públicos; nunca se envía al navegador.
- Si Google falla, se usa solo la agenda propia (los turnos se siguen tomando).
