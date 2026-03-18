FROM python:3.12-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir aiohttp watchfiles

COPY app.py /app/app.py

EXPOSE 8082

CMD ["python", "app.py"]
