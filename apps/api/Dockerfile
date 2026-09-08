FROM python:3.12.10-slim-bookworm@sha256:97983fa8cc88343512862c62307159a82261c3528dc025f79e5a3f7af43e50b4
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10001 mentor && useradd --uid 10001 --gid mentor --no-create-home mentor
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY database ./database
COPY --chmod=755 apps/api/entrypoint.sh /usr/local/bin/mentor-api-entrypoint
RUN python -m pip install --upgrade "pip==25.1.1" && python -m pip install .
EXPOSE 8080
ENTRYPOINT ["mentor-api-entrypoint"]
CMD ["uvicorn", "apps.api.src.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
