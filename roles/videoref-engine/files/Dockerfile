FROM python:3.12-slim-bookworm

# ffmpeg + ffprobe for keyframe extraction and motion analysis
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps: aiohttp (API), watchfiles (fs watch), Pillow + numpy (color extraction)
RUN pip install --no-cache-dir aiohttp watchfiles Pillow numpy

COPY app.py /app/app.py

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=30s \
    CMD wget -qO- http://127.0.0.1:8082/health || exit 1

CMD ["python", "app.py"]
