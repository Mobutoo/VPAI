FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn==0.34.0 \
    sentence-transformers==3.4.0 \
    torch==2.6.0 --extra-index-url https://download.pytorch.org/whl/cpu \
    pydantic==2.10.0

COPY . .

EXPOSE 8090

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
