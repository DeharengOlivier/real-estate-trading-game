#!/bin/bash

# Real Estate Investing - Quick Start Script
# This script helps you get started with the Real Estate Investing

echo "Real Estate Investing - Quick Start"
echo "=================================="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Check if docker-compose is available
if ! command -v docker compose &> /dev/null; then
    echo "docker compose command not found. Please install Docker Compose."
    exit 1
fi

echo "✅ Docker Compose is available"
echo ""

# Offer to clean up previous containers
read -p "Do you want to clean up previous containers? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleaning up..."
    docker compose down -v
    echo ""
fi

# Build and start containers
echo "Building and starting containers..."
echo "This may take a few minutes on first run..."
echo ""

docker compose up --build

# Note: This script will keep running until you press Ctrl+C
# The containers will continue running in the foreground
