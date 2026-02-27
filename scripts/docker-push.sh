#!/usr/bin/env bash
# ============================================================
# docker-push.sh — Build multi-arch e push su Docker Hub
# Repository: mccoy88f/planarallyplus
# Uso: ./scripts/docker-push.sh [TAG]
#   TAG  (opzionale) — default: "latest"
#        Esempi: latest, dev, v1.2.0
# ============================================================

set -euo pipefail

IMAGE="mccoy88f/planarallyplus"
TAG="${1:-latest}"
PLATFORMS="linux/amd64,linux/arm64"
BUILDER_NAME="planarallyplus-builder"

echo "=============================================="
echo "  Build multi-arch Docker image"
echo "  Image  : ${IMAGE}:${TAG}"
echo "  Piattaforme: ${PLATFORMS}"
echo "=============================================="

# 1. Controlla che buildx sia disponibile
if ! docker buildx version &>/dev/null; then
  echo "❌ docker buildx non trovato. Aggiorna Docker Desktop o installa il plugin buildx."
  exit 1
fi

# 2. Crea (o riusa) un builder multi-arch
if ! docker buildx inspect "${BUILDER_NAME}" &>/dev/null; then
  echo "→ Creazione builder buildx '${BUILDER_NAME}'..."
  docker buildx create --name "${BUILDER_NAME}" --driver docker-container --bootstrap
else
  echo "→ Builder '${BUILDER_NAME}' già esistente, lo riuso."
fi

docker buildx use "${BUILDER_NAME}"

# 3. Login Docker Hub (salta se già loggati)
echo "→ Verifica login Docker Hub..."
if ! docker info 2>/dev/null | grep -q "Username"; then
  docker login
fi

# 4. Build e push
echo "→ Build e push in corso (può richiedere diversi minuti)..."
docker buildx build \
  --platform "${PLATFORMS}" \
  --tag "${IMAGE}:${TAG}" \
  --build-arg DOCKER_TAG="${TAG}" \
  --push \
  .

echo ""
echo "✅ Immagine pubblicata con successo!"
echo "   https://hub.docker.com/r/mccoy88f/planarallyplus"
echo "   Tag: ${TAG}"
