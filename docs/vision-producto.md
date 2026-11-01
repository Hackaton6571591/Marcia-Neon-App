# Visión del producto: Marcia Neon para una pizzería (caso guía)

> Definida por el equipo el 2026-11-01. Es el norte del producto; el MVP de la hackatón implementa una parte.

## Dos modelos, nada más (decisión del equipo)
| Modelo | Rubros | Qué se despliega |
|---|---|---|
| **Productos físicos** | restaurante, rotisería, ferretería, almacén, comercio… | El **mismo** ecommerce: tienda + carrito + checkout + panel de pedidos. Solo cambia el catálogo. |
| **Servicios = turnos** | peluquería, consultorio, estética… | Un **banco de tiempo**: servicios con duración, reserva de franjas sin superposición, **integración con la agenda** del negocio. |

En el código: blueprints `restaurante` y `comercio` → modo `pedidos`; blueprint `turnos` → modo `turnos`.

## Qué es
Una **solución de ecommerce simplificada y hecha a medida** para el negocio, creada por Marcia (IA) a partir de una charla.

- **Del lado del cliente final:** una tienda propia de la pizzería (catálogo, carrito, checkout con efectivo / Mercado Pago / transferencia) **con un chatbot integrado** que toma pedidos conversando: *"mandame 2 porciones de muzzarella, ¿y qué empanadas tenés?"*.
- **Del lado del negocio:** un panel web tipo **CRM + ecommerce**: pedidos, productos, medios de pago, clientes, e **integración por API con WhatsApp**.

## Flujo
1. Landing → "pizzería" → Marcia conversa y arma la base (rubro, problema, nombre, menú, horarios).
2. Se publica la tienda y se entrega el **panel de control**.
3. En el panel, el negocio carga productos: **a mano**, por **CSV** o pegando la **URL de su menú actual** (la IA lo copia).
4. Configura medios de pago: **efectivo** y **Mercado Pago** (y transferencia).
5. Sus clientes compran en la tienda o por el chatbot; los pedidos llegan al panel y a WhatsApp.

## Estado por funcionalidad
| Funcionalidad | Estado |
|---|---|
| Launcher conversacional (crea la base del negocio) | ✅ |
| Tienda pública con carrito y checkout | ✅ |
| Panel: pedidos/turnos, KPIs | ✅ |
| Panel: carga manual de productos | ✅ |
| Panel: importación CSV (coma, `;`, tab; con o sin encabezado) | ✅ |
| Medios de pago: efectivo, Mercado Pago (link/alias), transferencia | ✅ |
| Mercado Pago Checkout Pro + webhook "pagado" | ✅ código listo, **se activa pegando el access token** (no se usa en la hackatón) |
| Copiar menú desde URL (IA con DeepSeek, heurística sin clave), protegido contra SSRF | ✅ |
| Logo e imagen de portada desde la web o Instagram (launcher y panel) + subir logo | ✅ |
| Categorías de productos, tienda agrupada por sección, ilustraciones automáticas | ✅ |
| Porciones combinables + combos (caso pizzería) | ✅ |
| **Vendedor virtual** conversacional en la tienda, integrado al catálogo (ver `vendedor-virtual.md`) | ✅ (DeepSeek al cargar la clave; reglas mientras tanto) |
| Mercado Pago habilitado por defecto junto con efectivo | ✅ |
| Fotos reales de productos generadas con IA (ChatGPT/DALL·E) | 🔜 (requiere clave; hoy ilustraciones automáticas) |
| WhatsApp Business API | 🔜 (placeholder en panel) |
| Panel de pedidos en vivo con estados, pago, comanda por WhatsApp/email/impresión | ✅ |
| Webhook firmado (API) a sistemas de cocina/ERP/delivery | ✅ |
| Seguimiento del pedido en vivo para el cliente | ✅ |
| Importar productos de tiendas online (APIs JSON, Shopify, WooCommerce) con fotos | ✅ |
| Foto del menú → productos (DeepSeek visión) | ✅ |
| Logo desde Instagram vía Instagram Graph API oficial | 🔜 |
| Integraciones PedidosYa / Uber Eats / Rappi | 🔜 (ver panel → Integraciones) |
| CRM de clientes (historial, recompra) | 🔜 |
| Turnos: sin superposición (según duración del servicio), no se reserva en el pasado | ✅ |
| Turnos: la tienda muestra las franjas ocupadas del día elegido | ✅ |
| Agenda: feed iCalendar privado (Google Calendar / Apple / Outlook se suscriben) | ✅ |
| Agenda: sincronización bidireccional con Google Calendar API (bloquear horarios desde la agenda) | 🔜 |
| Turnos: franjas según horario de atención estructurado | 🔜 (hoy el horario es texto libre) |

## Activar Mercado Pago (cuando se quiera)
En `/home/hackaton/creador-ia/.env`:
```
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...   # o TEST-... con MERCADOPAGO_SANDBOX=1
BASE_URL=https://dwday-38964763.online
```
`sudo systemctl restart marcia`. `/salud` muestra `"mercadopago": "checkout"`. El webhook es `POST /api/mp/webhook`: siempre re-consulta el pago a la API de MP antes de marcar el pedido como pagado. Código en `app/mercadopago.py`.

**Limitación actual:** el token es único para toda la plataforma. Para que cada negocio cobre en su propia cuenta, el paso siguiente es **OAuth de Mercado Pago (marketplace)** por negocio.
