FROM python:3.12-slim

WORKDIR /app

# Install Docker CLI (for docker mode)
RUN apt-get update && apt-get install -y \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy application
COPY . .

# Install app
RUN pip install --no-cache-dir -e .

# Default command
ENTRYPOINT ["bb-run"]
CMD ["--help"]