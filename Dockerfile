FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

# Healthcheck to verify local Modbus (if running all-in-one) or just script liveness
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import socket; socket.connect(('localhost', 502))" || exit 1

CMD ["python", "main.py"]
