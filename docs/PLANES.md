# Planes de mufa

mufa es **open-core**:

- **Este repositorio (AGPL-3.0)** es la edición gratuita. Es completa y útil
  por sí sola para una red chica, y cualquiera puede descargarla, probarla
  y revisar su código.
- **Los módulos de pago** están en `src/mufa/pro/`, bajo una licencia
  comercial ([LICENSE-PRO.md](../LICENSE-PRO.md)): se pueden leer y
  auditar, pero usarlos requiere una licencia Pro vigente. Van incluidos en
  todas las descargas y se activan al instalar la licencia.
- **Los servicios de mufa** (mufa Avisos, respaldo externo) corren en los
  servidores de mufa y se activan con la suscripción.

## Precios

| Plan | Mensual | Anual | Para quién |
|---|---|---|---|
| **Gratis** | $0 | $0 | El técnico o el ISP chico que quiere ordenar su red |
| **Pro** | $29 | — | El ISP que necesita no perderse una falla. **Equipos ilimitados** |
| **Empresa** | desde $199 | a cotizar | Operadores con NOC propio y requisitos de seguridad |

Precios en dólares. Por ahora se cobra con Ko-fi (PayPal o tarjeta), mes a
mes.

El plan Consultor ($79) se quitó: ofrecía casi lo mismo que Pro. Su lugar
lo toman dos ofertas que no compiten con Pro:

- **mufa Edge** (en desarrollo): control de tráfico por cliente en un
  servidor propio, entre la red de acceso y la salida a internet. Colas por
  plan (CAKE/HTB) para miles de clientes, DHCP (ISC Kea) conectado al IPAM y
  la calidad de cada cliente (latencia, pérdidas). Licencia mensual según el
  rendimiento en Gbps, con un piloto en la red del ISP antes de pagar. Es la
  alternativa accesible a las cajas propietarias de control de tráfico.
- **Ingeniería**: servicios del ingeniero que construye mufa, por proyecto o
  por hora: puesta en marcha de mufa, diseño y auditoría de red, colas y
  ancho de banda, FTTH/GPON, seguridad de equipos y capacitación.

Los pedidos de ambos llegan por el formulario del sitio (tipos «servicio» y
«edge») y avisan por Telegram.

## Qué incluye cada plan

| | Gratis | Pro | Empresa |
|---|:---:|:---:|:---:|
| Equipos | 10 | ilimitados | ilimitados |
| Usuarios | 3 | ilimitados | ilimitados |
| Interfaces vigiladas (caída y saturación) | 5 | ilimitadas | ilimitadas |
| Historial de tráfico | 7 días | 1 año | a medida |
| **Monitoreo** SNMPv3 multimarca, caídas, reinicios, disponibilidad | ✓ | ✓ | ✓ |
| Datos del equipo por SNMP (serie, modelo, versión) | ✓ | ✓ | ✓ |
| **Auditoría** de seguridad, versiones con CVE, puntaje | ✓ | ✓ | ✓ |
| **Respaldos** diarios cifrados, diferencias, buscador | ✓ | ✓ | ✓ |
| **IPAM y VLANs**, importados de los equipos | ✓ | ✓ | ✓ |
| **Fibra óptica**: presupuesto, dispersión, PON, potencia de SFP | ✓ | ✓ | ✓ |
| **Herramientas**: ping, traceroute, MTR, subredes, "¿dónde está?" | ✓ | ✓ | ✓ |
| Mapa de topología y modo NOC | ✓ | con su logo | con su logo |
| Alertas con bot y correo propios | ✓ | ✓ | ✓ |
| **mufa Avisos** (bot de Telegram y correo de mufa) | solo el dueño, 20/día | contactos y grupos | contactos y grupos |
| Escalamiento, guardias, "Lo tomo yo" | | ✓ | ✓ |
| Ventanas de mantenimiento | | ✓ | ✓ |
| Predicción de capacidad | | ✓ | ✓ |
| Alertas de potencia óptica por tendencia | | ✓ | ✓ |
| OLT GPON (Huawei, ZTE) | | ✓ | ✓ |
| Consumo por cliente (NetFlow) | | ✓ | ✓ |
| Informes en PDF con su logo | | ✓ | ✓ |
| Página de estado pública | | ✓ | ✓ |
| Integración con WispHub y Mikrowisp | | ✓ | ✓ |
| Respaldo externo cifrado | | ✓ | ✓ |
| Restauración de configuraciones | | ✓ | ✓ |
| Cambios masivos con Ansible y aprobación | | ✓ | ✓ |
| Varios clientes separados en una instalación | | | a medida |
| AAA de equipos (TACACS+ / RADIUS) | | | ✓ |
| Mesa de ayuda N1 / N2 / N3 | | | ✓ |
| Inicio de sesión con la cuenta de la empresa (SSO) | | | ✓ |
| Soporte | comunidad | 1 día hábil | 4 horas |

Las funciones de la tabla se van publicando por etapas; el estado de cada
una está en el historial del repositorio.

## Cómo funciona la licencia

Una licencia es un archivo de texto firmado con Ed25519 por el emisor. Se
instala desde la app (Ajustes → Plan) o la API (`PUT /api/v1/licencia`,
rol Admin) y se verifica sin internet: el servidor tiene solo la clave
pública, así que puede comprobar una licencia pero no fabricarla.

Lo que define una licencia (`mufa.licencia`):

- `plan`: pro, consultor o empresa.
- `cliente`: a nombre de quién está.
- `max_equipos`: vacío en los planes de pago (ilimitados).
- `vence`: fecha, u opcional para licencias perpetuas.
- `id`: el mismo en cada mes de una suscripción.

**Cómo se vende.** Pro es una membresía mensual de Ko-fi ($29, o $15 para
los primeros 150 fundadores). Cada pago llega al sitio por el webhook de
Ko-fi (`sitio/functions/api/kofi.js`), que firma una licencia de 35 días
con la clave del emisor (secreto `LICENCIA_CLAVE` del sitio) y la avisa
por Telegram para mandársela al cliente. Mientras siga pagando, la app trae
sola la licencia del mes siguiente desde `/api/licencia/renovar`, mandando
solo el `id`. Si cancela, vence sola y mufa vuelve al plan gratis sin
perder datos.

Cada módulo de pago protege sus rutas con
`requiere_funcion(Funcion.X)`: si el plan instalado no lo incluye, la API
responde 402.
