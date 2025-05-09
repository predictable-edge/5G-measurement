import socket
import struct
import time
from collections import defaultdict

# Maximum UDP packet size (practically safe)
MAX_UDP_PACKET = 8192
# UDP port for data communication
UDP_PORT = 5000

# Message types
MSG_TYPE_CONTROL = 1
MSG_TYPE_REQUEST = 2

# Storage for received chunks
chunk_buffer = defaultdict(dict)  # {request_id: {chunk_id: data}}

def receive_large_message(sock, expected_size, max_packet_size=MAX_UDP_PACKET, timeout=5):
    """
    Receive a large message that might be split across multiple datagrams
    
    Args:
        sock: UDP socket
        expected_size: Expected total size of the message
        max_packet_size: Maximum size of each datagram
        timeout: Timeout in seconds for receiving each datagram
    
    Returns:
        tuple: (message_data, client_address) or (None, None) if timeout
    """
    try:
        # Set timeout for receiving datagrams
        sock.settimeout(timeout)
        
        # Receive first datagram
        data, client_address = sock.recvfrom(max_packet_size)
        current_size = len(data)
        received_data = data
        
        # If message is complete in one datagram
        if current_size >= expected_size:
            return received_data, client_address
            
        # Receive remaining datagrams
        while current_size < expected_size:
            try:
                data, _ = sock.recvfrom(max_packet_size)
                received_data += data
                current_size += len(data)
            except socket.timeout:
                print("Timeout while receiving message fragments")
                return None, None
                
        return received_data, client_address
        
    except socket.timeout as e:
        print(f"Error receiving message: {e}")
        return None, None
    finally:
        # Reset timeout to None (blocking)
        sock.settimeout(None)

def process_chunk(data, client_address):
    """
    Process a received chunk of data
    
    Args:
        data: The received chunk data
        client_address: The client address (ip, port)
    
    Returns:
        tuple: (is_complete, request_id) if all chunks received, otherwise (False, request_id)
    """
    try:
        # Ensure we have at least the header
        if len(data) < 9:  # type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
            print(f"Received too small chunk from {client_address}")
            return False, None
            
        # Unpack header: type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
        msg_type, request_id, chunk_id, total_chunks = struct.unpack('!BIHH', data[:9])
        
        if msg_type != MSG_TYPE_REQUEST:
            print(f"Received unexpected message type: {msg_type}")
            return False, None
        
        # Just record that we received this chunk - no need to store payload
        chunk_buffer[request_id][chunk_id] = True
        print(f"Received chunk {chunk_id+1}/{total_chunks} of request {request_id}")
        
        # Check if we have received all chunks
        if len(chunk_buffer[request_id]) == total_chunks:
            print(f"Received all chunks for request {request_id}")
            # Clear buffer for this request
            del chunk_buffer[request_id]
            return True, request_id
            
        return False, request_id
        
    except (struct.error, IndexError) as e:
        print(f"Error processing chunk: {e}")
        return False, None

def start_udp_server(port=UDP_PORT, max_packet_size=MAX_UDP_PACKET):
    """
    Start a UDP server that listens for incoming data
    
    Args:
        port (int): Port number to listen on
        max_packet_size (int): Maximum size of UDP packet to receive
    
    Returns:
        None
    """
    # Create UDP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Bind the socket to the port
    server_address = ('', port)
    server_socket.bind(server_address)
    
    print(f"UDP Server listening on port {port}")
    
    # Dictionary to store client configurations
    client_configs = {}
    
    try:
        while True:
            # Wait for incoming data
            data, client_address = server_socket.recvfrom(max_packet_size)
            
            try:
                # Get message type from first byte
                msg_type = data[0]
                
                if msg_type == MSG_TYPE_CONTROL:
                    # Unpack control message: type(1) + request_size(4) + response_size(4)
                    _, request_size, response_size = struct.unpack('!BII', data)
                    print(f"Received control message - Request size: {request_size}, Response size: {response_size}")
                    
                    # Store client configuration
                    client_configs[client_address] = {
                        'request_size': request_size,
                        'response_size': response_size
                    }
                    
                    # Send control ACK (just the message type)
                    ack_message = struct.pack('!B', MSG_TYPE_CONTROL)
                    server_socket.sendto(ack_message, client_address)
                    print("Sent control ACK")
                    
                elif msg_type == MSG_TYPE_REQUEST:
                    # Process the chunk
                    is_complete, request_id = process_chunk(data, client_address)
                
            except (struct.error, IndexError) as e:
                print(f"Error processing message: {e}")
            
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    finally:
        server_socket.close()

def main():
    """
    Main function to start the server
    """
    start_udp_server()

if __name__ == "__main__":
    main()
