# 5G Network RTT Measurement Tool

A tool for measuring Round-Trip Time (RTT) in 5G networks, including a UDP client and local server that support chunked transmission of large messages.

## System Components

- `phone_client_udp.py`: UDP client for sending requests to a remote server and measuring RTT
- `aws_server_udp.py`: UDP server for receiving client requests and sending responses
- `local_server.py`: Local TCP server for receiving RTT data from the client and saving it to a file

## Running Instructions

### 1. Start the Local Server (Optional)

The local server receives and saves RTT measurement data:

```bash
python3 local_server.py
```

### 2. Start the UDP Client

Use the following command to start the client and connect to the UDP server:

```bash
python3 phone_client_udp.py --server_ip <SERVER_IP> [options]
```

Example:

```bash
python3 phone_client_udp.py --server_ip 18.88.0.144 --count 10 --request_size 20000 --response_size 20000
```

## Parameter Description

The client supports the following command-line parameters:

| Parameter | Description | Default Value |
|-----------|-------------|---------------|
| `--server_ip` | Server IP address (required) | - |
| `--server_port` | Server UDP port | 5000 |
| `--request_size` | Request packet size (bytes) | 100 |
| `--response_size` | Response packet size (bytes) | 100 |
| `--interval` | Request interval (milliseconds) | 1000 |
| `--count` | Number of requests to send | 10 |
| `--timeout` | Timeout (seconds) | 1 |
| `--local_server` | Local server IP address | 127.0.0.1 |
| `--local_port` | Local server port | 5001 |
| `--no_local_server` | Disable local server connection | false |

## Example Command Explanation

```bash
python3 phone_client_udp.py --server_ip 18.88.0.144 --count 10 --request_size 20000 --response_size 20000
```

This command will:
- Connect to a server with IP `18.88.0.144`
- Send 10 requests (`--count 10`)
- Set each request size to 20000 bytes (`--request_size 20000`)
- Set each response size to 20000 bytes (`--response_size 20000`)
- Use the default request interval of 1000 milliseconds
- Connect to the local server (default 127.0.0.1:5001) to save results

## Output Description

Client output includes:
- Request sending information
- Response receiving information
- RTT measurement results

The local server generates result files named in the format:
```
rtt_req<request_size>_resp<response_size>_<timestamp>.txt
```

The file contains the following columns:
- Request ID: The identifier of the request
- RTT (ms): The measured round-trip time in milliseconds
- Req Size: Request size in bytes
- Resp Size: Response size in bytes
