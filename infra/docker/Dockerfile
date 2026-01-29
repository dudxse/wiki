# Builder stage to convert requirements.lock to requirements.txt if needed 
# or just install directly. To keep it simple and robust:
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-root user
RUN addgroup --system appgroup && adduser --system --group appuser

# Install dependencies from lockfile
# We copy requirements.lock and ignore requirements.txt for reproducible builds
COPY requirements.lock ./
# We can install directly from requirements.lock if it's formatted for pip
# If it's a uv/poetry lock, we might need a different approach.
# Assuming standard pip freeze > requirements.lock format based on file view:
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

# Set permissions for the non-root user
RUN chown -R appuser:appgroup /app
RUN chmod +x infra/docker/entrypoint.sh

# Switch to non-root user
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/infra/docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
