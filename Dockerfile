FROM python:3-alpine

RUN pip install --no-cache-dir flask requests

WORKDIR /app
COPY app.py .
COPY chart4.5.0.min.js.js .

EXPOSE 8080
CMD ["python", "-u", "app.py"]
