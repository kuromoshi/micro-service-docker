FROM python:3.11-slim

WORKDIR /app

RUN pip install flask requests flask-cors

COPY . .

EXPOSE 5001

CMD ["python", "app.py"]
