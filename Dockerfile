FROM python:3.10-slim

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency definitions and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files into the container
COPY . .

RUN pip install --no-cache-dir -e .

# Expose port as defined in start_web.sh (port 5001)
EXPOSE 5001

# Set environment variables for production if necessary
ENV FLASK_ENV=production
ENV TEMPLATE_DIR=/app/user_levels/death_house

# Set working directory
WORKDIR /app/webapp

# Start the Flask application.
CMD ["python", "app.py"]