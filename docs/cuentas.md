# Cuentas: usuario y contraseña para los negocios

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
