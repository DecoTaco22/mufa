# Cambios

## v0.1.8

- **Mapa de la red:** mufa lee por SNMP los vecinos de cada equipo (LLDP, CDP
  de Cisco y la tabla de vecinos de MikroTik) y dibuja qué está conectado con
  qué, con el estado de cada uno. Los vecinos que no están en mufa también
  aparecen, para saber qué falta agregar.
- **Modo NOC:** pantalla completa para el televisor del NOC, con caídos,
  respaldos, seguridad, el mapa y los últimos avisos; se actualiza sola.
- **MTR** en Herramientas: dónde se pierde o se demora el tráfico en el camino.
- **Buscador en los respaldos:** una IP, una VLAN o un vecino BGP en la
  configuración de todos los equipos, también en versiones anteriores.
- Dependencias al día (cryptography, SQLAlchemy, FastAPI, vite y otras).

## v0.1.7

- **Prueba gratis de Pro por 14 días**, desde Ajustes › Plan o desde la
  página de cada módulo Pro: sin tarjeta, una por instalación. Al terminar
  vuelve al plan gratis sin perder datos.
- La app dice quién cobra Pro: Ko-fi, con PayPal o tarjeta.
- El sitio manda sola la licencia Pro por correo al cliente apenas paga
  (cuando el correo está configurado).

## v0.1.6

- **Respaldos completos:** en MikroTik el respaldo incluye contraseñas y
  claves (`/export show-sensitive`; en RouterOS 6 el export ya las trae), así
  sirve para restaurar el equipo tal cual. Se puede apagar en Respaldos.
- **Configuraciones grandes:** mufa espera hasta 10 minutos a que el equipo
  mande la configuración (mucho BGP o listas de miles de direcciones tardan
  en empezar). Por consola quita la paginación solo de esa sesión, así una
  configuración de miles de líneas llega de una vez.
- **Nunca un respaldo cortado:** si la configuración llega incompleta (Cisco
  sin `end`, Huawei sin `return`, o la consola deja de responder) no se
  guarda, se avisa y queda el respaldo anterior. El error dice qué pasó en
  vez de «el puerto no responde».
- **MikroTik por API:** el respaldo lee más de 100 menús (BGP completo de
  RouterOS 6 y 7, filtros de rutas, OSPF, PPP, túneles, colas, IPsec,
  scripts...). Para un `/export` idéntico al del equipo, se recomienda SSH.
- **Microsoft Store:** si los datos los dejó una versión más nueva de mufa,
  la app lo explica y dice cómo actualizar, en vez de no arrancar.

## v0.1.5

- **Actualizaciones:** mufa avisa cuando sale una versión nueva. En Windows
  (con el instalador) y en Mac se instala con un clic desde Ajustes y la app
  se vuelve a abrir sola. En un servidor, el aviso trae los pasos. Cada
  instalador se verifica con una firma antes de instalarlo.
- **Pro: avisos al equipo.** Tu bot de Telegram avisa a cada persona del NOC
  según quién está de turno. Botón «Lo tomo yo» y escalamiento a los
  supervisores si nadie lo toma; cuando el equipo vuelve, el aviso queda
  resuelto en todos los mensajes.
- **Pro: informes en PDF** con tu logo: disponibilidad (comparada con el mes
  anterior), caídas, interfaces más cargadas y seguridad. Por correo el día 1.
- **Pro: OLT GPON** Huawei y ZTE: cada ONU con su estado, potencia y
  distancia; aviso de corte de un puerto PON (fibra o luz) y de señal baja.
- Las páginas de Términos, Reembolsos y Privacidad describen el cobro con
  Ko-fi y las conexiones que hace la app.

## v0.1.4

- **Pro: predicción de capacidad.** Cada día se resume el tráfico de cada
  interfaz (percentil 95, promedio y máximo) y se guarda un año. Con los
  últimos 90 días, mufa calcula cuándo cada enlace llegará al 80 % de su
  velocidad en horas pico, con un gráfico de la tendencia, el crecimiento
  mensual y los enlaces ordenados por urgencia.
- **Pro por suscripción:** la licencia de una membresía se renueva sola cada
  mes mientras siga activa.
- Pro y Empresa habilitan funciones distintas.
- En la app, «Obtener Pro» lleva a la membresía.

## v0.1.3

- **Mac:** se descarga como `mufa-macos.dmg`, la imagen de disco de
  siempre: se arrastra mufa a Aplicaciones. La app muestra su versión, y
  las instrucciones explican cómo abrirla la primera vez en macOS 15
  (Sequoia) o más nuevo, donde ya no sirve el clic derecho › Abrir.
- **Servidor:** `sudo sh instalar.sh` revisa Docker y los permisos, pregunta
  con qué dirección van a entrar (la IP del servidor o un dominio), arranca
  mufa y muestra la dirección y el token. Entrar por la IP del servidor ya
  funciona (antes solo con un dominio o desde el mismo servidor). Para
  actualizar se descomprime el paquete nuevo encima y se vuelve a ejecutar.
- La descarga de «Llevar a otra computadora» funciona también en la app de Mac.

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
