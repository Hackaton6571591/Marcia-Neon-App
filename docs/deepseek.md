# DeepSeek integrado en Marcia Neon

Marcia Neon trae **DeepSeek integrado**: la IA que conversa con los clientes, entiende pedidos, lee fotos de menús y folletos, y copia catálogos de otras webs. Funciona en dos modos:

| Modo | Quién paga la IA | Cómo se activa |
|---|---|---|
| **IA de Marcia (incluida)** | La plataforma (clave en el servidor) | Por defecto, sin hacer nada |
| **IA propia del negocio** | El negocio, con su cuenta de DeepSeek | Panel → Integraciones → *Inteligencia artificial del vendedor* |

Si ninguna clave está disponible (o se agota el tope diario), **Marcia sigue funcionando con reglas**: el vendedor toma pedidos y turnos igual, solo que con respuestas menos flexibles. Nunca se corta la venta.

## Qué hace DeepSeek en el sistema

| Función | Dónde | Archivo |
|---|---|---|
| Vendedor virtual: responde dudas, recomienda, arma pedidos y turnos, muestra productos con foto | Tienda `/n/{slug}` | `app/vendedor.py` |
| Asistente que arma la tienda conversando (solo cuando el usuario se sale del flujo) | Launcher `/crear` | `app/launcher.py` |
| Leer **fotos de menús y folletos** y cargar los productos | Launcher y panel | `app/importar.py` (`desde_foto`) |
| Copiar catálogos de webs sin datos estructurados | Launcher y panel | `app/importar.py` (`con_ia`) |
| Sugerir colores y lema para el logo | Asistente de logos | `app/logos.py` |

## Cómo se usa sin alucinar y barato

- Modelo **`deepseek-chat`** (el más económico), temperatura baja y respuestas cortas.
- **Caché de contexto**: las instrucciones y la ficha del negocio van primero y no cambian, así DeepSeek cobra esa parte más barata.
- La IA solo usa el **catálogo de ese negocio** y devuelve **acciones en JSON** (agregar, quitar, mostrar productos, datos del cliente). El servidor valida todo: stock, precios, totales y horarios libres. Si menciona un precio que no existe, se descarta la respuesta.
- **Tope diario** de tokens para la clave de la plataforma (`IA_TOPE_TOKENS_DIA`).

Consumo medido: un mensaje del vendedor ≈ 1.200 tokens de entrada (la mayoría en caché) y ~50 de salida; leer un folleto chico ≈ 500 de entrada y ~40 de salida.

## Tutorial para cada negocio: conectar tu propia cuenta de DeepSeek

Este tutorial también está en el panel de cada negocio y en la página pública **`/ayuda/deepseek`**.

1. Entrá a **https://platform.deepseek.com** y creá una cuenta (podés usar tu email o Google).
2. En el menú, andá a **Top up** y cargá saldo. Con pocos dólares alcanza para miles de conversaciones.
3. Andá a **API keys** → **Create new API key**. Ponele un nombre (por ejemplo "Marcia - mi negocio") y copiá la clave que empieza con `sk-`.
   - Se muestra **una sola vez**. Guardala en un lugar seguro.
4. Abrí tu **panel de Marcia** → pestaña **🔌 Integraciones** → **🧠 Inteligencia artificial del vendedor**.
5. Elegí **"Mi cuenta de DeepSeek"**, pegá la clave y tocá **Guardar y probar**.
   - Marcia la prueba al instante. Si dice "✓ Conectado con tu cuenta", listo: tu vendedor virtual ya usa tu IA.
6. Para volver a la IA incluida, elegí **"IA de Marcia (incluida)"** y guardá.

**Seguridad de tu clave:** se guarda en el servidor, separada de los datos públicos de tu tienda; **nunca se vuelve a mostrar** (el panel solo enseña los últimos 4 caracteres) y nunca se envía al navegador de tus clientes. Si creés que alguien la vio, borrala en DeepSeek y creá una nueva.

## Para quien instala el proyecto (servidor)

En `/home/hackaton/creador-ia/.env` (permisos 600, **nunca se sube al repo**):

```
IA_PROVIDER=deepseek          # o "simulado" para apagar la IA
DEEPSEEK_API_KEY=sk-...       # clave de la plataforma (IA incluida)
DEEPSEEK_MODEL=deepseek-chat
IA_TOPE_TOKENS_DIA=400000
```

Después: `sudo deploy/reiniciar.sh`. `GET /salud` muestra `"ia":"deepseek"` cuando está activa.

También se puede usar **OpenAI** (u otra API compatible) por negocio desde el mismo panel: el cliente de IA (`app/ia.py`) es común a todos los proveedores.
