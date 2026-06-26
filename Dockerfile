# Isolated build env — quantfit never touches your global Python.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# torch from the CUDA wheel index first, then the package (build-isolation off so
# llm-compressor / gptqmodel see the installed torch).
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu124 && \
    pip3 install --no-cache-dir --no-build-isolation .

ENTRYPOINT ["quantfit"]
CMD ["--help"]
