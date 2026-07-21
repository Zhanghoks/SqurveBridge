FROM node:20-bookworm-slim AS frontend
WORKDIR /build/demo-app
COPY demo-app/package.json demo-app/package-lock.json ./
RUN npm ci
COPY demo-app/ ./
COPY config/ /build/config/
COPY reproduce/configs/ /build/reproduce/configs/
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
    SQURVE_DEPLOYMENT_TARGET=hf-space
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git git-lfs python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
COPY . /app
COPY --from=frontend /build/demo-app/dist /app/demo-app/dist
COPY --from=pi-builder /build/pi /app/pi
RUN GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Zhanghoks/SqurveBridge.git /tmp/squrvebridge-assets \
    && cd /tmp/squrvebridge-assets \
    && git lfs pull --include="benchmarks/packages/*.zip" \
    && python /app/tools/extract_space_assets.py --archive-root benchmarks/packages --output-root /app/benchmarks \
    && rm -rf /tmp/squrvebridge-assets
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
