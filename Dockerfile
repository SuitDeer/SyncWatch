FROM python:3-alpine

RUN pip install --no-cache-dir flask requests

WORKDIR /app
COPY app.py .

EXPOSE 8080
CMD ["python", "-u", "app.py"]
