# Cómo contribuir a mufa

¡Gracias por querer ayudar! mufa lo usan técnicos e ingenieros en redes de
producción, así que cuidamos mucho dos cosas: que nunca cambie nada en un
equipo sin que la persona lo pida, y que sea fácil de entender.

## Antes de empezar

- **Ideas y problemas:** abre un issue con la plantilla que corresponda.
  También puedes dejar ideas en el sitio, en "¿Qué le falta a mufa?".
- **Vulnerabilidades:** nunca en un issue público. Sigue [SECURITY.md](SECURITY.md).
- Para cambios grandes, abre primero un issue para conversarlo.

## Preparar el entorno

```bash
uv sync --all-groups
uv run pre-commit install                 # obligatorio: ver "Datos sensibles"
(cd web && npm ci && npm run build)
uv run mufa servidor                      # http://127.0.0.1:8080
cd web && npm run dev                     # la app web con recarga automática
```

## Antes de abrir un pull request

```bash
uv run ruff format && uv run ruff check
uv run mypy src
uv run pytest
(cd web && npx tsc --noEmit -p .)
```

El CI corre lo mismo, más `pip-audit` y una instalación completa con Docker
probada por HTTPS.

## Reglas

**Solo lectura.** Monitoreo, auditoría y respaldos nunca escriben en un
equipo. Un comando nuevo para SSH o la API va en la lista blanca de su marca
(`src/mufa/security.py`) y tiene que ser de consulta. Por SNMP, solo GET y
WALK. `tests/test_no_write.py` lo verifica.

**Livianos con los equipos.** Pedir solo los datos necesarios, agrupar
columnas por consulta SNMP y no sondear más seguido de lo que hace falta: un
router de un ISP está atendiendo clientes.

**Datos sensibles.** Nunca se commitean IPs públicas, ASNs ni nombres reales
de nodos o clientes. El hook de pre-commit (`scripts/check_sensitive.py`)
bloquea el commit si detecta alguno. En ejemplos usa los rangos de
documentación (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32).

**Idioma.** La app, los mensajes y la documentación van en español neutro,
tuteando ("elige", "escribe"). Los errores explican qué pasó y qué hacer.

**Código.** Nombres en español, como el resto del proyecto. Comentarios solo
donde el porqué no es obvio. Tests para lo que se agrega o se corrige.

## Licencia de las contribuciones

mufa se publica bajo la [AGPL-3.0](LICENSE) y además se ofrece con licencias
comerciales (ver [docs/PLANES.md](docs/PLANES.md)). Al enviar un pull request
aceptas que tu contribución se publique bajo la AGPL-3.0 y que el
mantenedor pueda incluirla también en esas licencias comerciales.
