#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
AWS_SERVER_DATA_PORT = 5002     # Port for data communication
LOCAL_SERVER_IP = '127.0.0.1'   # Local server IP address
LOCAL_SERVER_PORT = 5001        # Local server port for data forwarding

# Global variables
aws_data_socket = None          # TCP connection to AWS server for data
local_server_socket = None      # TCP connection to local server
running = True                  # Flag to control thread execution

def connect_to_aws_data_server(aws_server_ip):
    """Establish TCP connection to AWS server for data communication"""
    global aws_data_socket
    
    try:
        # Create TCP socket
        aws_data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Disable Nagle algorithm
        aws_data_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        aws_data_socket.connect((aws_server_ip, AWS_SERVER_DATA_PORT))
        print(f"Connected to AWS data server at {aws_server_ip}:{AWS_SERVER_DATA_PORT}")
        return True
    except Exception as e:
        print(f"Failed to connect to AWS data server: {e}")
        return False

def connect_to_local_server(local_ip):
    """Establish TCP connection to local server for data forwarding"""
    global local_server_socket
    
    try:
        # Create TCP socket
        local_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Disable Nagle algorithm
        local_server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        local_server_socket.connect((local_ip, LOCAL_SERVER_PORT))
        print(f"Connected to local server at {local_ip}:{LOCAL_SERVER_PORT}")
        return True
    except Exception as e:
        print(f"Failed to connect to local server: {e}")
        return False

def receive_data_from_server(num_requests, interval_ms, bytes_per_request):
    """Receive data from AWS server using trigger approach and output timestamps"""
    global aws_data_socket, local_server_socket, running
    
    try:
        # Send parameters to server
        # num_requests, interval_ms, bytes_per_request
        params = struct.pack('!iii', num_requests, interval_ms, bytes_per_request)
        aws_data_socket.sendall(params)
        
        print(f"Sent parameters to server: requests={num_requests}, interval={interval_ms}ms, bytes={bytes_per_request}")
        
        # Receive acknowledgment
        ack = aws_data_socket.recv(3)
        if ack != b'ACK':
            print(f"Did not receive proper acknowledgment from server: {ack}")
            return False
            
        print("Server acknowledged parameters, ready to send trigger packets...")
        
        # Statistics tracking
        request_count = 0
        
        while request_count < num_requests and running:
            # Send trigger packet to request data
            aws_data_socket.sendall(b'TRIG')
            print(f"Sent trigger packet for request {request_count+1}/{num_requests}")
            
            # First receive the header which contains timestamp and packet size
            # Format: !dI = 8-byte double + 4-byte unsigned int = 12 bytes total
            header = aws_data_socket.recv(12)
            if not header or len(header) < 12:
                if not header:
                    print("Connection closed by server")
                else:
                    print(f"Incomplete header received: {len(header)} bytes, expected 12 bytes")
                break
            
            # Parse the header to get timestamp and packet size
            server_timestamp, packet_size = struct.unpack('!dI', header)
            
            # Record the time when header is received
            receive_time = time.time()
            
            # Output timestamps without correction
            print(f"Request {request_count+1}: Local timestamp: {receive_time:.6f}, Server timestamp: {server_timestamp:.6f}")
            print(f"Time difference: {(receive_time - server_timestamp)*1000:.2f} ms")
            
            # Forward header to local server
            if local_server_socket:
                try:
                    # Send header to local server
                    local_server_socket.sendall(header)
                    print(f"Forwarded header to local server: {len(header)} bytes")
                except Exception as e:
                    print(f"Error forwarding header to local server: {e}")
            
            # Now receive the actual packet data
            remaining_bytes = packet_size
            received_packet = bytearray()
            
            while remaining_bytes > 0 and running:
                chunk = aws_data_socket.recv(min(4096, remaining_bytes))
                if not chunk:
                    print("Connection closed by server during packet reception")
                    break
                received_packet.extend(chunk)
                remaining_bytes -= len(chunk)
            
            # If we received the complete packet
            if len(received_packet) == packet_size:
                request_count += 1
                packet_receive_time = time.time()
                duration_ms = (packet_receive_time - receive_time) * 1000
                print(f"Packet fully received. Duration: {duration_ms:.2f} ms, packet size: {packet_size} bytes")
                
                # Send duration to local server
                if local_server_socket:
                    try:
                        # Pack duration as a double (8 bytes)
                        duration_bytes = struct.pack('d', duration_ms)
                        local_server_socket.sendall(duration_bytes)
                        print(f"Sent reception duration to local server: {duration_ms:.2f} ms")
                    except Exception as e:
                        print(f"Error sending duration to local server: {e}")
                
                print("-" * 50)
            else:
                print(f"Incomplete packet: received {len(received_packet)}/{packet_size} bytes")
                
            # Sleep for the specified interval before sending the next trigger
            if request_count < num_requests:
                interval_sec = interval_ms / 1000.0
                time.sleep(interval_sec)
        
        # Print summary
        if request_count > 0:
            print(f"\nReceived {request_count}/{num_requests} requests")
        
        return request_count == num_requests
    
    except Exception as e:
        print(f"Error receiving data from server: {e}")
        return False

def main():
    global aws_data_socket, local_server_socket, running
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Phone client for latency decomposition')
    parser.add_argument('--aws-ip', dest='aws_server_ip', required=True,
                        help='IP address of the AWS server')
    parser.add_argument('--local-ip', dest='local_server_ip', default=LOCAL_SERVER_IP,
                        help=f'IP address of the local server (default: {LOCAL_SERVER_IP})')
    parser.add_argument('--requests', type=int, default=100,
                        help='Number of requests to receive (default: 100)')
    parser.add_argument('--interval', type=int, default=1000,
                        help='Interval between requests in milliseconds (default: 1000)')
    parser.add_argument('--bytes', type=int, default=0,
                        help='Number of bytes per request (default: 0)')
    args = parser.parse_args()
    
    try:
        # Connect to AWS server for data communication
        if not connect_to_aws_data_server(args.aws_server_ip):
            print("Failed to connect to AWS data server, exiting...")
            running = False
            return
        
        # Connect to local server for data forwarding
        connect_to_local_server(args.local_server_ip)
        # Continue even if local server connection fails
        
        # Start data reception
        receive_data_from_server(args.requests, args.interval, args.bytes)
        
    except KeyboardInterrupt:
        print("Exiting...")
        running = False
    finally:
        # Close connections
        if aws_data_socket:
            aws_data_socket.close()
        if local_server_socket:
            local_server_socket.close()

if __name__ == "__main__":
    main()
