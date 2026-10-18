# Seguridad de mufa

mufa guarda el acceso a la red de sus usuarios: credenciales de routers,
OLTs y switches. Este documento explica qué protege cada capa y qué queda
pendiente.

## Lo que ya está implementado

### Los datos no salen del servidor del cliente
mufa es autoalojado. No hay telemetría ni conexión a servidores externos:
la licencia se verifica sin internet.

### Contraseñas de usuarios
- Se guardan con **Argon2id** (el algoritmo recomendado por OWASP), nunca en claro.
- Mínimo 12 caracteres.
- Si el email no existe, la verificación tarda lo mismo que con un email
  real: no se puede averiguar qué usuarios existen midiendo tiempos. El
  mensaje de error también es el mismo en ambos casos.
- **Bloqueo por fuerza bruta:** 5 intentos fallidos seguidos bloquean ese
  email y esa IP durante 15 minutos.

### Verificación en dos pasos
- Códigos **TOTP** de 6 dígitos, compatibles con cualquier app de autenticación.
- Diez **códigos de recuperación** de un solo uso al activarla, por si se
  pierde el teléfono. Se guardan como hash y se pueden regenerar.
- **Obligatoria para Técnico N2, Ingeniero N3, Senior y Admin**, es decir,
  para todo rol que puede usar las credenciales de los equipos (terminal,
  respaldos, herramientas): sin ella, la API solo les deja activarla
  (`MUFA_EXIGIR_DOS_PASOS=0` la desactiva, solo para pruebas).
- Funciona con cualquier app TOTP (RFC 6238): Google y Microsoft
  Authenticator, Contraseñas de Apple, 1Password, Bitwarden, Proton, Authy,
  2FAS, Aegis. La app las muestra al crear el usuario y al activarla.
- El secreto se guarda cifrado, igual que las credenciales de los equipos.
- Un código ya usado no sirve de nuevo, aunque siga en su ventana de 30 s.
- Un código incorrecto cuenta como intento fallido para el bloqueo.
- Si alguien pierde el teléfono, un Admin la restablece y la persona la
  vuelve a configurar al entrar.

### Sesiones
- Token aleatorio de 256 bits. En la base se guarda solo su SHA-256: una
  copia filtrada de la base no sirve para entrar.
- Vencen a las 8 h (`MUFA_DURACION_SESION_HORAS`).
- Cambiar la contraseña, que un admin la restablezca o desactivar un
  usuario cierra todas sus sesiones.

### Credenciales de los equipos
- Cifradas con **Fernet** (AES-128-CBC + HMAC-SHA256).
- La clave de cifrado vive en un archivo aparte (`secreto.key`, permisos
  0600), no en la base: un respaldo de la base sola no alcanza para leer
  las contraseñas.
- La API nunca las devuelve, ni cifradas: solo informa si hay credenciales
  cargadas.
- El registro de eventos anota que la contraseña cambió, nunca cuál es.

### Llevar los datos a otra computadora
- El archivo `.mufa` lleva la base y la clave de cifrado, así que va
  cifrado con una frase de al menos 12 caracteres (scrypt + Fernet). Sin la
  frase no se puede leer nada, ni siquiera los nombres de los equipos.
- Solo lo descarga un administrador, que tiene que volver a escribir su
  contraseña. Queda en el registro de eventos.
- Solo se abre en una instalación sin usuarios y con el token de primera
  vez: nunca reemplaza datos que ya existen. Las sesiones abiertas no viajan.

### Conexión a los equipos
- **Clave de host fija por equipo:** la primera conexión guarda la clave
  SSH del equipo y, si después cambia, mufa corta antes de mandar la
  contraseña (posible suplantación).
- **Lista blanca de comandos por marca:** el diagnóstico solo puede
  ejecutar comandos de lectura aprobados. Se verifica en tiempo de
  ejecución y con un test que recorre el código.
- **Paginación solo de la sesión:** por consola (Huawei, ZTE, HPE ProCurve,
  Cisco), antes de pedir la configuración mufa manda `screen-length 0
  temporary`, `terminal length 0` o `no page`. Solo afectan a esa sesión de
  terminal, no cambian la configuración del equipo y están en la lista blanca.

- **SHA-1 apagado por defecto** (CVE-2026-44405 / GHSA-r374-rxx8-8654):
  mufa usa paramiko 4 porque la 5 quitó por completo los algoritmos que
  hablan muchos IOS, VRP y JunOS viejos, pero cada conexión los desactiva y
  solo reintenta con ellos si el equipo no sabe negociar nada moderno. En la
  terminal se avisa. La clave del equipo se verifica igual.
- **Una clave de otro tipo no es «nueva»:** si ya conocemos la clave de un
  equipo y aparece con otro tipo (por ejemplo ssh-rsa en lugar de ed25519),
  se trata como clave cambiada: es justo lo que haría un intermediario.
- Protección contra Terrapin (CVE-2023-48795): paramiko negocia «strict kex».

### Terminal (SSH, Telnet, serie)
Es lo único de mufa que escribe en los equipos, y solo lo que la persona
teclea: mufa no agrega ni ejecuta nada por su cuenta.
- **Clave del equipo como en PuTTY:** la primera vez se muestra el tipo y la
  huella SHA-256 y la persona elige *Confiar y guardar*, *Solo esta vez* o
  *Cancelar*. Si la clave cambió se muestran la vieja y la nueva, y solo un
  Ingeniero N3 o superior puede reemplazarla (queda en el registro).
- Solo roles con permiso de usar credenciales y verificación en dos pasos.
- Un Técnico N2 se conecta solo a equipos del inventario; ir a cualquier IP
  desde el servidor de mufa queda para Ingeniero N3 en adelante.
- 5 intentos fallidos seguidos bloquean la terminal de esa persona 15
  minutos (contra probar contraseñas de un equipo desde mufa).
- La sesión de mufa se revisa cada minuto: si se cierra (cambio de
  contraseña, usuario desactivado, rol sin permiso), la terminal se corta.
- WebSocket solo desde la propia app (se verifica el origen) y con la cookie
  de sesión, que es HttpOnly y SameSite=Strict.
- Se cierra sola tras 30 minutos sin actividad.
- El registro guarda quién abrió cada sesión, hacia dónde, cuánto duró y los
  intentos fallidos con su motivo. **Nunca** lo que se escribió.
- Telnet avisa que viaja sin cifrar.

### App de escritorio
- El servidor escucha solo en 127.0.0.1 y únicamente acepta los nombres
  `127.0.0.1` y `localhost` (contra el *DNS rebinding*: una página web que
  apunte su dominio a tu computadora no llega). En un servidor se configura
  con `MUFA_HOSTS_PERMITIDOS=mufa.tuempresa.com`.
- Las herramientas (ping, traceroute) corren sin abrir ventanas y sin shell.

### Monitoreo y respaldos
- **SNMPv3 authPriv por defecto** (SHA-256 + AES). Sin DES ni 3DES. Las
  claves SNMP se guardan cifradas y la API no las devuelve.
- Solo consultas SNMP (GET/WALK): mufa nunca envía SET.
- Los respaldos de configuración se guardan cifrados: pueden incluir
  secretos del equipo. Su contenido solo lo ven los roles que pueden usar
  credenciales, y cada lectura queda en el registro de eventos.
- Por defecto el respaldo de MikroTik usa `/export show-sensitive`: incluye
  contraseñas y claves (secretos PPPoE, VPN, wifi), porque sin ellas no se
  puede restaurar el equipo. Se apaga en Respaldos (entonces usa `/export`,
  que en RouterOS 7 no las incluye). Las copias por FTP simple viajan sin
  cifrar: con secretos, usar SFTP.
- Un respaldo que llega cortado (Cisco sin `end`, Huawei sin `return`,
  Junos con llaves sin cerrar, o una consola que deja de responder) no se
  guarda: se registra el error y queda el respaldo anterior.

### Control de acceso
- Cada ruta de la API pide un **permiso** concreto, y cada rol tiene un
  conjunto fijo de permisos.
- No se puede quitar ni desactivar al último administrador.
- **Registro de eventos:** inicios de sesión (incluidos los fallidos),
  cambios de usuarios, inventario, auditorías y licencia, con usuario y hora.

### API
- Cabeceras de seguridad en todas las respuestas: `X-Content-Type-Options`,
  `X-Frame-Options: DENY`, `Content-Security-Policy`, `Referrer-Policy`,
  `Cache-Control: no-store`.
- Validación estricta de entradas (Pydantic): IPs, puertos, largos máximos.
- Archivos subidos limitados a 5 MB.
- Consultas a la base solo por el ORM (SQLAlchemy): sin SQL armado con texto.
- Por defecto el servidor escucha solo en `127.0.0.1`.

### Licencias
- Firmadas con **Ed25519**. El servidor solo tiene la clave pública:
  puede verificar una licencia, pero no fabricarla. Cambiar un solo byte
  invalida la firma.

### Instalación
- **HTTPS incluido** con Docker: Caddy pide y renueva el certificado
  (Let's Encrypt con dominio, CA propia sin dominio) y agrega HSTS.
- El contenedor de mufa no publica puertos: solo se llega por el proxy.
  El servidor toma la IP real del cliente del proxy (`--proxy-confiable`)
  para que el bloqueo por intentos fallidos funcione por persona.
- Corre como usuario sin privilegios dentro del contenedor.

### Alertas
- Los webhooks van firmados con HMAC-SHA256 (`X-Mufa-Firma`), así quien
  los recibe comprueba que vienen de mufa.
- Correo con STARTTLS o SSL. Tokens y contraseñas de los canales cifrados.

### Proceso
- El CI corre en cada cambio: formato, lint, tipos estrictos, más de 200 tests,
  **pip-audit** de las dependencias de producción y una instalación
  completa con Docker probada por HTTPS.
- Hook de pre-commit que bloquea IPs públicas, ASNs y nombres internos.
- Reporte privado de vulnerabilidades: [SECURITY.md](../SECURITY.md).

## Pendiente (en orden)

1. **Rotación de la clave de cifrado** sin perder las credenciales guardadas.
2. **Respaldos cifrados** del directorio de datos de mufa.
3. **Límite de origen**: aceptar conexiones solo desde las redes de gestión.
4. **Evaluar las ACL de Cisco** para no marcar servicios que sí están filtrados.
