# Marcia Neon — Presentación del proyecto (Hackatón DonWeb 2026)

**Página web de esta presentación:** https://dwday-38964763.online/proyecto

## Qué es
**Marcia Neon** es una plataforma con IA que, en un par de minutos y charlando, le arma a cualquier negocio local su **tienda online** o **agenda de turnos**, un **vendedor virtual** que atiende 24/7 y un **panel** para gestionar todo. Resuelve el desafío de la hackatón: negocios que pierden ventas porque atienden a mano, por WhatsApp o por teléfono.

## Dos modelos
- **Productos → tienda online** (restaurantes, comercios, ferreterías, ropa, pet shops): catálogo con fotos, carrito, pedido, pago, seguimiento y vendedor por chat.
- **Servicios → turnero** (peluquerías, consultorios, estética): agenda por profesional, horarios libres, reserva online o por chat, cancelación y calendario.

## Componentes
| Componente | Qué hace |
|---|---|
| **Landing** (`/`) | Explica el valor y lleva al launcher. Mobile, 9 KB comprimida. |
| **Launcher con IA** (`/crear`) | Charla guiada que arma la solución con vista previa en vivo. Productos por texto, **foto del menú/folleto** (DeepSeek visión) o **link de la web** (copia productos, fotos, logo y nombre). Logos con IA, deshacer, QR y compartir al publicar. |
| **Tienda online** (`/n/{negocio}`) | Estilo app de delivery: buscador, categorías, grilla con fotos, ficha, carrito, stock, pagos, seguimiento en vivo. PWA instalable. |
| **Vendedor virtual** | Chat integrado al catálogo: recomienda, muestra productos con foto, arma y cierra el pedido. No alucina (el servidor valida stock, precios y totales). Funciona sin IA. |
| **Turnero** | Horarios por día y profesional, horarios libres por duración, reserva validada, turnero por chat ("¿el martes antes de las 15?"), cancelación, .ics y Google Calendar por API. |
| **Panel / CRM** (`/panel/{negocio}`) | Clave de acceso (PIN). Pedidos en vivo con estados y aviso por WhatsApp, comanda a cocina, productos (manual, CSV, foto, URL), vendedor virtual, pagos, integraciones, compartir con QR. |
| **Importadores** | JSON-LD (Tiendanube/Shopify/VTEX), APIs JSON propias, recorrido de categorías + DeepSeek, foto/folleto. Respeta bloqueos de marketplaces. |
| **IA** | DeepSeek (`deepseek-chat`), caché de contexto, modo híbrido, tope diario, clave propia por negocio. Ver [uso-con-y-sin-ia.md](uso-con-y-sin-ia.md). |
| **Integraciones** | WhatsApp (links), webhook firmado, Mercado Pago (listo para activar), Google Calendar (listo para activar), exportación para PedidosYa/Uber Eats/Rappi. |

## Cómo lo hicimos
- **Stack:** Python 3.12 + FastAPI, SQLite (WAL), HTML/CSS/JS nativo, Caddy (HTTPS automático), systemd. Sin Docker ni Node, optimizado para el VPS.
- **Infraestructura DonWeb:** VPS de DonWeb (2 vCPU / 4 GB), dominio `dwday-38964763.online` con DNS de DonWeb, Let's Encrypt.
- **Seguridad:** scrypt, sesiones HttpOnly/Secure, protección SSRF, límites de intentos, secretos fuera del repo, totales calculados en el servidor.
- **Calidad:** pruebas de punta a punta de cada flujo, navegador sin pantalla (Playwright) en tamaño celular, instancia de prueba sin IA, scraping probado con sitios reales, bitácora completa en `docs/bitacora.md`.

## Demo
- Crear un negocio: https://dwday-38964763.online/crear?msg=pizzeria
- Pizzería con vendedor IA: https://dwday-38964763.online/n/don-luigi-2
- Tiendas importadas de webs reales: `/n/ferretera-san-luis`, `/n/chill-out`, `/n/pets`, `/n/nollyashop`
- Turnos: `/n/estilo-neon` (grilla) · `/n/soy-la-licenciada-huevo` (turnero por chat)
- Panel de demo: https://dwday-38964763.online/panel/pizzeria-compartir (clave **1357**)

## Roadmap
Modo sanatorio (especialidad, sede, cobertura), WhatsApp Business API, Mercado Pago y Google Calendar activados en producción, editor de diseño de la tienda, APIs de partners de delivery.
