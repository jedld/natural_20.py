FROM python:3.10-slim

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency definitions and install
COPY requirements.txt .

# Install Gunicorn and other dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn eventlet

# Copy all project files into the container
COPY . .

RUN pip install --no-cache-dir -e .

# Set default port (can be overridden during container start)
ENV PORT=5000

# Expose port from environment variable
EXPOSE ${PORT}

# Set environment variables for production if necessary
ENV FLASK_ENV=production
ENV TEMPLATE_DIR=/app/user_levels/death_house

# Set working directory
WORKDIR /app/webapp

# Start using Gunicorn with eventlet worker (for socketio support)
CMD gunicorn --worker-class eventlet --workers 4 --bind 0.0.0.0:${PORT} --timeout 120 app:app