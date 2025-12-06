set -e

NUM_CHUNKS=5

CONFIG_MAX_CHUNKS=$(python -c "
import json
import os
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = os.getenv('CONFIG_PATH')
with open(CONFIG_PATH) as f:
    config = json.load(f)
print(config['processing']['number_of_chunks'])
")

if [ $NUM_CHUNKS -gt $CONFIG_MAX_CHUNKS ]; then
    echo "ERROR: NUM_CHUNKS ($NUM_CHUNKS) exceeds config maximum ($CONFIG_MAX_CHUNKS)"
    exit 1
fi

if [ $NUM_CHUNKS -lt 1 ]; then
    echo "ERROR: NUM_CHUNKS must be at least 1"
    exit 1
fi

PIDS=()
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

for i in $(seq 0 $((NUM_CHUNKS - 1))); do
    python src/main.py --chunk-id $i > "$LOG_DIR/chunk_$i.log" 2>&1 &
    PIDS+=($!)
done

FAILED=0
FAILED_CHUNKS=()

for i in "${!PIDS[@]}"; do
    wait ${PIDS[$i]}
    EXIT_CODE=$?
    if [ $EXIT_CODE -ne 0 ]; then
        FAILED=1
        FAILED_CHUNKS+=($i)
    fi
done

if [ $FAILED -eq 1 ]; then
    echo "ERROR: ${#FAILED_CHUNKS[@]} chunk(s) failed: ${FAILED_CHUNKS[*]}"
    exit 1
fi

python merge_chunks.py

if [ $? -ne 0 ]; then
    echo "Merge failed"
    exit 1
fi