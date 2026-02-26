#!/usr/bin/env bash
# Build script for Render.com deployment

set -o errexit  # Exit on error

# Install system dependencies (Tesseract OCR for logbook scanning)
echo "Installing Tesseract OCR..."
apt-get update && apt-get install -y tesseract-ocr || echo "Warning: Could not install Tesseract (may already be installed or need sudo)"

# Install Python dependencies
pip install -r requirements.txt

# Ensure latest CA certificates for SSL connections (FlightAware API)
pip install --upgrade certifi

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
