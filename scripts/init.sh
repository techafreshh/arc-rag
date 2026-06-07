#!/bin/bash
set -e

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-arcgis_docs}"
SOURCE="${SOURCE:-arcpro}"

echo "[init] (source=${SOURCE}) Starting ingestion"

echo "[init] Waiting for Qdrant at ${QDRANT_URL}..."
for i in $(seq 1 60); do
    status=$(wget -q -O- "${QDRANT_URL}/health" 2>/dev/null || true)
    if echo "$status" | grep -q '"status":"green"'; then
        echo "[init] Qdrant is healthy"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "[init] ERROR: Qdrant did not become healthy within 5 minutes"
        exit 1
    fi
    sleep 5
done

filter='{"filter":{"must":[{"key":"source","match":{"value":"'$SOURCE'"}}]}}'
source_count=$(wget -q -O- --post-data="$filter" --header="Content-Type: application/json" \
    "${QDRANT_URL}/collections/${QDRANT_COLLECTION}/points/count" 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('result', {}).get('count', 0))" 2>/dev/null || echo "0")

if [ "$source_count" -gt 0 ]; then
    echo "[init] Collection '${QDRANT_COLLECTION}' already has ${source_count} points with source='${SOURCE}', skipping ingestion"
    exit 0
fi

echo "[init] Running build_index.py (source=${SOURCE})..."
python /app/scripts/build_index.py --source "$SOURCE" --concurrency 5 --delay 0.2

echo "[init] Running load_qdrant.py (source=${SOURCE})..."
python /app/scripts/load_qdrant.py --source "$SOURCE" --batch-size 100

echo "[init] Ingestion complete for source=${SOURCE}"
