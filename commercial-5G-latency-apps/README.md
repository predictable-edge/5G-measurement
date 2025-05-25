# 5G Video Streaming Client

This project provides a containerized environment for running 5G video streaming measurement tools, specifically the client-side video streaming application from the [5G-measurement](https://github.com/predictable-edge/5G-measurement) repository.

## Prerequisites

- Docker Desktop installed and running on Windows
- Internet connection for downloading dependencies

## Deployment Options

There are two ways to set up and run the 5G video streaming client:

1. **Manual Setup** - Using a base Ubuntu container and manually installing dependencies
2. **Dockerfile** - Automated setup using a pre-configured Docker image

---

## Option 1: Manual Setup (Without Dockerfile)

### Step 1: Create and Run Base Container

```cmd
# Pull Ubuntu 22.04 image
docker pull ubuntu:22.04

# Create and run container with host networking
docker run -d --name 5g-client --network host ubuntu:22.04 tail -f /dev/null

# Enter the container
docker exec -it 5g-client /bin/bash
```

### Step 2: Install Dependencies

```bash
# Update package manager
apt-get update

# Install required tools
apt-get install -y net-tools inetutils-ping git gcc g++ make sudo curl wget vim

# Verify installation
ifconfig
ping google.com
```

### Step 3: Download and Setup Project

```bash
# Clone the project repository
cd /root
git clone https://github.com/predictable-edge/5G-measurement.git

# Navigate to project directory
cd 5G-measurement/commercial-5G-latency-apps/video-transcoding-rtp

# Make shell scripts executable
find . -name "*.sh" -type f -exec chmod +x {} \;
```

### Step 4: Install Server Dependencies

```bash
# Install server environment
cd server_transcoding
./env_install.sh
```

### Step 5: Compile Client

```bash
# Compile the client application
cd ../client_streaming
make
```

### Step 6: Run the Application

```bash
# Basic usage
./client_streaming

# With parameters (requires video file)
./client_streaming /path/to/video.mp4 rtp://SERVER_IP:9000 rtp://0.0.0.0:10000
```

---

## Option 2: Dockerfile (Automated Setup)

### Step 1: Create Dockerfile

Create a file named `dockerfile` (no extension) with the following content:

```dockerfile
# Based on Ubuntu 22.04
FROM ubuntu:22.04

# Set non-interactive mode to avoid prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install all dependencies in one layer to reduce build time
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
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /root

# Clone repository (this will be cached if repository doesn't change)
RUN git clone https://github.com/predictable-edge/5G-measurement.git

# Copy only the specific directories we need
WORKDIR /root/5G-measurement/commercial-5G-latency-apps/video-transcoding-rtp

# Add execute permissions to shell scripts
RUN find . -name "*.sh" -type f -exec chmod +x {} \;

# Install server dependencies and compile client in one step
RUN cd server_transcoding && ./env_install.sh && \
    cd ../client_streaming && make

# Set final working directory
WORKDIR /root/5G-measurement/commercial-5G-latency-apps/video-transcoding-rtp/client_streaming

# Keep container running
CMD ["tail", "-f", "/dev/null"]
```

### Step 2: Build Docker Image

```cmd
# Build the image (this may take 5-15 minutes on first build)
docker build -t 5g-video-client .

# Verify the image was created
docker images
```

### Step 3: Run Container

```cmd
# Stop and remove any existing container with the same name
docker stop 5g-client 2>/dev/null || true
docker rm 5g-client 2>/dev/null || true

# Run the container with host networking
docker run -d --name 5g-client --network host 5g-video-client

# Enter the container
docker exec -it 5g-client /bin/bash
```

### Step 4: Run the Application

```bash
# The application is already compiled and ready to use
./client_streaming

# With parameters
./client_streaming /root/video.mp4 rtp://SERVER_IP:9000 rtp://0.0.0.0:10000
```

---

## File Transfer

### Copy files from Windows to Container

```cmd
# Copy a video file to the container
docker cp C:\path\to\video.mp4 5g-client:/root/

# Copy entire folder
docker cp C:\path\to\folder 5g-client:/root/
```

### Copy files from Container to Windows

```cmd
# Copy files from container to Windows
docker cp 5g-client:/root/output.txt C:\Users\YourName\Desktop\
```

---

## Container Management

### Useful Commands

```cmd
# View running containers
docker ps

# View all containers
docker ps -a

# Stop container
docker stop 5g-client

# Start existing container
docker start 5g-client

# Remove container
docker rm 5g-client

# Remove image
docker rmi 5g-video-client

# View container logs
docker logs 5g-client
```

### Container Access

```cmd
# Enter running container
docker exec -it 5g-client /bin/bash

# Run single command in container
docker exec 5g-client ls -la /root

# Check container network information
docker exec 5g-client ifconfig
```

---

## Troubleshooting

### Common Issues

1. **Container won't start**: Ensure Docker Desktop is running
2. **Network issues**: Verify host networking mode is enabled
3. **Permission errors**: Run commands with sudo inside container if needed
4. **Build failures**: Check internet connection and try again

### Debugging

```cmd
# Check container status
docker inspect 5g-client

# View detailed build output
docker build --progress=plain -t 5g-video-client .

# Rebuild without cache
docker build --no-cache -t 5g-video-client .
```

---

## Notes

- **Host Networking**: The container uses `--network host` to share the host's network interface
- **Persistence**: Data inside the container is not persistent unless mounted or copied out
- **Performance**: First build takes longer; subsequent builds use Docker cache
- **Ports**: Ports 9000 and 10000 are exposed for RTP streaming

## Quick Start Summary

**For quick setup with Dockerfile:**
```cmd
# 1. Create dockerfile
# 2. Build image
docker build -t 5g-video-client .
# 3. Run container
docker run -d --name 5g-client --network host 5g-video-client
# 4. Enter container
docker exec -it 5g-client /bin/bash
# 5. Run application
./client_streaming
```