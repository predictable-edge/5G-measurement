#!/bin/bash

# Exit on error
set -e

echo "Starting environment setup for video streaming client..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "Homebrew is already installed"
fi

# Update Homebrew
echo "Updating Homebrew..."
brew update

# Install FFmpeg with all necessary options
echo "Installing FFmpeg..."
brew install ffmpeg

# Install pkg-config if not already installed
if ! command -v pkg-config &> /dev/null; then
    echo "Installing pkg-config..."
    brew install pkg-config
fi

# Create necessary directories
echo "Creating result directory..."
mkdir -p result

# Set permissions for the script
chmod +x env_install.sh

echo "Environment setup completed successfully!"
echo "You can now compile the code using 'make'"
