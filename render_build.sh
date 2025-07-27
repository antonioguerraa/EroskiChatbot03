#!/bin/bash
# Build script for Render deployment

echo "🚀 Starting Render build process..."

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p data/dictionary_cache
mkdir -p public

# Set permissions
echo "🔒 Setting permissions..."
chmod +x chainlit_app.py

echo "✅ Build complete!"