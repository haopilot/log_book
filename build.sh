#!/usr/bin/env bash
# Build script for Render.com deployment

set -o errexit  # Exit on error

# Install Python dependencies
pip install -r requirements.txt

# Create data directory if it doesn't exist
mkdir -p data

# Download airport database if it doesn't exist
if [ ! -f data/airports.csv ]; then
    echo "Downloading airport database..."
    curl -o data/airports.csv https://davidmegginson.github.io/ourairports-data/airports.csv
    echo "Airport database downloaded successfully"
else
    echo "Airport database already exists"
fi

echo "Build completed successfully"
