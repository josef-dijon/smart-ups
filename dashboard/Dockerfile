FROM python:3.12-slim

# Create data directory for persistent SQLite database
RUN mkdir -p /data

# Set the working directory
WORKDIR /app

# Copy the server and dashboard assets
COPY index.html server.py ./

# Expose the server port
EXPOSE 8080

# Default configuration environment variables
ENV PORT=8080
ENV DB_PATH=/data/history.db
ENV PICO_UPS_URL=http://127.0.0.1:9999

# Start the Python unified API and static file server
CMD ["python", "server.py"]
