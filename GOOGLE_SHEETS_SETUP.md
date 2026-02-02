# Google Sheets Setup Guide

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click "Select a project" → "New Project"
3. Name it "Pilot Logbook" → Click "Create"

## Step 2: Enable Google Sheets API

1. In the Cloud Console, go to "APIs & Services" → "Library"
2. Search for "Google Sheets API"
3. Click on it → Click "Enable"

## Step 3: Create OAuth Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure OAuth consent screen:
   - User Type: External
   - App name: Pilot Logbook
   - User support email: your email
   - Developer contact: your email
   - Click "Save and Continue" (skip scopes, test users)
4. Back to Create OAuth client ID:
   - Application type: "Desktop app"
   - Name: "Pilot Logbook Desktop"
   - Click "Create"
5. Download the JSON file → Rename it to `credentials.json`

## Step 4: Create Google Sheet

1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new blank spreadsheet
3. Name it "Pilot Logbook"
4. Copy the Spreadsheet ID from the URL:
   - URL format: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`
   - Copy the `SPREADSHEET_ID` part

## Step 5: Configure Application

### For Local Development:
1. Place `credentials.json` in the project root directory
2. Update `.env`:
   ```
   GOOGLE_SHEETS_ID=your_spreadsheet_id_here
   ```

### For Render Deployment:
1. The credentials.json needs to be added as an environment variable
2. Add `GOOGLE_SHEETS_ID` in Render dashboard

## Step 6: First-time Authentication

The first time you sync, a browser window will open asking you to:
1. Select your Google account
2. Click "Advanced" → "Go to Pilot Logbook (unsafe)"
3. Click "Allow"

This creates a `token.pickle` file for future authentication.
