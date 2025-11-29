# Use newer Python to avoid "End of Life" warnings
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Run with Gunicorn (2 workers is safe for Free Tier)
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]