FROM python:3.11-slim

# system libs needed by opencv-headless / pymupdf at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py batch_scan.py scan_form.py template_config.py prepare_template.py capture.html ./
COPY markers ./markers
COPY output ./output

RUN mkdir -p uploads crops

# runs as non-root
RUN useradd -m scanner && chown -R scanner:scanner /app
USER scanner

EXPOSE 5001

# gunicorn = production WSGI server. app.py's __main__ dev server block is
# only used for local testing, not this container.
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "--timeout", "60", "app:app"]
