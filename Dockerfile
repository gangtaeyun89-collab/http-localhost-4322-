FROM python:3.12-slim

# OS deps: only what we need (curl for healthcheck, build for any wheel that
# needs compiling). Cleaned in the same layer to keep the image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so they cache when only source changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project.
COPY . .

# SQLite + bot logs live here. Mounted to a Fly.io volume in production so
# state survives redeploys.
RUN mkdir -p /data
ENV POLYMARKET_DB_PATH=/data/polymarket.sqlite
ENV PYTHONPATH=/app

# Streamlit listens on 8080; Fly.io routes external traffic to that port.
EXPOSE 8080

# Run the entrypoint script that starts both the bot and the dashboard.
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
