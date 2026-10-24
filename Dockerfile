FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# Deno is the JavaScript runtime yt-dlp uses to solve YouTube's challenges (with yt-dlp-ejs).
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

# PUID/PGID 0 so a NAS share is writable without setup; set them to run as another user.
ENV WMF_MUSIC_DIR=/music WMF_DATA_DIR=/data PUID=0 PGID=0
VOLUME ["/music", "/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ.get(\"WMF_PORT\",\"8080\")}/healthz', timeout=3)"

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["python", "-m", "webmusicfolder.main"]
