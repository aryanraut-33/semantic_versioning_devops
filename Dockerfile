FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY app.py VERSION ./
COPY templates/ ./templates/

# Supply the source commit at build time so it travels with the image.
ARG APP_COMMIT=unknown
ENV APP_COMMIT=${APP_COMMIT}
LABEL org.opencontainers.image.revision="${APP_COMMIT}"

USER 10001:10001

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
