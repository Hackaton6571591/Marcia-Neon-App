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

## Stack
Python 3.12 · FastAPI · SQLite (WAL) · HTML/CSS/JS nativo · Caddy · systemd. Sin Docker ni Node, optimizado para un VPS de 2 vCPU y 4 GB.

## Documentación
- [docs/arquitectura-landing-launcher.md](docs/arquitectura-landing-launcher.md): arquitectura de la landing y el launcher (flujo, IA, datos, API, estructura).
- [docs/arquitectura.md](docs/arquitectura.md): stack y criterios de optimización.
- [docs/idea-y-evaluacion.md](docs/idea-y-evaluacion.md): evaluación de la idea, alcance del MVP y riesgos.
- [docs/servidor.md](docs/servidor.md): server, usuario y entorno.
- [docs/bitacora.md](docs/bitacora.md): registro cronológico de todo lo que se hace.
- [docs/vision-producto.md](docs/vision-producto.md): visión del producto (ecommerce + CRM + chatbot + WhatsApp) y estado por funcionalidad.
- [docs/launcher.md](docs/launcher.md): implementación del launcher, IA, API y pruebas.
- [docs/mobile.md](docs/mobile.md): mobile nativo y PWA (cada tienda se instala como app).
- [docs/deploy.md](docs/deploy.md): Caddy, servicio, URLs y cómo vincular el dominio.

## Ver en vivo
- Vista previa: https://66-97-32-220.sslip.io
- Dominio oficial: https://dwday-38964763.online (cuando se cree la zona DNS)

## Estado
- ✅ Landing pública.
- ✅ Launcher (`/crear`): chat con Marcia + vista previa en vivo + publicar.
- ✅ Página pública del negocio (`/n/{slug}`): pedidos o turnos.
- ✅ Panel privado del negocio (`/panel/{slug}?t=…`): pedidos, productos (manual + CSV), medios de pago.
- ✅ Mercado Pago Checkout Pro listo para activar con el access token (modo manual en la hackatón).
- ⏳ IA real: DeepSeek integrado, falta cargar la API key (mientras tanto, modo demo).

- ✅ Mobile nativo + PWA: Marcia y cada tienda se instalan en el celular.

## Demo rápida
1. Entrar a la vista previa → "Restaurante".
2. Responder a Marcia (o usar las sugerencias) → **Publicar**.
3. Abrir "Ver mi página", hacer un pedido → aparece en "Mi panel".

## Correr local
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```
