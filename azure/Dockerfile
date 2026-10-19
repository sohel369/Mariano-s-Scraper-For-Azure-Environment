FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set non-interactive and working directory
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY . /app/

# Create output and staging volumes
RUN mkdir -p /app/data/staging /app/data/output /app/data/checkpoints

# Default command: Run Mariano's production scraper
ENTRYPOINT ["python", "scripts/run_scraper.py"]
CMD ["--zipcode", "60601", "--max-pages", "5"]
