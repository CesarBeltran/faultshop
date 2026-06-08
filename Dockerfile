FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y wget iputils-ping && rm -rf /var/lib/apt/lists/*
COPY . .
RUN sed -i 's/\r//' entrypoint.sh app.py init_db.py
RUN chmod +x entrypoint.sh
EXPOSE 5000
CMD ["sh", "entrypoint.sh"]
