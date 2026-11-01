# Launcher: implementación (MVP)

Implementa el diseño de [arquitectura-landing-launcher.md](arquitectura-landing-launcher.md), recortado para entregar en tiempo de hackatón.

## Flujo de punta a punta
1. **Landing** (`/`) → el usuario escribe su rubro o toca un chip → `/crear?rubro=…` o `/crear?msg=…`.
2. **Launcher** (`/crear`): chat con Marcia a la izquierda y **vista previa en vivo** a la derecha, con barra de progreso por etapas. En celular, pestañas Chat / Vista previa.
3. **Publicar** → crea el negocio y devuelve dos links:
   - `/n/{slug}`: página pública del negocio (catálogo + pedido, o servicios + turno).
   - `/panel/{slug}?t={token}`: panel privado con pedidos/turnos, total facturado y autorefresco cada 20 s.
4. El cliente final hace un pedido o reserva en `/n/{slug}` → aparece en el panel.

## Etapas (máquina de estados, `app/launcher.py`)
`rubro → dolor → negocio → oferta → horarios → revision`. La etapa se **calcula** a partir de los datos que faltan; la IA no decide transiciones.

## IA
| Proveedor | Cuándo | Cómo |
|---|---|---|
| **DeepSeek** (`deepseek-chat`) | `DEEPSEEK_API_KEY` cargada en `.env` | Una llamada por mensaje con `response_format: json_object`. Devuelve `{respuesta, datos}`. Los `datos` pasan por `validar()`: solo campos conocidos y tipos correctos. |
| **Simulado** | sin clave, `IA_PROVIDER=simulado`, o si DeepSeek falla/timeout (25 s) | Reglas: detección de rubro por sinónimos, parser de precios (`$9.500`, `8k`, `8 mil`), duraciones (`30min`, `1h`), teléfono. |

Si DeepSeek responde pero no extrae nada en las etapas `rubro` u `oferta`, se usa el parser local como red de seguridad. El front muestra qué IA respondió ("IA: DeepSeek" / "IA: modo demo").

**Activar DeepSeek:** editar `/home/hackaton/creador-ia/.env` (permisos 600, fuera del repo):
```
IA_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
```
y `sudo systemctl restart marcia`. `/salud` informa qué IA está activa.

## Blueprints (`app/blueprints.py`)
| id | Rubros | Modo |
|---|---|---|
| `restaurante` | pizzería, rotisería, bar, delivery, café… | catálogo + pedidos |
| `turnos` | peluquería, barbería, consultorio, estética, veterinaria… | servicios + turnos |
| `comercio` | ferretería, almacén, kiosco, tienda… (y por defecto) | catálogo + pedidos |

## API
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/launcher/mensaje` | `{sesion?, texto}` → `{sesion, etapa, progreso, datos, respuesta, ia}` |
| GET | `/api/launcher/sesion/{id}` | estado + historia (para retomar al recargar) |
| POST | `/api/launcher/sesion/{id}/publicar` | → `{slug, url, url_panel}` (solo en etapa `revision`) |
| POST | `/api/n/{slug}/pedido` | `{cliente, contacto, items:{índice:cantidad}, cuando, nota}` → `{numero, total, detalle}` |
| GET | `/n/{slug}` | página pública del negocio |
| GET | `/panel/{slug}?t=` | panel privado (403 si el token no coincide; comparación en tiempo constante) |

## Datos (SQLite WAL, `data/marcia.db`, fuera del repo)
`sesiones(id, datos JSON, historia JSON, mensajes)`, `negocios(slug, datos JSON, token_admin)`, `pedidos(negocio_id, tipo, cliente, contacto, detalle JSON, total, cuando, nota, estado)`.
El **total del pedido se calcula en el servidor** con los precios guardados: el cliente no puede manipularlo.

## Seguridad
- Límites por IP (ventana de 1 min): 20 mensajes de chat, 10 publicaciones, 10 pedidos. 40 mensajes máx por sesión. IP tomada del último valor de `X-Forwarded-For` (lo agrega Caddy; no se puede falsear).
- Plantillas Jinja2 con autoescape; el chat escapa HTML antes de aplicar negritas/itálicas.
- La IA solo propone datos validados; publicar requiere clic del usuario.

## Probado (2026-11-01)
- Restaurante: 5 mensajes → revisión → publicar `/n/don-luigi` → pedido #1 (total $25.500 calculado en servidor) → visible en panel; panel con token inválido → 403.
- Peluquería: 5 mensajes → publicar `/n/estilo-neon` → turno #2 con fecha; turno sin fecha → 400.

## Panel del negocio (agregado)
Pestañas: **Pedidos** (KPIs, medio de pago, estado pagado) · **Productos** (edición manual, importación CSV, "copiar desde URL" próximamente) · **Medios de pago** (efectivo, Mercado Pago link/alias, transferencia) · **Integraciones** (WhatsApp, chatbot, MP Checkout: próximamente).

| Método | Ruta | Descripción |
|---|---|---|
| PUT | `/api/panel/{slug}/items?t=` | reemplaza productos/servicios (validados) |
| POST | `/api/panel/{slug}/csv?t=[&reemplazar=true]` | cuerpo = CSV. Columnas `nombre,precio[,duracion]` |
| PUT | `/api/panel/{slug}/pagos?t=` | `{efectivo, mercadopago, transferencia}` |
| POST | `/api/mp/webhook` | notificaciones de Mercado Pago (ver `vision-producto.md`) |

El cliente elige el medio de pago en la tienda; el servidor valida que esté habilitado. Probado: CSV con `;` y encabezado (3), CSV sin encabezado (1), edición manual, pagos, token inválido → 403, pago no habilitado → 400.

## Pendiente / siguiente
- Probar con la API key real de DeepSeek.
- Streaming SSE de la respuesta (hoy la respuesta llega completa).
- Cambiar estado de pedidos desde el panel; WhatsApp; avatar.
- Ver roadmap completo en [vision-producto.md](vision-producto.md).
