# ---------- STAGE 1: CLONE ----------
FROM alpine/git AS CLONER
WORKDIR /usr/src

# forza rebuild quando cambiano i commit
ADD https://api.github.com/repos/mccoy88f/PlanarAllyPlus/commits/main /dev/null

RUN git clone --depth=1 --branch main https://github.com/mccoy88f/PlanarAllyPlus.git .

# ---------- STAGE 2: BUILD CLIENT ----------
FROM node:24-alpine AS BUILDER

RUN apk add --no-cache python3 make g++

WORKDIR /usr/src/client

COPY --from=CLONER /usr/src/client/package.json .
COPY --from=CLONER /usr/src/client/package-lock.json .

RUN npm ci && npm cache clean --force

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
