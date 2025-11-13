FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/staticfiles /app/media /app/logs
RUN adduser --disabled-password celeryuser
USER celeryuser

COPY . .

# Для ASGI (Channels)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "orthodox_dating.asgi:application"]

