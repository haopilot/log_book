#!/usr/bin/env bash
# Build script for Render.com deployment

set -o errexit  # Exit on error

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

# Create service account file from environment variable if it exists
echo "Checking for GOOGLE_SERVICE_ACCOUNT_JSON environment variable..."
if [ -z "$GOOGLE_SERVICE_ACCOUNT_JSON" ]; then
    echo "WARNING: GOOGLE_SERVICE_ACCOUNT_JSON is not set or is empty"
else
    echo "Creating service account credentials from environment variable..."
    echo "$GOOGLE_SERVICE_ACCOUNT_JSON" > service-account.json
    echo "Service account credentials created successfully"
    # Verify file was created
    if [ -f service-account.json ]; then
        echo "Verified: service-account.json file exists"
    else
        echo "ERROR: service-account.json file was not created"
    fi
fi

echo "Build completed successfully"
