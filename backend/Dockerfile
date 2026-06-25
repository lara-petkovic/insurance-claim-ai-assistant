FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements ./requirements
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY src ./src

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
