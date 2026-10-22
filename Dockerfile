# One image for the web, worker and beat services on Railway; each service sets its own start command.
# https://docs.railway.com/builds/dockerfiles

FROM node:24-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY assets ./assets
COPY vite.config.ts tsconfig.json tailwind.config.js ./
# Vite writes to static/ (vite.config.ts outDir); Tailwind scans templates/ and apps/ for class names.
COPY templates ./templates
COPY apps ./apps
RUN npm run build

FROM python:3.14-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH=/app/.venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
COPY --from=frontend /app/static ./static
# The production settings refuse to import without the secrets, so collectstatic runs with the development
# module (same files) and whitenoise's compress command adds the gzip and brotli copies its storage would make.
RUN DEBUG=False DJANGO_SETTINGS_MODULE=project.settings python manage.py collectstatic --noinput \
    && python -m whitenoise.compress static_root
RUN useradd --create-home app && chown -R app /app
USER app
ENV DJANGO_SETTINGS_MODULE=project.settings_production
CMD ["sh", "-c", "gunicorn project.wsgi --bind 0.0.0.0:$PORT"]
