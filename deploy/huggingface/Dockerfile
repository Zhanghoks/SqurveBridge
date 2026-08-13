# Node 22 across every stage: jsdom pulls an undici that calls
# webidl.util.markAsUncloneable, which does not exist before Node 22.
FROM node:22-bookworm-slim AS frontend
WORKDIR /build/demo-app
COPY demo-app/package.json demo-app/package-lock.json ./
RUN npm ci
COPY demo-app/ ./
COPY config/ /build/config/
COPY reproduce/configs/ /build/reproduce/configs/
# Tests run in the workflow's own frontend job; the image only produces assets.
RUN npm run build

FROM node:22-bookworm-slim AS pi-sdk
WORKDIR /build/demo
COPY demo/package.json demo/package-lock.json ./
RUN npm ci --ignore-scripts

FROM node:22-bookworm-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    SQURVE_DEPLOYMENT_TARGET=hf-space
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
COPY . /app
COPY --from=frontend /build/demo-app/dist /app/demo-app/dist
COPY --from=pi-sdk /build/demo/node_modules /app/demo/node_modules
RUN python /app/tools/benchmarks.py download all \
    && python /app/tools/extract_space_assets.py --archive-root benchmarks/packages --output-root /app/benchmarks \
    && rm -f /app/benchmarks/packages/*.zip
RUN python -m pip install --upgrade pip \
    && python -m pip install -r deploy/huggingface/requirements.txt \
    && python demo/runtime_check.py \
    && chmod +x deploy/huggingface/entrypoint.sh \
    && mkdir -p /app/workspace \
    && chown -R node:node /app
USER node
EXPOSE 7860
RUN node --version && python --version
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl --fail http://127.0.0.1:7860/api/health || exit 1
ENTRYPOINT ["/app/deploy/huggingface/entrypoint.sh"]
