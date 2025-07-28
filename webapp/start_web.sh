#!/bin/sh

# Use command-line argument as TEMPLATE_DIR if provided, otherwise use default
if [ -n "$1" ]; then
    TEMPLATE_DIR="$1"
else
    TEMPLATE_DIR="../templates"
fi

TEMPLATE_DIR="$TEMPLATE_DIR" python -m flask run --debug --host=0.0.0.0 --port=5001