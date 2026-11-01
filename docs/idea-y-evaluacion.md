# Idea y evaluación

## ¿Es buena idea?
**Sí, con un recorte de alcance.** Es buena porque:
- Ataca directo el problema planteado (consultas, pedidos y turnos manuales).
- Sirve a varios rubros con un solo producto, no a uno solo.
- La landing conversacional es la demo: el jurado ve el valor en 1 minuto.

## Riesgo principal
Construir "todo para todos" no llega a terminar en un hackatón. Lo que se arma tiene que **funcionar de punta a punta** en al menos dos rubros.

## Propuesta de alcance (MVP)
**Núcleo (obligatorio):**
1. Landing con chat: pregunta rubro y problema, y propone la solución.
2. Generación de la configuración del negocio (nombre, catálogo o servicios, horarios) a partir de la charla.
3. Un negocio demo de **pedidos** (restaurante) y uno de **turnos** (peluquería), ambos funcionando.
4. Panel simple para ver pedidos y turnos.
5. Chat público del negocio generado (el "asistente web").

**Si hay tiempo:** avatar, integración real con WhatsApp, más rubros, pagos.
**Fuera del MVP:** facturación, multi-idioma, app móvil.

## IA
- **DeepSeek** (propuesta del equipo): bajo costo, sirve para el "creador de soluciones" y el avatar.
- Se accede por API compatible con OpenAI. La clave va en variables de entorno y **nunca** al repo.
- A decidir: usar un solo modelo para todo o separar tareas (charla, extracción estructurada de pedidos/turnos).
- Detalle clave: la IA debe devolver datos **estructurados** (JSON) para pedidos y turnos, no solo texto, para evitar pedidos mal anotados.

## Preguntas abiertas
- Criterios de evaluación de DonWeb y qué hay que entregar.
- Dominio asignado y si el DNS apunta al server.
- Stack preferido o requerido.
- WhatsApp: ¿real (API de Meta) o simulado en la demo?
