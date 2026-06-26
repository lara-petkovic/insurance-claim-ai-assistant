FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=prod \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY config ./config

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
