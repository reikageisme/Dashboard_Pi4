FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including systemd for journalctl and docker client
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    systemd \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
# Note: rpi-lgpio might fail on non-Pi architectures during build, 
# so we might need to handle that or user ensures they are on a Pi.
# We interpret 'rpi-lgpio' as a candidate. Alternatively we can rely on system packages if base was a Pi OS.
# For now, we attempt to install requirements.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
