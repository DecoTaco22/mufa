# Cambios

## v0.1.2

- Instalador para Windows (`mufa-instalador-windows.exe`): se instala en
  Archivos de programa con permiso de administrador, con acceso en el menú
  Inicio, ícono opcional en el escritorio y desinstalador en «Aplicaciones
  instaladas». Al actualizar se instala encima, sin perder datos. Sigue la
  versión portátil (`mufa-windows.zip`).
- La app de Windows ya no es un solo `.exe` que se descomprime cada vez:
  abre más rápido y los antivirus la confunden menos con malware. Lleva
  nombre, versión y editor en sus propiedades.
- **Llevar a otra computadora:** en Ajustes, el administrador descarga todos
  los datos en un archivo cifrado con una frase. En la otra computadora,
  la pantalla de bienvenida tiene **Ya tengo cuenta** para abrirlo y entrar
  con el mismo usuario, en vez de crear una cuenta nueva.

## v0.1.1

- README con capturas de la app.
- Textos: «1 IP» y «1 red» en singular; el panel enlaza al horario de respaldos.

## v0.1.0 — primera versión pública

Edición gratuita para redes de hasta 10 equipos.

- Monitoreo SNMPv3 multimarca: estado, tráfico, caídas, reinicios; autocompleta
  nombre, marca, modelo y serie al probar la conexión.
- Auditoría de seguridad por SSH o la API de RouterOS (MikroTik, Cisco IOS),
  solo lectura.
- Respaldos cifrados de MikroTik, Cisco, Huawei, Juniper, HPE / Aruba,
  Ubiquiti, Nokia y ZTE, todos los días a la hora elegida (12:00 por
  defecto), también en equipos que solo aceptan consola. Copia automática a
  un servidor propio por SFTP, FTPS o FTP.
- IPAM agrupado por equipo con mapa de direcciones e importación desde el
  equipo; VLANs por dominio con su equipo e interfaz; calculadoras de fibra.
- Terminal SSH, Telnet y serie con verificación de la clave del equipo.
- Herramientas en vivo: ping, traceroute, DNS, puertos, "¿Dónde está?",
  calculadora IP.
- Alertas por Telegram, correo y webhook firmado.
- Usuarios con roles, verificación en dos pasos y registro de eventos.
- App con ventana propia para Windows y macOS; servidor con Docker y HTTPS.
