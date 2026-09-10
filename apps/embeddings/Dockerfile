FROM python:3.12.10-slim-bookworm@sha256:97983fa8cc88343512862c62307159a82261c3528dc025f79e5a3f7af43e50b4
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false EMBEDDINGS_BACKEND=real MODEL_REVISION=fd1525a9fd15316a2d503bf26ab031a61d056e98
WORKDIR /app
RUN groupadd --gid 10001 mentor && useradd --uid 10001 --gid mentor --no-create-home mentor
COPY apps/embeddings/requirements-real.lock ./requirements.lock
COPY apps/worker/src/embedding_service.py ./apps/worker/src/embedding_service.py
COPY apps/embeddings/model-cpu ./model-cpu
COPY apps/embeddings/model-cpu.manifest.sha256 ./model-cpu.manifest.sha256
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
USER 10001:10001
CMD ["python", "-m", "apps.worker.src.embedding_service"]
