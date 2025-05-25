apt-get update && apt-get install -y \
    net-tools \
    inetutils-ping \
    git \
    gcc \
    g++ \
    make \
    sudo \
    curl \
    wget \
    vim \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

git clone https://github.com/predictable-edge/5G-measurement.git

cd 5G-measurement/commercial-5G-latency-apps/video-transcoding-rtp/client_streaming

./env_install.sh

make