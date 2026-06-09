FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY chat_demo.py server.py ./
COPY web ./web

# Platforms like Render/Railway/Fly override PORT; server binds 0.0.0.0 when set.
ENV PORT=8000
EXPOSE 8000

CMD ["python", "server.py"]
