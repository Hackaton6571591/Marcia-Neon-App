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
- `docs/deploy.md`: se crea cuando llegue el dominio.

## Estado
Arquitectura de landing + launcher definida. Siguiente paso: esqueleto de la app (ver el plan de construcción en la arquitectura).
