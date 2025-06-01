# 5G Latency Measurement System

This system consists of three main components for measuring 5G uplink latency:

## Components

### 1. `lz_server.py` - Time Synchronization Server
Provides timestamp service for time synchronization requests.

**Features:**
- TCP-based timestamp service
- Responds to client requests with current server time
- Supports multiple client connections
- Simple stateless design

**Usage:**
```bash
python3 lz_server.py
```

### 2. `edge_server.py` - Edge Data Server
Receives UDP data packets and handles ping-pong measurements.

**Features:**
- UDP data reception and analysis
- Ping-pong latency measurements
- Result logging with timestamps
- No time synchronization functionality

**Usage:**
```bash
python3 edge_server.py
```

### 3. `local_pc.py` - Client Application
Sends data to edge server and synchronizes time with LZ server.

**Features:**
- Time synchronization with LZ server via WiFi
- Local calculation and storage of time offset
- Data transmission to edge server via mobile interface
- UDP ping-pong testing
- Configurable payload sizes and intervals

**Usage:**
```bash
python3 local_pc.py --cloud-ip <EDGE_SERVER_IP> --lz-ip <LZ_SERVER_IP> --wifi-ip <WIFI_IP> --mobile-ip <MOBILE_IP>
```

## Setup Instructions

1. **Start the Time Synchronization Server:**
   ```bash
   python3 lz_server.py
   ```

2. **Start the Edge Server:**
   ```bash
   python3 edge_server.py
   ```

3. **Run the Client:**
   ```bash
   # List available network interfaces
   python3 local_pc.py --list-interfaces
   
   # Run with specific parameters
   python3 local_pc.py \
     --cloud-ip 192.168.1.100 \
     --lz-ip 192.168.1.200 \
     --wifi-ip 192.168.1.5 \
     --mobile-ip 10.0.0.5 \
     --requests 100 \
     --bytes 1024 \
     --interval 500
   ```

## Parameter Descriptions

- `--cloud-ip`: IP address of the edge server (for data transmission)
- `--lz-ip`: IP address of the LZ server (for time synchronization)
- `--wifi-ip`: Local WiFi interface IP (used for time sync with LZ server)
- `--mobile-ip`: Local mobile interface IP (used for data transmission to edge server)
- `--requests`: Number of data packets to send (default: 10)
- `--bytes`: Size of each data packet in bytes (default: 1)
- `--interval`: Interval between packets in milliseconds (default: 1000)
- `--no-ping-pong`: Disable ping-pong latency testing

## Network Architecture

```
[Local PC] ----WiFi----> [LZ Server] (Time Sync)
    |
    +------Mobile-----> [Edge Server] (Data + Ping-Pong)
```

## Time Synchronization Process

1. **Client-Initiated Sync**: Local PC initiates synchronization requests to LZ server
2. **Timestamp Request**: Client sends a request to LZ server
3. **Timestamp Response**: LZ server responds with current server timestamp
4. **Local Offset Calculation**: Client calculates time offset and RTT locally
5. **Local Storage**: Time offset is stored and maintained by the client
6. **Synchronized Timestamps**: Client uses synchronized time for data transmission

## Key Features

- **Client-Side Time Management**: Time offset calculation and storage handled by local PC
- **Stateless LZ Server**: LZ server simply provides timestamps without maintaining client state
- **Enhanced Client Configuration**: Added `--lz-ip` parameter for time sync server
- **Interface Binding**: Client can bind to specific network interfaces for different functions
- **Simplified Edge Server**: Focuses only on data reception and ping-pong measurements

## Output Files

The edge server generates result files with naming pattern:
`ul_udp_bytes{SIZE}_{TIMESTAMP}.txt`

Results include:
- Index
- Uplink delay (ms)
- Transfer duration (ms)  
- Packet size (bytes) 