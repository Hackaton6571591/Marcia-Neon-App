# Vendedor virtual (chatbot de la tienda)

Cada tienda publicada (`/n/{slug}`) tiene un **vendedor virtual** integrado al catálogo: responde dudas y **arma el pedido conversando**, como un vendedor del local.

## Experiencia
- Se abre desde el botón flotante **"💬 Pedí por chat"** o desde el buscador de la portada. En celular, a pantalla completa.
- Respuestas rápidas sugeridas según el momento (ver menú, envío, pagos, confirmar, cambiar).
- **Integrado al catálogo:** lo que se agrega en el chat aparece en los contadores +/− de la tienda y en el total de la barra inferior.
- Si el cliente comparte datos, los recuerda durante la sesión (un segundo pedido no vuelve a pedir el nombre).

## Proceso de venta (siempre el mismo)
1. El cliente pide o pregunta → el vendedor agrega productos y pregunta **"¿algo más?"**.
2. Cuando termina → **resumen con total** y **"¿lo confirmo o querés cambiar algo?"**.
3. Confirmado → pide de a uno: **nombre**, **dirección o retiro** (o día y hora para turnos), **teléfono/WhatsApp**, **medio de pago**.
4. Crea el pedido (aparece en el panel) y responde con número, detalle, total e instrucciones de pago.

## Qué sabe
- Catálogo con precios y categorías, horarios, teléfono, medios de pago.
- Lo que el negocio carga en **Panel → Vendedor virtual**: costo y zona de envío, demora, condiciones de venta, preguntas frecuentes.
- Si algo no está cargado, dice que el local lo confirma. **Nunca inventa** precios ni condiciones.

## IA
| Modo | Cuándo | Cómo |
|---|---|---|
| **DeepSeek** | `DEEPSEEK_API_KEY` en `.env` | Conversación natural. Recibe la ficha del negocio + el estado del pedido y devuelve JSON con acciones (`agregar`, `quitar`, `cliente`, `pago`, `cuando`, `confirmado`). |
| **Reglas** | sin clave o si DeepSeek falla | Entiende pedidos con cantidades ("2 porciones de muzza y 1 de fugazzeta", "media docena"), contexto (la 2da también es porción), preguntas ("¿tenés empanadas de carne?" → "sí, ¿cuántas?" → "3"), "me olvidé de algo", "sacá la coca", "quiero cambiar algo", envíos, pagos, horarios. |

**Seguridad:** la IA solo propone acciones. El servidor valida índices y cantidades, **calcula precios y totales** con el catálogo guardado y crea el pedido solo si el cliente confirmó y están todos los datos. Turnos: misma validación de superposición que el formulario. Límite: 30 mensajes/min por IP, 60 por charla.

## Activar DeepSeek (la clave NUNCA va al repo)
Por SSH en el server (no pegarla en chats):
```bash
sudo nano /home/hackaton/creador-ia/.env     # DEEPSEEK_API_KEY=sk-...
sudo systemctl restart marcia
curl https://66-97-32-220.sslip.io/salud     # → "ia":"deepseek"
```
`.env` está en `.gitignore`, con permisos 600. Antes de cada push se corre una búsqueda de patrones de claves.

## API
`POST /api/n/{slug}/chat` `{chat?, texto}` → `{chat, respuesta, ia, carrito, total, paso, pedido}`. `paso`: `comprando` · `confirmar` · `datos` · `hecho`.

## Probado (2026-11-01, modo reglas)
"hola, tenés empanadas de carne" → "3" → "me olvidé de pedir algo" → "una coca" → "¿hacen envíos?" → "eso es todo" → "quiero cambiar algo" → "sacá la coca" → "sumá 2 empanadas de pollo" → confirmar → nombre → retiro → teléfono → efectivo → **pedido #7 creado** con total correcto.
