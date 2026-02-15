FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    speedtest-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

ENV ADMIN_USER=admin
ENV ADMIN_PASS=admin
ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
