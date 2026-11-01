# Usar Marcia Neon con DeepSeek y sin DeepSeek

Marcia funciona **siempre**, con o sin IA. DeepSeek la hace más inteligente y flexible, pero ningún flujo depende de ella.

## Comparación rápida

| Función | Con DeepSeek | Sin DeepSeek |
|---|---|---|
| **Launcher** (armar la tienda charlando) | Igual que sin IA; además responde preguntas fuera del flujo ("¿esto cuesta plata?") de forma natural | Flujo guiado por etapas; las preguntas reciben respuestas preparadas y nunca se guardan como datos |
| **Cargar productos escribiendo** ("Muzza 8000, Napo 9500") | ✅ | ✅ (parser propio) |
| **Foto del menú / folleto → productos** | ✅ DeepSeek lee la imagen | ❌ Marcia avisa y pide los productos escritos o un CSV |
| **Copiar productos de una web** | ✅ Tiendanube/Shopify/WooCommerce y webs comunes (recorre categorías) | ✅ Tiendanube/Shopify/WooCommerce (datos estructurados); ❌ webs sin datos estructurados |
| **Vendedor virtual de la tienda** | Conversación natural: recomienda, compara, entiende frases complejas, muestra productos con foto | Vendedor por reglas: entiende pedidos con cantidades, "sacá…", "sumá…", envíos, pagos, horarios, y cierra la venta |
| **Turnero** (horarios libres, reservar) | ✅ (lo resuelve el servidor) | ✅ idéntico (no usa IA) |
| **Asistente de logos** | Colores y lema sugeridos por IA | 4 logos con colores según el rubro, sin lema |
| **Panel, pedidos, stock, pagos, Google Calendar, compartir, QR** | ✅ | ✅ (no usan IA) |

## 1. Usarlo con DeepSeek (IA incluida para todos los negocios)

Quien administra el servidor carga **una clave de la plataforma** y todos los negocios la usan.

### Cómo sacar la API key de DeepSeek
1. Entrá a **https://platform.deepseek.com** y creá una cuenta (email o Google).
2. **Top up** → cargá saldo. Marcia usa el modelo más barato (`deepseek-chat`); con pocos dólares alcanza para miles de conversaciones (un mensaje del vendedor ≈ 1.200 tokens de entrada, la mayoría en caché, y ~50 de salida).
3. **API keys → Create new API key** → copiá la clave que empieza con `sk-`. Se muestra **una sola vez**.

### Cómo integrarla en el servidor
En `/home/hackaton/creador-ia/.env` (permisos 600; **nunca se sube al repo**, está en `.gitignore`):
```
IA_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-chat
IA_TOPE_TOKENS_DIA=400000      # tope diario para cuidar el saldo
```
Aplicar y verificar:
```bash
sudo /home/hackaton/creador-ia/deploy/reiniciar.sh
curl https://dwday-38964763.online/salud      # → "ia":"deepseek"
```
La etiqueta del launcher pasa a decir **"IA: DeepSeek"** y el vendedor muestra "IA DeepSeek" en su cabecera.

## 2. Cada negocio con su propia API key

Un negocio puede usar **su cuenta de DeepSeek** (o de OpenAI) en vez de la incluida:
1. Saca su API key (pasos de arriba).
2. Entra a su **panel** (con su clave de acceso) → **🔌 Integraciones** → **🧠 Inteligencia artificial del vendedor**.
3. Elige **"Mi cuenta de DeepSeek"**, pega la clave → **Guardar y probar**. Marcia la prueba al instante.

La clave se guarda en el servidor (tabla `secretos`, separada de los datos públicos), **nunca se vuelve a mostrar** (solo los últimos 4 caracteres) y nunca llega al navegador. Su consumo no cuenta para el tope de la plataforma. Tutorial público: **https://dwday-38964763.online/ayuda/deepseek** (también dentro del panel).

## 3. Usarlo sin DeepSeek

Cualquiera de estas opciones apaga la IA:
```
IA_PROVIDER=simulado        # apaga la IA aunque haya clave
# o dejar DEEPSEEK_API_KEY vacío
```
`sudo deploy/reiniciar.sh` → `/salud` muestra `"ia":"simulado"`.

También pasa automáticamente si DeepSeek no responde, si la clave no tiene saldo o si se alcanza el tope diario: **el sistema cambia a reglas sin cortar ninguna venta** y vuelve a la IA cuando está disponible.

## 4. Cómo está integrado (para desarrolladores)

- `app/ia.py`: cliente único para APIs compatibles con OpenAI (DeepSeek, OpenAI). Resuelve credenciales (negocio → plataforma), aplica el tope diario, reintenta si DeepSeek devuelve JSON vacío y registra tokens usados.
- `app/vendedor.py`: vendedor virtual. La IA recibe la **ficha del negocio** (catálogo con índices, stock, precios, info) primero —para aprovechar la caché— y devuelve **acciones en JSON** (`agregar`, `quitar`, `mostrar`, `cliente`, `pago`, `confirmado`). El servidor valida stock, precios y totales; si la IA menciona un precio que no existe, se descarta y responde el modo reglas.
- `app/launcher.py`: modo **híbrido** — reglas para el flujo normal (costo 0) y DeepSeek solo cuando el usuario se sale del flujo.
- `app/importar.py`: `desde_foto` (visión de DeepSeek para menús/folletos), `con_ia` (extraer productos del texto de una web).
- `app/logos.py`: sugerencia de colores y lema.

Más detalle: [deepseek.md](deepseek.md) · [vendedor-virtual.md](vendedor-virtual.md).
