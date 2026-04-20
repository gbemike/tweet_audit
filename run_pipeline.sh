#!/usr/bin/env bash
set -e

NUM_CHUNKS=5

# Fetch config
CONFIG_MAX_CHUNKS=$(poetry run python -c "
import json
import os
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = os.getenv('CONFIG_PATH')
with open(CONFIG_PATH) as f:
    config = json.load(f)
print(config['processing']['number_of_chunks'])
")

if [ "$NUM_CHUNKS" -gt "$CONFIG_MAX_CHUNKS" ]; then
    echo "ERROR: NUM_CHUNKS ($NUM_CHUNKS) exceeds config maximum ($CONFIG_MAX_CHUNKS)"
    exit 1
fi

if [ "$NUM_CHUNKS" -lt 1 ]; then
    echo "ERROR: NUM_CHUNKS must be at least 1"
    exit 1
fi

PIDS=()
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

for i in $(seq 0 $((NUM_CHUNKS - 1))); do
    poetry run python src/main.py --chunk-id "$i" > "$LOG_DIR/chunk_$i.log" 2>&1 &
    PIDS+=($!)
done

FAILED=0
FAILED_CHUNKS=()

for i in "${!PIDS[@]}"; do
    wait "${PIDS[$i]}" || EXIT_CODE=$?
    
    if [ "${EXIT_CODE:-0}" -ne 0 ]; then
        FAILED=1
        FAILED_CHUNKS+=("$i")
    fi
    unset EXIT_CODE
done

echo "Running merge..."
poetry run python src/merge_chunks.py

if [ $FAILED -eq 1 ]; then
    echo "WARNING: ${#FAILED_CHUNKS[@]} chunk(s) failed: ${FAILED_CHUNKS[*]}"
    echo "Partial merge completed with successful chunks."
    echo "Re-run the pipeline to retry failed chunks."
    exit 1
else
    echo "Success: All chunks processed and merged."
fi