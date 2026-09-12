FROM python:3.12.10-slim-bookworm@sha256:97983fa8cc88343512862c62307159a82261c3528dc025f79e5a3f7af43e50b4
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 mentor && useradd --uid 10001 --gid mentor --no-create-home mentor
COPY requirements.lock ./
COPY apps ./apps
COPY config ./config
COPY apps/external/ssl/gsgccr6alphasslca2025.crt /usr/local/share/ca-certificates/gsgccr6alphasslca2025.crt
RUN update-ca-certificates
RUN python -m pip install --require-hashes --no-deps -r requirements.lock
USER 10001:10001
CMD ["python", "-m", "apps.external.service"]
