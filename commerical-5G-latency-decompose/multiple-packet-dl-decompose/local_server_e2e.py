#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
AWS_SERVER_IP_PORT = 5000       # Port for timestamp service
AWS_SERVER_DATA_PORT = 5002     # Port for data communication
TIME_SYNC_INTERVAL = 1          # Sync time with AWS server every second
LOCAL_IP = '0.0.0.0'            # Listen on all interfaces

# Global variables
time_offset = 0.0               # Time difference between client and AWS server
last_sync_time = 0              # Last time we synced with AWS server
aws_time_socket = None          # TCP connection to AWS server for time sync
aws_data_socket = None          # TCP connection to AWS server for data
running = True                  # Flag to control thread execution
measurement_count = 0           # Counter for measurements

def connect_to_aws_time_server(aws_server_ip):
    """Establish TCP connection to AWS server for time synchronization"""
    global aws_time_socket
    
    while True:
        try:
            # Create TCP socket
            aws_time_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            aws_time_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            aws_time_socket.connect((aws_server_ip, AWS_SERVER_IP_PORT))
            print(f"Connected to AWS time server at {aws_server_ip}:{AWS_SERVER_IP_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to AWS time server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

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

def sync_with_aws_server(aws_server_ip):
    """Periodically sync time with AWS server"""
    global time_offset, last_sync_time, aws_time_socket, running
    
    while running:
        try:
            # Ensure we have a connection
            if aws_time_socket is None:
                connect_to_aws_time_server(aws_server_ip)
                
            send_time = time.time()
            
            # Send empty packet as request to AWS server
            aws_time_socket.sendall(b'x')  # Send a single byte as request
            
            # Receive response from AWS server
            data = aws_time_socket.recv(1024)
            if not data:
                # Connection closed, try to reconnect
                print("AWS server connection closed, reconnecting...")
                aws_time_socket.close()
                aws_time_socket = None
                connect_to_aws_time_server(aws_server_ip)
                continue
                
            receive_time = time.time()
            
            # Unpack timestamp from response
            server_time = struct.unpack('d', data)[0]
            rtt = receive_time - send_time
            
            # Calculate one-way delay (assuming symmetric network)
            one_way_delay = rtt / 2
            
            # Calculate time offset (difference between our time and server time)
            # Adjusted for the one-way delay
            offset = server_time - (send_time + one_way_delay)
            
            time_offset = offset
            last_sync_time = time.time()
                
            print(f"Synced with AWS server - Offset: {offset:.6f}s, RTT: {rtt*1000:.2f}ms")
            
            # Wait for next sync interval
            time.sleep(TIME_SYNC_INTERVAL)
            
        except Exception as e:
            print(f"Error syncing with AWS server: {e}")
            # Close socket and try to reconnect next time
            if aws_time_socket:
                aws_time_socket.close()
                aws_time_socket = None
            time.sleep(1)  # Wait before retrying

def receive_data_from_server(num_requests, interval_ms):
    """Receive data from AWS server and calculate transmission delay using time offset"""
    global aws_data_socket, running, time_offset, measurement_count
    
    try:
        # Send parameters to server
        # num_requests, interval_ms, bytes_per_request
        bytes_per_request = 0  # 1000 bytes per request
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
        total_bytes_received = 0
        total_dl_delay = 0
        
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
            header_recv_time = time.time()
            
            # Apply our time offset to convert to local time
            corrected_server_time = server_timestamp - time_offset
            
            # Calculate transmission delay (server to client)
            dl_transmission_delay = header_recv_time - corrected_server_time
            
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
                total_bytes_received += packet_size
                total_dl_delay += dl_transmission_delay
                measurement_count += 1
                
                print(f"Received request {request_count}/{num_requests}: " +
                      f"{packet_size} bytes, DL transmission delay: {dl_transmission_delay*1000:.2f} ms")
            else:
                print(f"Incomplete packet: received {len(received_packet)}/{packet_size} bytes")
                
            # Sleep for the specified interval before sending the next trigger
            if request_count < num_requests:
                interval_sec = interval_ms / 1000.0
                time.sleep(interval_sec)
        
        # Print summary
        if request_count > 0:
            avg_dl_delay = total_dl_delay / request_count
            print(f"\nReceived {request_count}/{num_requests} requests")
            print(f"Total bytes: {total_bytes_received}")
            print(f"Average DL transmission delay: {avg_dl_delay*1000:.2f} ms")
        
        return request_count == num_requests
    
    except Exception as e:
        print(f"Error receiving data from server: {e}")
        return False

def main():
    global aws_time_socket, aws_data_socket, running
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Local server end-to-end for latency decomposition')
    parser.add_argument('--aws-ip', dest='aws_server_ip', required=True,
                        help='IP address of the AWS server')
    parser.add_argument('--requests', type=int, default=30,
                        help='Number of requests to receive (default: 30)')
    parser.add_argument('--interval', type=int, default=1000,
                        help='Interval between requests in milliseconds (default: 1000)')
    args = parser.parse_args()
    
    try:
        # Connect to AWS server for time synchronization
        connect_to_aws_time_server(args.aws_server_ip)
        
        # Start thread for AWS server time sync
        aws_sync_thread = threading.Thread(
            target=sync_with_aws_server, 
            args=(args.aws_server_ip,), 
            daemon=True
        )
        aws_sync_thread.start()
        
        # Give some time for initial time sync
        print("Waiting for initial time synchronization...")
        time.sleep(2)
        
        # Connect to AWS server for data communication
        if not connect_to_aws_data_server(args.aws_server_ip):
            print("Failed to connect to AWS data server, exiting...")
            running = False
            return
        
        # Start thread for data reception
        data_thread = threading.Thread(
            target=receive_data_from_server,
            args=(args.requests, args.interval),
            daemon=True
        )
        data_thread.start()
        
        # Keep the main thread running
        try:
            while running and (aws_sync_thread.is_alive() or data_thread.is_alive()):
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...")
            running = False
    finally:
        # Close connections
        if aws_time_socket:
            aws_time_socket.close()
        if aws_data_socket:
            aws_data_socket.close()

if __name__ == "__main__":
    main()
