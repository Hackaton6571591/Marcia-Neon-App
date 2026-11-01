# Marcia Neon App

Hackatón DonWeb. La herramienta para que un negocio local **deje de perder pedidos, consultas y turnos** que hoy atiende a mano, por WhatsApp o por teléfono.

## Problema
Un negocio local pierde ventas porque atiende consultas y pedidos a mano, por WhatsApp o teléfono: mensajes que se pierden, pedidos mal anotados, clientes que esperan y se van.

## Solución
Una landing con un asistente con IA, **Marcia**: *"Decime qué rubro sos y te ayudo a no perder más pedidos."*
El **launcher** (creador de soluciones) conversa con el dueño del negocio, entiende su rubro y su problema, y le arma y publica su solución:

1. **Web con asistente** (chat/avatar que responde consultas).
2. **Catálogo + bot de pedidos** (restaurante, ferretería, etc.).
3. **Turnos con IA** (peluquería, consultorio, etc.).

Integra IA real (DeepSeek) con un proveedor simulado de respaldo para que la demo nunca se caiga.

## 🧠 DeepSeek integrado
Marcia Neon trae **DeepSeek integrado**: un vendedor virtual que conversa con los clientes, arma pedidos y turnos, muestra productos con foto, y una IA que lee fotos de menús y folletos y copia catálogos de otras webs.
- **IA incluida** con la clave de la plataforma (modelo económico `deepseek-chat`, caché de contexto, tope diario).
- **Cada negocio puede usar su propia API key de DeepSeek** desde *Panel → Integraciones → Inteligencia artificial del vendedor*.
- Tutorial para negocios: [docs/deepseek.md](docs/deepseek.md) y la página pública `/ayuda/deepseek` (también dentro del panel).
- Sin IA, el sistema sigue funcionando con reglas: nunca se corta una venta. Comparación completa y pasos en [docs/uso-con-y-sin-ia.md](docs/uso-con-y-sin-ia.md).

## Stack
Python 3.12 · FastAPI · SQLite (WAL) · HTML/CSS/JS nativo · Caddy · systemd. Sin Docker ni Node, optimizado para un VPS de 2 vCPU y 4 GB.

## Documentación
- [docs/arquitectura-landing-launcher.md](docs/arquitectura-landing-launcher.md): arquitectura de la landing y el launcher (flujo, IA, datos, API, estructura).
- [docs/arquitectura.md](docs/arquitectura.md): stack y criterios de optimización.
- [docs/idea-y-evaluacion.md](docs/idea-y-evaluacion.md): evaluación de la idea, alcance del MVP y riesgos.
- [docs/servidor.md](docs/servidor.md): server, usuario y entorno.
- [docs/bitacora.md](docs/bitacora.md): registro cronológico de todo lo que se hace.
- [docs/vision-producto.md](docs/vision-producto.md): visión del producto (ecommerce + CRM + chatbot + WhatsApp) y estado por funcionalidad.
- [docs/cuentas.md](docs/cuentas.md): usuario y contraseña para los negocios.
- [docs/google-calendar.md](docs/google-calendar.md): sincronización con Google Calendar por API.
- [docs/uso-con-y-sin-ia.md](docs/uso-con-y-sin-ia.md): **cómo usar Marcia con DeepSeek y sin DeepSeek**, cómo sacar e integrar la API key.
- [docs/deepseek.md](docs/deepseek.md): **DeepSeek integrado** y tutorial para que cada negocio conecte su propia API key.
- [docs/vendedor-virtual.md](docs/vendedor-virtual.md): chatbot vendedor de cada tienda (proceso de venta, IA, seguridad).
- [docs/launcher.md](docs/launcher.md): implementación del launcher, IA, API y pruebas.
- [docs/mobile.md](docs/mobile.md): mobile nativo y PWA (cada tienda se instala como app).
- [docs/deploy.md](docs/deploy.md): Caddy, servicio, URLs y cómo vincular el dominio.

## Ver en vivo
- 📄 **Presentación del proyecto:** https://dwday-38964763.online/proyecto ([docs/presentacion.md](docs/presentacion.md))
- **https://dwday-38964763.online** (dominio oficial de la hackatón, HTTPS)
- Alternativa: https://66-97-32-220.sslip.io

## Estado
- ✅ Landing pública.
- ✅ Launcher (`/crear`): chat con Marcia + vista previa en vivo + publicar.
- ✅ Página pública del negocio (`/n/{slug}`): pedidos o turnos.
- ✅ Panel privado del negocio (`/panel/{slug}?t=…`): pedidos, productos (manual + CSV), medios de pago.
- ✅ **Vendedor virtual** en cada tienda: responde dudas y arma el pedido conversando, integrado al catálogo.
- ✅ Copiar menú desde una URL; logo e imagen desde la web o Instagram; categorías e ilustraciones.
- ✅ Mercado Pago Checkout Pro listo para activar con el access token (modo manual en la hackatón).
- ⏳ IA real: DeepSeek integrado, falta cargar la API key (mientras tanto, modo demo).

- ✅ Mobile nativo + PWA: Marcia y cada tienda se instalan en el celular.

## Demo rápida
1. Entrar a la vista previa → "Restaurante".
2. Responder a Marcia (o usar las sugerencias) → **Publicar**.
3. Abrir "Ver mi página", hacer un pedido → aparece en "Mi panel".
4. En la tienda, tocar **💬 Pedí por chat** y pedir: *"hola, tenés empanadas de carne?"*, *"3"*, *"y una coca"*, *"eso es todo"*…

Tienda de ejemplo completa: https://dwday-38964763.online/n/don-luigi-2

## Correr local
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```
