# Multiple Packet Uplink Latency Decomposition

This tool enables the measurement and analysis of uplink latency components in 5G networks, specifically for scenarios involving multiple packet transmissions from client to server.

## Overview

This system consists of three main components:

1. **AWS Server (`aws_server_udp.py`)**: A server deployed on AWS that receives data packets from the client, measures timing, and collects measurement data
2. **Phone Client (`phone_client_udp.py`)**: A UDP client that runs on a mobile device and sends large data packets to the server
3. **Local Server (`local_server.py`)**: A server running on a local machine that provides time synchronization between the phone client and AWS server

Unlike the downlink scenario, in uplink measurement the AWS server is responsible for collecting and recording the measurement data as it receives packets from the client.

## Components

### AWS Server (`aws_server_udp.py`)

The AWS UDP server listens for large data payloads from clients, processes them, and records measurement data.

Features:
- Processing of multi-packet requests
- Precise timing measurements for packet arrival
- Recording of transmission statistics
- Collection and storage of measurement data
- Acknowledgment of received packets

### Phone Client (`phone_client_udp.py`)

The phone client sends large data payloads to the AWS server.

Features:
- Configurable packet sizes for testing different uplink scenarios
- Automatic segmentation of large payloads into multiple UDP packets
- Timestamps sent along with data for latency calculation
- Status reporting of transmission progress

### Local Server (`local_server.py`)

The local server facilitates accurate latency measurement by handling time synchronization.

Features:
- Provides timestamp synchronization
- Enables clock alignment between client and server
- Ensures measurement accuracy across devices

## Usage

### 1. Start the AWS Server

Deploy the AWS server script on your AWS instance:

```bash
python3 aws_server_udp.py
```

### 2. Start the Local Server

Start the local server on your computer for time synchronization:

```bash
python3 local_server.py --aws-ip <AWS_SERVER_IP> --requests 100 --bytes 20000
```

Parameters:
- `--aws-ip`: IP address of the AWS server (required)
- `--requests`: Number of requests to send (default: 100)
- `--bytes`: Size of request data in bytes (default: 1000)

### 3. Run the Phone Client

Execute the client on your mobile device:

```bash
python3 phone_client_udp.py --aws-ip <AWS_SERVER_IP>
```

Parameters:
- `--aws-ip`: IP address of the AWS server (required)
- `--local-ip`: IP address of the local server (default: 127.0.0.1)

## Output and Analysis

The AWS server saves the measurement data to files on the server side. The recorded data includes:
- Request ID
- Timestamp when transmission started
- Timestamp when all packets were received
- Uplink transmission delay
- Packet size information
- Number of segments received

## Example

To perform a test with 100 requests and 20KB request packets:

1. Start the AWS server: `python3 aws_server_udp.py`
2. Start the local server: `python3 local_server.py --aws-ip 18.88.0.144`
3. Run the client: `python3 phone_client_udp.py --aws-ip 18.88.0.144 --requests 100 --bytes 20000`

The test will measure the uplink latency for 100 large packet transmissions. Results will be stored on the AWS server for further analysis.
