#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
AWS_SERVER_IP_PORT = 5000       # Port for timestamp service
TIME_SYNC_INTERVAL = 1          # Expected sync interval from AWS server
PHONE_LISTEN_IP = '0.0.0.0'     # Listen on all interfaces for phone connection
PHONE_LISTEN_PORT = 5001        # Port for sending data to phone client via UDP
PACKET_INTERVAL = 1           # Time between sending packets (seconds)

# Global variables
aws_time_socket = None          # TCP connection to AWS server for time sync
running = True                  # Flag to control thread execution
phone_client_address = None     # Address of the phone client for UDP
phone_udp_socket = None         # UDP socket for phone client communication
num_requests = 10               # Number of requests to send
bytes_per_request = 1           # Number of bytes per request
should_send = False             # Flag to control sending

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

def listen_for_aws_sync():
    """Listen for time sync packets from AWS server and respond"""
    global aws_time_socket, running
    
    try:
        while running:
            try:
                # Wait for timestamp from AWS server
                data = aws_time_socket.recv(8)  # Expect an 8-byte double
                if not data or len(data) < 8:
                    # Connection closed or invalid data
                    if not data:
                        print("AWS server connection closed, reconnecting...")
                    else:
                        print(f"Received invalid data from AWS server: {len(data)} bytes, expected 8")
                    
                    # Try to reconnect
                    aws_time_socket.close()
                    aws_time_socket = None
                    break
                
                # Unpack server timestamp
                server_timestamp = struct.unpack('!d', data)[0]
                
                # Send our current time back to server
                client_timestamp = time.time()
                response = struct.pack('!d', client_timestamp)
                aws_time_socket.sendall(response)
                
                print(f"Received sync from AWS - Server time: {server_timestamp:.6f}, responded with: {client_timestamp:.6f}")
                
            except socket.timeout:
                # Socket timeout, just continue the loop
                continue
            except ConnectionError as e:
                print(f"Connection error with AWS server: {e}")
                aws_time_socket.close()
                aws_time_socket = None
                break
            except Exception as e:
                print(f"Error handling AWS sync: {e}")
                time.sleep(1)  # Avoid tight loop
    
    except Exception as e:
        print(f"Error in AWS sync listener: {e}")
        
    finally:
        # Handle reconnection in the main thread
        if not aws_time_socket and running:
            print("AWS sync listener exited, will reconnect")

def maintain_aws_connection(aws_server_ip):
    """Maintain connection to AWS server and handle reconnections"""
    global aws_time_socket, running
    
    while running:
        if aws_time_socket is None:
            # Need to connect/reconnect
            connect_to_aws_time_server(aws_server_ip)
            
            # Start a new thread to listen for time sync from AWS
            sync_thread = threading.Thread(
                target=listen_for_aws_sync,
                daemon=True
            )
            sync_thread.start()
        
        # Check periodically if we need to reconnect
        time.sleep(5)

def handle_phone_client(client_address):
    """Send data packets to phone client via UDP"""
    global phone_client_address, running, num_requests, bytes_per_request, phone_udp_socket
    
    try:
        # Store the client address globally
        phone_client_address = client_address
        
        print(f"Phone client registered from {client_address}")
        
        # Send data in this thread
        requests_sent = 0
        
        while running and requests_sent < num_requests:
            try:
                # Create request ID (1-based)
                request_id = requests_sent + 1
                
                # Get current timestamp
                timestamp = time.time()
                
                # Create header: request_id (4 bytes), size (4 bytes), timestamp (8 bytes)
                header = struct.pack('!IId', request_id, bytes_per_request, timestamp)
                
                # Send the header via UDP
                try:
                    phone_udp_socket.sendto(header, client_address)
                    requests_sent += 1
                    print(f"Sent request {request_id}/{num_requests} to phone client - timestamp: {timestamp:.6f}")
                except Exception as e:
                    print(f"Error sending UDP packet to phone client: {e}")
                    break
                
                # Sleep before sending next packet
                time.sleep(PACKET_INTERVAL)
                
            except Exception as e:
                print(f"Error sending data to phone client: {e}")
                time.sleep(1)  # Avoid tight loop on error
        
        print(f"Completed sending {requests_sent}/{num_requests} requests to phone client")
            
    except Exception as e:
        print(f"Error handling phone client {client_address}: {e}")
    finally:
        time.sleep(1)
        # Reset global address if this is the current client
        if phone_client_address == client_address:
            phone_client_address = None

def listen_for_phone_clients():
    """Listen for phone client registration via UDP"""
    global phone_udp_socket, phone_client_address
    
    # Create UDP socket for phone clients
    phone_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    phone_udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    phone_udp_socket.bind((PHONE_LISTEN_IP, PHONE_LISTEN_PORT))
    
    print(f"Listening for phone clients on UDP {PHONE_LISTEN_IP}:{PHONE_LISTEN_PORT}")
    
    try:
        while running:
            # Wait for a registration message from phone client
            data, client_address = phone_udp_socket.recvfrom(1024)
            
            # Simple registration protocol - expecting "REGISTER" message
            if data == b'REGISTER':
                print(f"Received registration from phone client: {client_address}")
                
                # Respond with acknowledgment
                phone_udp_socket.sendto(b'ACK', client_address)
                
                # Handle this client in a thread
                client_thread = threading.Thread(
                    target=handle_phone_client,
                    args=(client_address,)
                )
                client_thread.daemon = True
                client_thread.start()
            else:
                print(f"Received unexpected data from {client_address}: {data}")
    
    except KeyboardInterrupt:
        print("Phone server shutting down...")
    except Exception as e:
        print(f"Error in UDP listener: {e}")
    finally:
        if phone_udp_socket:
            phone_udp_socket.close()

def main():
    global aws_time_socket, running, num_requests, bytes_per_request, PACKET_INTERVAL
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Time synchronization client for AWS server')
    parser.add_argument('--aws-ip', dest='aws_server_ip', required=True,
                        help='IP address of the AWS server')
    parser.add_argument('--requests', type=int, default=10,
                        help='Number of requests to send to phone client (default: 10)')
    parser.add_argument('--bytes', type=int, default=1,
                        help='Size in bytes (for information only, no payload is sent)')
    parser.add_argument('--interval', type=int, default=1000,
                        help='Interval between packets in milliseconds (default: 1000)')
    args = parser.parse_args()
    
    # Update request parameters
    num_requests = args.requests
    bytes_per_request = args.bytes
    # Convert interval from milliseconds to seconds
    PACKET_INTERVAL = args.interval / 1000.0
    
    try:
        # Start thread to maintain AWS server connection
        aws_thread = threading.Thread(
            target=maintain_aws_connection,
            args=(args.aws_server_ip,),
            daemon=True
        )
        aws_thread.start()
        
        # Start thread for listening for phone connections
        phone_listen_thread = threading.Thread(
            target=listen_for_phone_clients,
            daemon=True
        )
        phone_listen_thread.start()
        
        print(f"Local server running, responding to time sync requests from AWS server")
        print(f"Ready to send {num_requests} requests with header information to phone clients")
        print(f"Listening for phone clients on UDP port {PHONE_LISTEN_PORT}")
        print("Press Ctrl+C to exit")
        
        # Keep the main thread running
        try:
            while running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...")
            running = False
    finally:
        # Close connections
        if aws_time_socket:
            aws_time_socket.close()

if __name__ == "__main__":
    main()
