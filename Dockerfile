# ---------- STAGE 1: CLONE ----------
FROM alpine/git AS CLONER
# Default dev: main su GitHub può essere indietro rispetto al lockfile/patches. Override: --build-arg PA_GIT_REF=main
ARG PA_GIT_REF=dev
WORKDIR /usr/src

# forza rebuild quando cambiano i commit sul branch scelto
ADD https://api.github.com/repos/mccoy88f/PlanarAllyPlus/commits/${PA_GIT_REF} /dev/null

RUN git clone --depth=1 --branch "${PA_GIT_REF}" https://github.com/mccoy88f/PlanarAllyPlus.git .

# ---------- STAGE 2: BUILD CLIENT ----------
FROM node:24-alpine AS BUILDER

# python3/make/g++: build moduli nativi (es. bufferutil); git: alcuni pacchetti;
# libc6-compat: compatibilità binari precompilati (musl vs glibc) su Alpine.
RUN apk add --no-cache python3 make g++ git libc6-compat

WORKDIR /usr/src/client

COPY --from=CLONER /usr/src/client/package.json .
COPY --from=CLONER /usr/src/client/package-lock.json .
# Necessario per postinstall → patch-package (vue3-pdf-app); senza cartella la patch non si applica.
COPY --from=CLONER /usr/src/client/patches ./patches

# Evita ERESOLVE su npm 10+ in ambiente CI/Alpine (stesso effetto di npm install --legacy-peer-deps)
ENV NPM_CONFIG_LEGACY_PEER_DEPS=true
# Host con poca RAM (Portainer/NAS): npm ci può uscire con 1 senza messaggio chiaro se OOM.
ENV NODE_OPTIONS=--max-old-space-size=6144

RUN npm ci --no-audit --no-fund && npm cache clean --force

COPY --from=CLONER /usr/src /usr/src

RUN npm run build

# ---------- STAGE 3: FINAL IMAGE ----------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

EXPOSE 8000

WORKDIR /planarally

# crea cartelle necessarie
RUN mkdir -p /planarally/data \
    /planarally/static/assets \
    /planarally/static/mods \
    /planarally/static/temp/dungeons \
    /planarally/extensions \
    && chown -R 9000:9000 /planarally

ENV PYTHONUNBUFFERED=1
ENV UV_CACHE_DIR=/planarally/.uv
ENV USERNAME=planarally
ENV PA_BASEPATH=/

# dipendenze sistema
RUN apt-get update && apt-get install --no-install-recommends -y \
    dumb-init \
    curl \
    libffi-dev \
    libssl-dev \
    gcc \
    libegl1 \
    libgl1 \
    libgles2-mesa \
    && rm -rf /var/lib/apt/lists/*

USER 9000

# copia backend
COPY --from=BUILDER --chown=9000:9000 /usr/src/server/pyproject.toml .
COPY --from=BUILDER --chown=9000:9000 /usr/src/server/uv.lock .

RUN uv sync --frozen --no-cache

COPY --from=BUILDER --chown=9000:9000 /usr/src/server/ .
COPY --from=BUILDER --chown=9000:9000 /usr/src/extensions ./extensions

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["uv", "run", "planarally.py"]
