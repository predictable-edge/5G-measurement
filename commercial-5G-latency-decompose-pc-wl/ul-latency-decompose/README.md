# 5G Latency Measurement System

This system consists of three main components for measuring 5G uplink latency:

## Components

### 1. `lz_server.py` - Time Synchronization Server
Provides centralized time synchronization service for accurate latency measurements.

**Features:**
- TCP-based time synchronization
- Calculates time offset between server and clients
- Supports multiple client connections

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
- No time synchronization (moved to lz_server.py)

**Usage:**
```bash
python3 edge_server.py
```

### 3. `local_pc.py` - Client Application
Sends data to edge server and synchronizes time with LZ server.

**Features:**
- Time synchronization with LZ server via WiFi
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

## Key Changes

- **Separated Time Synchronization**: Time sync functionality moved from `edge_server.py` to dedicated `lz_server.py`
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