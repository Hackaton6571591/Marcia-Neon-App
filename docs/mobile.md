# Mobile nativo

Requisito del equipo: **todo Marcia debe ser mobile responsive nativo**. La mayoría de los clientes de una pizzería o peluquería piden desde el celular.

## Principios aplicados en todas las pantallas
- **Diseño fluido**: grids que pasan a una columna, sin anchos fijos; se probó para 360–430 px.
- **Sin zoom de iOS**: todos los inputs con `font-size: 16px`.
- **Áreas táctiles ≥ 44 px** (botones, +/− del carrito, borrar producto). Sin efectos hover en pantallas táctiles.
- **Safe areas** (notch y barra inferior del iPhone): `viewport-fit=cover` + `env(safe-area-inset-*)` en barras fijas y encabezados.
- `touch-action: manipulation` (sin demora de 300 ms al tocar), sin resaltado gris al tocar, `overscroll-behavior` controlado.
- Respeta `prefers-reduced-motion`.

## Instalable como app (PWA)
- **Marcia** (landing, launcher, panel): `/static/manifest.webmanifest`. El dueño del negocio puede "Agregar a inicio" su panel y abrirlo como app.
- **Cada tienda** tiene su propio manifest: `/n/{slug}/manifest.webmanifest`, con el **nombre del negocio**. El cliente de la pizzería instala "Don Luigi" en su celular como si fuera una app propia.
- `display: standalone`, `theme-color` oscuro, ícono SVG, meta tags de Apple.

## Por pantalla
| Pantalla | Adaptación móvil |
|---|---|
| Landing | Hero en una columna, input y botón apilados, teléfono demo más chico, chips táctiles. |
| Launcher `/crear` | Pestañas **Chat / Vista previa** a pantalla completa (altura `100dvh`, se adapta al teclado). Punto verde en "Vista previa" cuando Marcia agrega datos. Sugerencias en una fila deslizable. Al publicar, salta a la vista previa con los botones. |
| Tienda `/n/{slug}` | Barra inferior fija con total y botón de confirmar (respeta la barra del iPhone), +/− de 44 px, medios de pago en botones de media pantalla. |
| Panel | Pestañas deslizables, KPIs en 2 columnas, pedidos compactos, edición de productos con el nombre a todo el ancho. |
