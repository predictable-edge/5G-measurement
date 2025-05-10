# 5G Network Latency Measurement System

This repository contains a comprehensive system for measuring and analyzing 5G network latency in commercial environments. The system supports both downlink (server-to-phone) and uplink (phone-to-server) measurements with configurable packet sizes.

## System Overview

The system consists of the following components:

1. **AWS Server (UDP)**: Receives requests from the phone and sends responses of configurable size
2. **Phone Client (UDP)**: Sends requests to the AWS server and receives responses
3. **Local Server (TCP)**: Collects RTT (Round-Trip Time) measurements from the phone and saves them to files

The system supports:
- Configurable request and response sizes
- Chunked transmission for large packets
- Precise RTT measurement
- Structured data collection for analysis

## Prerequisites

- Python 3.6 or higher
- Android device with 5G connectivity
- Android Debug Bridge (ADB) installed on your computer
- AWS account (for deploying the server component)

## Setup Instructions

### 1. Install ADB

ADB (Android Debug Bridge) is required to forward ports between your computer and Android device.

#### For macOS:
```bash
brew install android-platform-tools
```

#### For Ubuntu/Debian:
```bash
sudo apt-get install adb
```

#### For Windows:
Download and install the [Android SDK Platform Tools](https://developer.android.com/studio/releases/platform-tools).

### 2. Connect Your Android Device

1. Enable USB debugging on your Android device (Settings → Developer options → USB debugging)
2. Connect the device to your computer via USB
3. Verify the connection:
```bash
adb devices
```

### 3. Set Up Port Forwarding

This critical step forwards TCP port 5001 from your Android device to your computer:

```bash
adb reverse tcp:5001 tcp:5001
```

### 4. Deploy AWS Server (Use DL latency decomposition as an example)

1. Launch an EC2 instance with a public IP address
2. Upload the `aws_server_udp.py` script to the instance
3. Run the server:
```bash
python3 aws_server_udp.py
```

### 5. Run Local Server

The local server collects measurement data from the phone client:

```bash
python3 local_server.py
```

### 6. Run Phone Client

Transfer the `phone_client_udp.py` script to your Android device and run:

```bash
python3 phone_client_udp.py --server_ip <AWS_SERVER_IP> --request_size <SIZE> --response_size <SIZE>
```