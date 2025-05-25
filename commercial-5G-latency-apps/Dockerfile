# Based on Ubuntu 22.04
FROM ubuntu:22.04

# Set non-interactive mode to avoid prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /root

# Update package manager and install necessary tools
RUN apt-get update && apt-get install -y \
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
    && rm -rf /var/lib/apt/lists/*

# Clone 5G measurement project
RUN git clone https://github.com/predictable-edge/5G-measurement.git

# Set project working directory
WORKDIR /root/5G-measurement/commercial-5G-latency-apps/video-transcoding-rtp

# Add execute permissions to all shell scripts
RUN find . -name "*.sh" -type f -exec chmod +x {} \;

# Install server environment dependencies
WORKDIR /root/5G-measurement/commercial-5G-latency-apps/video-transcoding-rtp/client_streaming
RUN ./env_install.sh
RUN make

# Set final working directory
WORKDIR /root/5G-measurement/commercial-5G-latency-apps/video-transcoding-rtp/client_streaming

# Default command to keep container running
CMD ["tail", "-f", "/dev/null"]