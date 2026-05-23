FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

# Java runtime required by opendataloader-pdf
RUN apt-get update && apt-get install -y --no-install-recommends default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8088
CMD ["python", "app.py"]
