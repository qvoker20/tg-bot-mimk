#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   DB_NAME=erp DB_USER=postgres DB_HOST=127.0.0.1 DB_PORT=5432 ./postgres_backup.sh

DB_NAME="${DB_NAME:-erp}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/erp-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$BACKUP_DIR/${DB_NAME}_${TS}.sql.gz"

pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" | gzip > "$OUT_FILE"

# Cleanup old backups
find "$BACKUP_DIR" -type f -name "${DB_NAME}_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete

echo "Backup created: $OUT_FILE"
