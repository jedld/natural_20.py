#!/bin/bash

# Start script optimized for ngrok usage
echo "Starting Natural20 webapp for ngrok..."

# Set environment variables for ngrok
export FLASK_ENV=development
export TEMPLATE_DIR=../templates
export CORS_ORIGINS="http://localhost:5000,http://127.0.0.1:5000,http://localhost:5001,http://127.0.0.1:5001,https://*.ngrok.io,https://*.ngrok-free.app"

# Start the Flask app
echo "Starting Flask app on port 5001..."
python -m flask run --host=0.0.0.0 --port=5001 --no-reload 