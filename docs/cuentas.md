# Acceso al panel: clave (PIN) por negocio + cuentas opcionales

## Clave de acceso (modo principal)
- La **primera vez** que el negocio abre su panel (con el link que recibe al publicar), Marcia le pide **crear su clave** (mínimo 4 caracteres; puede ser un PIN numérico).
- Las **veces siguientes** le pide la clave. La sesión queda abierta 7 días en ese dispositivo (cookie HttpOnly/Secure; en la base solo el hash).
- Una vez creada la clave, **el link solo ya no alcanza**: ni el panel ni la API del panel funcionan sin sesión (401).
- **🔐 Acceso** en el panel: cambiar la clave (pide la actual; cierra las sesiones de los demás dispositivos) y cerrar sesión.
- Clave con scrypt + sal; límite de intentos por IP (6/min por negocio).
- Probado: crear (corta → rechazo), entrar, otro dispositivo con el link → pide clave, API sin sesión → 401, clave incorrecta, cambio de clave cierra la otra sesión, cerrar sesión, límite de intentos (429).

# Cuentas con email (opcional)

Cada negocio entra a su panel con **email y contraseña**.

## Flujo
- **Registro / ingreso:** `/ingresar` (pestañas *Ingresar* / *Crear cuenta*). Un usuario puede tener **varios negocios** → `/mis-negocios`.
- **Al crear un negocio en el launcher:** si estás logueado, queda en tu cuenta. Si no, al publicar aparece **"🔒 Crear mi cuenta"**.
- **Negocios creados antes (con link privado):** el panel muestra *"Protegé tu panel: creá tu usuario y contraseña"*. Al crear la cuenta (o ingresar con una existente) el negocio queda asociado y **se rota la clave del link**: el link privado viejo deja de dar acceso.
- **Panel de un negocio con cuenta:** sin sesión → redirige a `/ingresar`; con la sesión de otro usuario → 403.

## Seguridad
- Contraseñas con **scrypt** (sal aleatoria por usuario, `n=2^14, r=8, p=1`); nunca en texto plano. Mínimo 8 caracteres.
- Sesión en cookie **HttpOnly + Secure + SameSite=Lax** (30 días). En la base se guarda solo el **hash** del token de sesión.
- Mensaje genérico ante credenciales inválidas ("Email o contraseña incorrectos") y **límite de intentos** por IP (ingreso 8/min, registro 5/min).
- Asociar un negocio exige su link privado vigente (comparación en tiempo constante) y que el negocio no tenga dueño.

## API
| Método | Ruta | |
|---|---|---|
| POST | `/api/cuenta/registro` | `{nombre, email, clave, slug?, t?}` |
| POST | `/api/cuenta/ingresar` | `{email, clave, slug?, t?}` |
| POST | `/api/cuenta/salir` | cierra la sesión |
| GET | `/ingresar`, `/mis-negocios` | páginas |

## Pendiente
Recuperar contraseña por email (requiere un servicio de envío de correo) y verificación de email.
