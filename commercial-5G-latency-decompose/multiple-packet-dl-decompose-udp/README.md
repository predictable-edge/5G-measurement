# Multiple Packet Downlink Latency Decomposition

This tool allows for the measurement and analysis of downlink latency components in 5G networks, with a focus on handling multiple packet transmissions.

## Overview

This system consists of three main components:

1. **AWS Server (`aws_server_udp.py`)**: A server deployed on AWS that sends data packets to the client upon trigger
2. **Phone Client (`phone_client_udp.py`)**: A UDP client that runs on a mobile device, triggers packet transmission from the server, and measures timing
3. **Local Server (`local_server.py`)**: A server running on a local machine that collects measurement data from the phone client for analysis

The system is designed to decompose various factors that contribute to the overall latency experienced in 5G downlink transmissions, particularly when multiple packets are involved.

## Components

### AWS Server (`aws_server_udp.py`)

The AWS UDP server listens for trigger packets from clients, then responds with larger data payloads that may be split into multiple UDP packets.

Features:
- Configurable response packet size
- Support for multi-packet responses with proper segmentation
- Timestamp inclusion for precise timing analysis

### Phone Client (`phone_client_udp.py`)

The phone client sends trigger packets to the AWS server and measures the timing of the responses.

Features:
- Configurable number of requests
- Adjustable interval between requests
- Automatic handling of multi-packet responses
- Precise timing measurements
- Forwarding of timing data to local server

### Local Server (`local_server.py`)

The local server receives timing data from the phone client, allowing for later analysis on a more powerful device.

Features:
- Collects and saves measurement data
- Provides timestamp synchronization
- Logs complete transmission information

## Usage

### 1. Start the AWS Server

Deploy the AWS server script on your AWS instance:

```bash
python3 aws_server_udp.py
```

### 2. Start the Local Server

Start the local server on your computer:

```bash
python3 local_server.py --aws-ip <AWS_SERVER_IP>
```

### 3. Run the Phone Client

Execute the client on your mobile device:

```bash
python3 phone_client_udp.py --aws-ip <AWS_SERVER_IP> --requests 100 --bytes 20000
```

Parameters:
- `--aws-ip`: IP address of the AWS server (required)
- `--local-ip`: IP address of the local server (default: 127.0.0.1)
- `--requests`: Number of requests to send (default: 100)
- `--interval`: Interval between requests in milliseconds (default: 1000)
- `--bytes`: Size of response data in bytes (default: 0)

## Output and Analysis

The local server saves measurement data to a file with timestamp information. The output includes:
- Request counter
- DL transmission delay (server to phone)
- Reception duration on the phone
- Total observed latency
- Packet size
- Time synchronization information

## Example

To perform a test with 100 requests, 1-second intervals, and 20KB response packets:

1. Start the AWS server
2. Start the local server: `python3 local_server.py --aws-ip 18.88.0.144`
3. Run the client: `python3 phone_client_udp.py --aws-ip 18.88.0.144 --requests 100 --interval 1000 --bytes 20000`

The test will run for approximately 100 seconds (based on the interval) and save results to the local server.
