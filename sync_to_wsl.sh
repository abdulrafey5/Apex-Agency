#!/bin/bash
# Sync files from Windows mount to WSL root location
# Run this from WSL: bash sync_to_wsl.sh

WIN_LOCATION="/mnt/c/Users/dell/Apex-Agency"
WSL_LOCATION="$HOME/apex-agency"

echo "Syncing files from $WIN_LOCATION to $WSL_LOCATION..."

# Key files to sync
FILES=(
    "app/scripts/vectorize_marketing_department.py"
    "app/scripts/quick_env_test.py"
    "app/scripts/test_env_loading.py"
    "app/services/db_service.py"
    "app/.env"
    "app/services/document_ingestion_service.py"
    "app/services/embedding_service.py"
    "app/services/rag_service.py"
)

for file in "${FILES[@]}"; do
    win_file="$WIN_LOCATION/$file"
    wsl_file="$WSL_LOCATION/$file"
    
    if [ -f "$win_file" ]; then
        mkdir -p "$(dirname "$wsl_file")"
        cp -v "$win_file" "$wsl_file"
    else
        echo "⚠️  File not found: $win_file"
    fi
done

echo "✅ Sync complete!"

