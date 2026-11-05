#!/usr/bin/env bash
# Backup the OpenFeedback database and attachments.
#
# The database and the attachments must be backed up together: an attachment
# row without its file is a broken record.
set -euo pipefail

DATA_DIR="${OF_DATA_DIR:-/var/lib/openfeedback}"
BACKUP_DIR="${OF_BACKUP_DIR:-/var/backups/openfeedback}"
KEEP_DAYS="${OF_BACKUP_KEEP_DAYS:-7}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/$STAMP"

mkdir -p "$TARGET"

# SQLite's own backup API produces a consistent copy even while the service
# is writing; copying the file directly could capture a torn page.
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DATA_DIR/openfeedback.db" ".backup '$TARGET/openfeedback.db'"
else
  echo "sqlite3 not found; falling back to a plain copy" >&2
  cp "$DATA_DIR/openfeedback.db" "$TARGET/openfeedback.db"
fi

if [ -d "$DATA_DIR/attachments" ]; then
  cp -a "$DATA_DIR/attachments" "$TARGET/attachments"
fi

tar -C "$BACKUP_DIR" -czf "$BACKUP_DIR/openfeedback-$STAMP.tar.gz" "$STAMP"
rm -rf "$TARGET"

# Keep the newest N daily backups.
find "$BACKUP_DIR" -name 'openfeedback-*.tar.gz' -type f -mtime "+$KEEP_DAYS" -delete

echo "backup written: $BACKUP_DIR/openfeedback-$STAMP.tar.gz"
