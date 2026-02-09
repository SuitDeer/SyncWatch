FROM python:3-alpine

RUN pip install --no-cache-dir flask requests gunicorn

WORKDIR /app
COPY app.py .

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "2", "app:app"]