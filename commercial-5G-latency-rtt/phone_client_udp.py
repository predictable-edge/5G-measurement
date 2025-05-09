import argparse
import socket
import struct
import time
import random

# Maximum UDP packet size (practically safe)
MAX_UDP_PACKET = 8192
# UDP port for data communication
UDP_PORT = 5000

# Message types
MSG_TYPE_CONTROL = 1
MSG_TYPE_REQUEST = 2

# Global request counter
request_counter = 0

def parse_arguments():
    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser(description='UDP Client for latency measurement')
    parser.add_argument('--server_ip', type=str, required=True, help='Server IP address')
    parser.add_argument('--server_port', type=int, default=UDP_PORT, help=f'Server UDP port (default: {UDP_PORT})')
    parser.add_argument('--request_size', type=int, default=100, help='Request size in bytes (default: 100)')
    parser.add_argument('--response_size', type=int, default=100, help='Response size in bytes (default: 100)')
    parser.add_argument('--interval', type=int, default=1000, help='Request interval in ms (default: 1000)')
    parser.add_argument('--count', type=int, default=10, help='Number of requests to send (default: 10)')
    parser.add_argument('--timeout', type=int, default=5, help='Socket timeout in seconds (default: 5)')
    
    return parser.parse_args()

def send_control_message(sock, server_address, request_size, response_size):
    """
    Send control message to server and wait for ACK
    
    Args:
        sock: UDP socket
        server_address: Server address tuple (ip, port)
        request_size: Size of request packets
        response_size: Size of response packets
    
    Returns:
        bool: True if ACK received successfully, False otherwise
    """
    try:
        # Pack control message: type(1) + request_size(4) + response_size(4)
        control_message = struct.pack('!BII', MSG_TYPE_CONTROL, request_size, response_size)
        
        # Send control message
        sock.sendto(control_message, server_address)
        print(f"Sent control message - Request size: {request_size}, Response size: {response_size}")
        
        # Wait for ACK
        data, _ = sock.recvfrom(MAX_UDP_PACKET)
        if len(data) >= 1 and data[0] == MSG_TYPE_CONTROL:
            print("Received control ACK")
            return True
        else:
            print("Received unexpected message type")
            return False
            
    except (socket.timeout, struct.error) as e:
        print(f"Error in control message: {e}")
        return False

def send_request(sock, server_address, request_size):
    """
    Send request data to server
    
    Args:
        sock: UDP socket
        server_address: Server address tuple (ip, port)
        request_size: Size of request data to send
    
    Returns:
        bool: True if request sent successfully, False otherwise
    """
    global request_counter
    try:
        # Generate a request ID
        request_id = request_counter
        request_counter += 1
        
        # Calculate header size: type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
        header_size = 9
        
        # Calculate actual payload size
        payload_size = request_size - header_size
        if payload_size < 0:
            print(f"Error: Request size {request_size} is too small for header")
            return False
            
        # Calculate how many chunks we need
        max_chunk_payload = MAX_UDP_PACKET - header_size
        total_chunks = (payload_size + max_chunk_payload - 1) // max_chunk_payload
        total_chunks = max(1, total_chunks)  # At least 1 chunk
        
        print(f"Total request data length: {request_size} bytes, splitting into {total_chunks} chunks")
        
        # Split data into chunks and send
        remaining_payload = payload_size
        for chunk_id in range(total_chunks):
            # Calculate this chunk's payload size
            this_chunk_payload = min(max_chunk_payload, remaining_payload)
            
            # Pack the header: type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
            chunk_header = struct.pack('!BIHH', MSG_TYPE_REQUEST, request_id, chunk_id, total_chunks)
            
            # Create chunk data with header and payload
            chunk_data = chunk_header + b'0' * this_chunk_payload
            
            # Send the chunk
            sock.sendto(chunk_data, server_address)
            print(f"Sent chunk {chunk_id+1}/{total_chunks} of request {request_id}: {len(chunk_data)} bytes")
            
            # Update remaining payload
            remaining_payload -= this_chunk_payload
        
        return True
        
    except Exception as e:
        print(f"Error sending request: {e}")
        return False

def main():
    """
    Main function to start the client
    """
    args = parse_arguments()
    
    # Create UDP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(args.timeout)
    
    server_address = (args.server_ip, args.server_port)
    
    try:
        # Send control message and wait for ACK
        if not send_control_message(client_socket, server_address, args.request_size, args.response_size):
            print("Failed to establish connection with server")
            return
            
        print("Connection established with server")
        
        # Send requests
        for i in range(args.count):
            if not send_request(client_socket, server_address, args.request_size):
                print(f"Failed to send request {i+1}")
                continue
                
            print(f"Request {i+1}/{args.count} sent")
            
            # Wait for the specified interval
            if i < args.count - 1:  # Don't wait after the last request
                time.sleep(args.interval / 1000)  # Convert ms to seconds
        
    except KeyboardInterrupt:
        print("\nClient shutting down...")
    finally:
        client_socket.close()

if __name__ == "__main__":
    main()
