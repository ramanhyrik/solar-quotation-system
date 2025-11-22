#!/usr/bin/env bash
# Build script for Render deployment

# Install system dependencies required for matplotlib and PDF generation
apt-get update
apt-get install -y \
    gcc \
    g++ \
    libfreetype6-dev \
    libpng-dev \
    pkg-config \
    fontconfig \
    fonts-dejavu-core

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
