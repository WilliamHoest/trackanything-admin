# Use Python 3.9 slim image for smaller size
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies without cache to keep image small
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway will set the PORT env variable)
EXPOSE $PORT

# Run uvicorn server
# Railway provides $PORT environment variable dynamically
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
