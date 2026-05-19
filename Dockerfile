FROM python:3.12-slim

WORKDIR /app

# Install build deps for opencv (only headless needed at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e ".[webui]" types-openpyxl

ENV PYTHONIOENCODING=utf-8

# 数据卷：用户挂载论文目录到 /data
VOLUME /data
VOLUME /root/.paperguard
WORKDIR /data

EXPOSE 8765

ENTRYPOINT ["paperguard"]
CMD ["--help"]
