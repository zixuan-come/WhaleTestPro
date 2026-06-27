FROM python:3.10-slim

WORKDIR /app

# 先单独拷 requirements，利用 Docker 层缓存：依赖没变就不重装，改源码不触发重装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷源码（变动频繁，放后面）
COPY . .

EXPOSE 8000

# 容器内监听 0.0.0.0（不是 127.0.0.1，否则容器外/别的容器连不进来）；不开 --reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
