# Vi opgraderer til Python 3.11 for at understøtte nyeste uvicorn
FROM python:3.11-slim

# Sæt arbejdsmappen i containeren
WORKDIR /app

# Kopier requirements filen først (for bedre caching)
COPY requirements.txt .

# Installer afhængigheder
RUN pip install --no-cache-dir -r requirements.txt

# Kopier resten af koden
COPY . .

# Kommandoen der starter applikationen
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT