# ---------- Stage 1: Build ----------
FROM debian:bookworm-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential git cmake libcurl4-openssl-dev \
 && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/ggerganov/llama.cpp.git && \
    cd llama.cpp && \
    cmake -B build \
      -DCMAKE_BUILD_TYPE=Release \
      -DGGML_NATIVE=ON \
      -DLLAMA_CURL=ON \
      -DLLAMA_SERVER=ON \
    && cmake --build build -j$(nproc)

# ---------- Stage 2: Llama runtime ----------
FROM debian:bookworm-slim AS llama-runtime

RUN apt-get update && apt-get install -y \
    libgomp1 libcurl4 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server

COPY --from=builder /app/llama.cpp/build/bin/lib*.so* /usr/lib/

RUN ldconfig

EXPOSE 8080

CMD ["llama-server"]

# ---------- Stage 3: Telegram bot ----------
FROM python:3.11-slim-bookworm AS bot-runtime
WORKDIR /app

RUN pip install --no-cache-dir \
    "python-telegram-bot[job-queue]" pytz requests pydantic aiohttp pandas matplotlib

COPY main.py .

CMD ["python", "main.py"]
