#!/bin/bash
set -e

# Fix permissions for mounted volumes
# This script runs as root, fixes permissions, then switches to appuser

if [ -d "/app/storage" ]; then
    chown -R appuser:appuser /app/storage 2>/dev/null || true
    chmod -R 755 /app/storage 2>/dev/null || true
fi

if [ -d "/app/app/logs" ]; then
    chown -R appuser:appuser /app/app/logs 2>/dev/null || true
    chmod -R 755 /app/app/logs 2>/dev/null || true
fi

# Create required directories if they don't exist
mkdir -p /app/storage/chat_history/tasks
mkdir -p /app/storage/instructions/agents
chown -R appuser:appuser /app/storage 2>/dev/null || true
chmod -R 755 /app/storage 2>/dev/null || true

# Switch to appuser and execute the main command
exec gosu appuser "$@"

