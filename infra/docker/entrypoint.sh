#!/bin/sh
set -e

# Wait for Postgres (simple check)
# In a real production environment, we might use a proper wait-for-it script
# or rely on the app's reconnection logic.
echo "Starting entrypoint..."

# Build DATABASE_URL if missing or pointing to localhost (container needs db hostname)
if [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_PASSWORD" ] && [ -n "$POSTGRES_DB" ]; then
  if [ -z "$DATABASE_URL" ] || echo "$DATABASE_URL" | grep -Eq "(localhost|127\\.0\\.0\\.1)"; then
    export DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}/${POSTGRES_DB}"
  fi
fi

# Run migrations
echo "Running migrations..."
alembic upgrade head

# Start application
echo "Starting application..."
exec "$@"
