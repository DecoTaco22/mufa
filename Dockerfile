# Imagen de mufa: el servidor con la API y la app web. HTTPS lo pone el proxy
# (ver docker-compose.yml).

FROM node:24-slim AS web
WORKDIR /mufa/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY web/ ./
# Compila en /mufa/src/mufa/web (ver vite.config.ts).
RUN npm run build

FROM python:3.13-slim AS construccion
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# Primero solo las dependencias: se reutilizan entre versiones si no cambian.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY --from=web /mufa/src/mufa/web ./src/mufa/web
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim
# ping: para saber si un equipo sin SNMP está encendido (ver mufa/alcance.py).
# traceroute: para la herramienta de la app.
# tzdata: para que TZ fije la hora del respaldo diario.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping traceroute tzdata \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 mufa \
    && mkdir /datos && chown mufa:mufa /datos
COPY --from=construccion /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    MUFA_DIR_DATOS=/datos \
    PYTHONUNBUFFERED=1
USER mufa
VOLUME /datos
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/salud')"
# Solo el proxy llega a este contenedor (no publica puertos): se confía en su X-Forwarded-For.
CMD ["mufa", "servidor", "--host", "0.0.0.0", "--proxy-confiable", "*"]
