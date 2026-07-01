# Fargate corre en amd64 por defecto: fijamos la plataforma para builds desde Mac ARM.
FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 80
CMD ["python", "app.py"]
