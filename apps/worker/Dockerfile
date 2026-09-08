FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10001 mentor && useradd --uid 10001 --gid mentor --no-create-home mentor
COPY pyproject.toml README.md ./
COPY apps ./apps
RUN python -m pip install --upgrade "pip==25.1.1" && python -m pip install .
USER 10001:10001
CMD ["python", "-m", "apps.worker.src.main"]
