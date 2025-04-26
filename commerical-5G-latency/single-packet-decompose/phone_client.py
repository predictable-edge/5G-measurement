#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
AWS_SERVER_PORT = 5000       # Port for timestamp service
CLIENT_SERVER_PORT = 5001    # Port on client server to send data to

# Global variables
aws_socket = None            # TCP connection to AWS server
client_socket = None         # TCP connection to client server

def connect_to_aws_server(aws_server_ip):
    """Establish TCP connection to AWS server"""
    global aws_socket
    
    while True:
        try:
            # Create TCP socket
            aws_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            aws_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            aws_socket.connect((aws_server_ip, AWS_SERVER_PORT))
            print(f"Connected to AWS server at {aws_server_ip}:{AWS_SERVER_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to AWS server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

def connect_to_client_server(client_server_ip):
    """Establish TCP connection to client server"""
    global client_socket
    
    while True:
        try:
            # Create TCP socket
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client_socket.connect((client_server_ip, CLIENT_SERVER_PORT))
            print(f"Connected to client server at {client_server_ip}:{CLIENT_SERVER_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to client server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

def measure_rtt_and_report(aws_server_ip, client_server_ip, packet_size, measurement_interval):
    """Measure RTT to AWS server and report to client server"""
    global aws_socket, client_socket
    
    # Create a packet of specified size
    packet = b'x' * packet_size
    
    while True:
        try:
            # Ensure we have connections
            if aws_socket is None:
                connect_to_aws_server(aws_server_ip)
            if client_socket is None:
                connect_to_client_server(client_server_ip)
                
            # Record send time
            send_time = time.time()
            
            # Send packet to AWS server with specified size
            aws_socket.sendall(packet)
            
            # Receive response from AWS server - collect all data until we get expected size
            # The server will respond with at least packet_size bytes (or 8 bytes if packet_size < 8)
            expected_size = max(packet_size, 8)  # At least 8 bytes for timestamp
            
            chunks = []
            bytes_received = 0
            
            while bytes_received < expected_size:
                chunk = aws_socket.recv(2048)
                if not chunk:
                    # Connection closed
                    raise ConnectionError("AWS server connection closed during receive")
                    
                chunks.append(chunk)
                bytes_received += len(chunk)
                print(f"Received chunk: {len(chunk)} bytes, total: {bytes_received} bytes")
            
            # Combine all received chunks
            data = b''.join(chunks)
            
            # Record receive time
            receive_time = time.time()
            
            # Print data size for debugging
            print(f"Total data received: {len(data)} bytes (expected at least {expected_size} bytes)")
            
            # Calculate RTT
            rtt = receive_time - send_time
            
            # Make sure we have at least 8 bytes for the timestamp
            if len(data) < 8:
                print(f"Error: Received only {len(data)} bytes, need at least 8 bytes for timestamp")
                time.sleep(1)
                continue
                
            # Unpack timestamp from the first 8 bytes of response
            server_timestamp = struct.unpack('d', data[:8])[0]
            
            # Pack data to send to client server: server_timestamp, rtt, phone_receive_time
            report_data = struct.pack('ddd', server_timestamp, rtt, receive_time)
            
            try:
                # Send data to client server
                client_socket.sendall(report_data)
            except Exception as e:
                print(f"Error sending data to client server: {e}")
                # Try to reconnect
                client_socket.close()
                client_socket = None
                connect_to_client_server(client_server_ip)
                # Try to send again
                client_socket.sendall(report_data)
            
            print(f"RTT to AWS server: {rtt*1000:.2f}ms, reported to client server")
            
            # Wait for next measurement interval
            time.sleep(measurement_interval)
            
        except Exception as e:
            print(f"Error measuring RTT: {e}")
            # Close sockets if there was an error
            if aws_socket:
                try:
                    aws_socket.close()
                except:
                    pass
                aws_socket = None
            time.sleep(1)  # Wait before retrying

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Phone client for latency measurement")
    parser.add_argument("--aws-ip", default="18.88.35.208", help="AWS server IP address")
    parser.add_argument("--client-ip", default="0.0.0.0", help="Client server IP address")
    parser.add_argument("--packet-size", type=int, default=1, help="Size of packet to send to AWS server (max 1400 bytes)", choices=range(1, 1401))
    parser.add_argument("--interval", type=float, default=1.0, help="Measurement interval in seconds")
    args = parser.parse_args()
    
    # Configuration from command-line arguments
    aws_server_ip = args.aws_ip
    client_server_ip = args.client_ip
    packet_size = args.packet_size
    measurement_interval = args.interval
    
    print(f"Starting Samsung phone RTT measurement app")
    print(f"AWS Server: {aws_server_ip}:{AWS_SERVER_PORT}")
    print(f"Client Server: {client_server_ip}:{CLIENT_SERVER_PORT}")
    print(f"Packet Size: {packet_size} bytes")
    print(f"Measurement Interval: {measurement_interval} seconds")
    
    # Connect to servers
    connect_to_aws_server(aws_server_ip)
    connect_to_client_server(client_server_ip)
    
    # Start thread for RTT measurement
    rtt_thread = threading.Thread(
        target=measure_rtt_and_report, 
        args=(
            aws_server_ip, 
            client_server_ip, 
            packet_size, 
            measurement_interval
        ),
        daemon=True
    )
    rtt_thread.start()
    
    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
        if aws_socket:
            aws_socket.close()
        if client_socket:
            client_socket.close()

if __name__ == "__main__":
    main()