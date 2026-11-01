# Visión del producto: Marcia Neon para una pizzería (caso guía)

> Definida por el equipo el 2026-11-01. Es el norte del producto; el MVP de la hackatón implementa una parte.

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
| Copiar menú desde URL con IA | 🔜 (placeholder en panel) |
| Chatbot de pedidos conversacional en la tienda | 🔜 (DeepSeek / Claude / ChatGPT) |
| WhatsApp Business API | 🔜 (placeholder en panel) |
| CRM de clientes (historial, recompra) | 🔜 |

## Activar Mercado Pago (cuando se quiera)
En `/home/hackaton/creador-ia/.env`:
```
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...   # o TEST-... con MERCADOPAGO_SANDBOX=1
BASE_URL=https://dwday-38964763.online
```
`sudo systemctl restart marcia`. `/salud` muestra `"mercadopago": "checkout"`. El webhook es `POST /api/mp/webhook`: siempre re-consulta el pago a la API de MP antes de marcar el pedido como pagado. Código en `app/mercadopago.py`.

**Limitación actual:** el token es único para toda la plataforma. Para que cada negocio cobre en su propia cuenta, el paso siguiente es **OAuth de Mercado Pago (marketplace)** por negocio.
