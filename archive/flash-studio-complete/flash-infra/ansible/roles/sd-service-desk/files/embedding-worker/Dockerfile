FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn==0.34.0 \
    httpx==0.28.0 \
    redis==5.2.0 \
    qdrant-client==1.14.0 \
    pytest \
    typesense==0.21.0 \
    tiktoken==0.9.0 \
    pydantic==2.10.0

COPY . .

EXPOSE 8093

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8093"]
