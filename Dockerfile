FROM python:3.9-slim

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -r appuser

# Set working directory
WORKDIR /app

# Copy dependency definitions and install
COPY requirements.txt .

# Install Gunicorn and other dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn eventlet

# Copy all project files into the container
COPY . .

RUN pip install --no-cache-dir -e .

# Create and set permissions for flask_session directory
RUN mkdir -p /app/webapp/flask_session && \
    chown -R appuser:appuser /app/webapp/flask_session && \
    chmod 755 /app/webapp/flask_session

# Set default port (can be overridden during container start)
ENV PORT=80

# Expose port from environment variable
EXPOSE ${PORT}

# Set environment variables for production if necessary
ENV FLASK_ENV=production
ENV TEMPLATE_DIR=/app/templates
ENV FLASK_APP=webapp/app.py
ENV AWS_ENVIRONMENT=true

# Set working directory
WORKDIR /app/webapp

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Switch to non-root user
USER appuser

# Start using Gunicorn with eventlet worker (for socketio support)
CMD gunicorn --worker-class eventlet --workers 1 --bind 0.0.0.0:${PORT} --timeout 120 app:app