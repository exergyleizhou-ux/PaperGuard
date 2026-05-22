# PaperGuard — multi-arch Docker image
# Built and pushed for linux/amd64 + linux/arm64 to ghcr.io on every release tag.
# Usage:
#   docker run --rm -v "$PWD:/data" \
#       ghcr.io/exergyleizhou-ux/paperguard:latest scan -f /data/paper.pdf

FROM python:3.12-slim

WORKDIR /app

# Native deps needed at runtime by opencv / pymupdf / pdfplumber. Kept minimal:
# - libglib2.0-0 / libgl1: opencv runtime
# - libgomp1: scipy / numpy
# - ca-certificates: outbound HTTPS for fetcher modules
# - tzdata: timezone-aware timestamp handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Cache pip layer: copy only the dep-declaring files first.
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src/ ./src/

# Install with all production extras (webui + industrial + legacy-doc)
# so the image is useful out of the box. Slim users can build their own
# image with `pip install paperguard` for academic-only.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[webui,industrial,legacy-doc]" \
       types-openpyxl

ENV PYTHONIOENCODING=utf-8 \
    PAPERGUARD_HOME=/root/.paperguard

# User data lives on a mount.
VOLUME /data
VOLUME /root/.paperguard
WORKDIR /data

EXPOSE 8765

# Default entrypoint is the CLI; `docker run paperguard <subcommand>` works.
ENTRYPOINT ["paperguard"]
CMD ["--help"]

LABEL org.opencontainers.image.source="https://github.com/exergyleizhou-ux/PaperGuard" \
      org.opencontainers.image.description="Research-data integrity triage — 37 detectors, 12 industrial sectors" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.authors="PaperGuard Contributors"
