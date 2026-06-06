#!/bin/bash
set -e

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-arcgis_docs}"

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

collection_info=$(wget -q -O- "${QDRANT_URL}/collections/${QDRANT_COLLECTION}" 2>/dev/null || true)
points_count=$(echo "$collection_info" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('result', {}).get('points_count', 0))" 2>/dev/null || echo "0")

if [ "$points_count" -gt 0 ]; then
    echo "[init] Collection '${QDRANT_COLLECTION}' already has ${points_count} points, skipping ingestion"
    exit 0
fi

echo "[init] Running build_index.py..."
python /app/scripts/build_index.py --source arcpro --concurrency 5 --delay 0.2

echo "[init] Running load_qdrant.py..."
python /app/scripts/load_qdrant.py --source arcpro --recreate --batch-size 100

echo "[init] Ingestion complete"
