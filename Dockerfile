# Vi opgraderer til Python 3.11 for at understøtte nyeste uvicorn
FROM python:3.11-slim

# Sæt arbejdsmappen i containeren
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Kopier requirements filen først (for bedre caching)
COPY requirements.txt .

# Installer afhængigheder
RUN pip install --no-cache-dir -r requirements.txt

# Installer Playwright browser binaries + Linux system dependencies
RUN playwright install --with-deps chromium

# Kopier resten af koden
COPY . .

# Kommandoen der starter applikationen
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
