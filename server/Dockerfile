FROM python:3.12-slim
WORKDIR /app/server
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ .
COPY client/client.py /app/client/client.py
COPY docs/ /app/docs/
EXPOSE 15000
CMD ["python3", "-u", "server.py"]
