FROM python:3.11-slim

WORKDIR /app

# Install system fonts for QR card typography
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        fonts-dejavu-extra \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
