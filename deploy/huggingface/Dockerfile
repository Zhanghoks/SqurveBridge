FROM node:20-bookworm-slim AS frontend
WORKDIR /build
COPY demo-app/package.json demo-app/package-lock.json ./
RUN npm ci
COPY demo-app/ ./
RUN npm test && npm run build

FROM node:22-bookworm-slim AS pi-builder
WORKDIR /build
COPY pi/ ./pi/
COPY demo/build_embedded_pi.sh ./demo/build_embedded_pi.sh
RUN bash demo/build_embedded_pi.sh

FROM node:22-bookworm-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    SQURVE_DEPLOYMENT_TARGET=hf-space \
    SQURVE_LLM_PROVIDER=qwen \
    SQURVE_LLM_MODEL=qwen-plus
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && useradd --create-home --uid 1000 user
COPY . /app
COPY --from=frontend /build/dist /app/demo-app/dist
COPY --from=pi-builder /build/pi /app/pi
RUN python -m pip install --upgrade pip \
    && python -m pip install -r deploy/huggingface/requirements.txt \
    && chmod +x deploy/huggingface/entrypoint.sh \
    && mkdir -p /app/tmp /app/artifacts \
    && chown -R user:user /app
USER user
EXPOSE 7860
RUN node --version && python --version
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl --fail http://127.0.0.1:7860/api/health || exit 1
ENTRYPOINT ["/app/deploy/huggingface/entrypoint.sh"]
