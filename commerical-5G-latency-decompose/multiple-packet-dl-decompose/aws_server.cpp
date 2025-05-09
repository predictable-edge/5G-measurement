#include <iostream>
#include <cstring>
#include <ctime>
#include <thread>
#include <vector>
#include <cstdlib>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <atomic>
#include <chrono>
#include <mutex>
#include <csignal>
#include <endian.h>

// Configuration
const char* SERVER_IP = "0.0.0.0";  // Listen on all interfaces
const int SERVER_SYNC_PORT = 5000;  // Port for timestamp service
const int PHONE_SERVER_PORT = 5002; // Port for phone client connections

// Global variables
std::atomic<bool> running{true};
std::mutex console_mutex;

// Function declarations
void handle_pc_client(int client_socket, struct sockaddr_in client_addr);
void handle_phone_client(int client_socket, struct sockaddr_in client_addr);
void listen_for_pc_clients();
void listen_for_phone_clients();
void send_data_to_phone(int client_socket, struct sockaddr_in client_addr, int num_requests, int bytes_per_request);

// Safe console output to avoid interleaving between threads
template<typename... Args>
void safe_print(Args... args) {
    std::lock_guard<std::mutex> lock(console_mutex);
    (std::cout << ... << args) << std::endl;
}

// Get current time in seconds (similar to Python's time.time())
double get_current_time() {
    auto now = std::chrono::system_clock::now();
    auto duration = now.time_since_epoch();
    return std::chrono::duration_cast<std::chrono::microseconds>(duration).count() / 1000000.0;
}

// Function to handle PC client connections
void handle_pc_client(int client_socket, struct sockaddr_in client_addr) {
    char client_ip[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, INET_ADDRSTRLEN);
    int client_port = ntohs(client_addr.sin_port);
    
    safe_print("New PC connection from ", client_ip, ":", client_port);
    
    try {
        char buffer[2048];
        
        while (running) {
            // Receive request
            int bytes_received = recv(client_socket, buffer, sizeof(buffer), 0);
            if (bytes_received <= 0) {
                // Connection closed by client or error
                break;
            }
            
            // Get current timestamp
            double current_time = get_current_time();
            
            // Get size of received data
            int data_size = bytes_received;
            
            // Create response of the same size
            // First 8 bytes contain the timestamp
            char response[2048];
            memcpy(response, &current_time, sizeof(double));
            
            // Fill the rest with padding to match the original data size
            if (data_size <= 8) {
                // If received data is smaller than 8 bytes, still send full timestamp
                send(client_socket, response, sizeof(double), 0);
            } else {
                // If larger, send timestamp + padding
                int padding_size = data_size - 8;
                if (bytes_received > 8) {
                    memcpy(response + 8, buffer + 8, padding_size);
                } else {
                    memset(response + 8, 0, padding_size);
                }
                send(client_socket, response, data_size, 0);
            }
            
            safe_print("Timestamp sent to ", client_ip, ":", client_port, 
                       ", response size: ", data_size, " bytes");
        }
    } catch (const std::exception& e) {
        safe_print("Error handling PC client ", client_ip, ":", client_port, ": ", e.what());
    }
    
    // Close the connection
    close(client_socket);
    safe_print("Connection closed with PC client ", client_ip, ":", client_port);
}

// Function to send data to phone client
void send_data_to_phone(int client_socket, struct sockaddr_in client_addr, int num_requests, int bytes_per_request) {
    char client_ip[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, INET_ADDRSTRLEN);
    int client_port = ntohs(client_addr.sin_port);
    
    safe_print("Ready to send ", num_requests, " requests to ", client_ip, ":", client_port, " when triggered");
    
    try {
        int requests_sent = 0;
        char trigger_buffer[4];
        
        while (requests_sent < num_requests && running) {
            // Wait for trigger packet from client
            int bytes_received = recv(client_socket, trigger_buffer, 4, 0);
            if (bytes_received <= 0) {
                safe_print("Connection closed by client during trigger wait");
                break;
            }
            
            // Check if it's a valid trigger packet
            if (bytes_received != 4 || strncmp(trigger_buffer, "TRIG", 4) != 0) {
                safe_print("Received invalid trigger packet");
                continue;
            }
            
            // Get current timestamp
            double current_time = get_current_time();
            
            // Create payload of specified size with random bytes
            std::vector<char> payload;
            if (bytes_per_request > 0) {
                payload.resize(bytes_per_request, 0);
            }
            
            // Create header with timestamp and packet size
            char header[12]; // 8 bytes for timestamp, 4 bytes for size
            uint64_t bits;
            memcpy(&bits, &current_time, sizeof(double));
            bits = htobe64(bits); 
            uint32_t net_size = htonl(bytes_per_request);
            memcpy(header, &bits, sizeof(uint64_t));
            memcpy(header + 8, &net_size, sizeof(uint32_t));
            
            // Send header and payload separately
            send(client_socket, header, sizeof(header), 0);
            if (bytes_per_request > 0) {
                send(client_socket, payload.data(), bytes_per_request, 0);
            }
            
            requests_sent++;
            safe_print("Sent request ", requests_sent, "/", num_requests, " to ", 
                      client_ip, ":", client_port, ": ", bytes_per_request, " bytes of payload");
        }
        
        safe_print("Completed sending all ", requests_sent, "/", num_requests, 
                  " requests to ", client_ip, ":", client_port);
        
    } catch (const std::exception& e) {
        safe_print("Error sending data to phone client ", client_ip, ":", client_port, ": ", e.what());
    }
}

// Function to handle phone client connections
void handle_phone_client(int client_socket, struct sockaddr_in client_addr) {
    char client_ip[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, INET_ADDRSTRLEN);
    int client_port = ntohs(client_addr.sin_port);
    
    safe_print("New phone connection from ", client_ip, ":", client_port);
    
    try {
        // Disable Nagle algorithm for the client socket
        int flag = 1;
        setsockopt(client_socket, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(int));
        
        // Receive parameters from phone client
        // Parameters are packed as (num_requests, interval, bytes_per_request)
        // Format: iii = 4-byte int + 4-byte int + 4-byte int = 12 bytes total
        char param_bytes[12];
        int bytes_received = recv(client_socket, param_bytes, sizeof(param_bytes), 0);
        
        if (bytes_received != 12) {
            safe_print("Failed to receive parameters from ", client_ip, ":", client_port);
            close(client_socket);
            return;
        }
        
        // Parse parameters (network byte order)
        int num_requests, interval_ms, bytes_per_request;
        memcpy(&num_requests, param_bytes, sizeof(int));
        memcpy(&interval_ms, param_bytes + 4, sizeof(int));
        memcpy(&bytes_per_request, param_bytes + 8, sizeof(int));
        
        // Convert from network byte order
        num_requests = ntohl(num_requests);
        interval_ms = ntohl(interval_ms);
        bytes_per_request = ntohl(bytes_per_request);
        
        safe_print("Received parameters from ", client_ip, ":", client_port, ":");
        safe_print("  - Number of requests: ", num_requests);
        safe_print("  - Interval: ", interval_ms, "ms (not used in trigger mode)");
        safe_print("  - Bytes per request: ", bytes_per_request);
        
        // Send acknowledgment
        const char* ack = "ACK";
        send(client_socket, ack, 3, 0);
        
        // Wait for trigger packets and send data
        send_data_to_phone(client_socket, client_addr, num_requests, bytes_per_request);
        
    } catch (const std::exception& e) {
        safe_print("Error handling phone client ", client_ip, ":", client_port, ": ", e.what());
    }
    
    // Close the connection
    close(client_socket);
    safe_print("Connection closed with phone client ", client_ip, ":", client_port);
}

// Function to listen for PC client connections
void listen_for_pc_clients() {
    // Create TCP socket for PC clients
    int pc_server_socket = socket(AF_INET, SOCK_STREAM, 0);
    if (pc_server_socket < 0) {
        std::cerr << "Failed to create PC server socket" << std::endl;
        return;
    }
    
    // Set socket options
    int opt = 1;
    setsockopt(pc_server_socket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    
    // Disable Nagle algorithm
    setsockopt(pc_server_socket, IPPROTO_TCP, TCP_NODELAY, &opt, sizeof(opt));
    
    // Bind socket to address and port
    struct sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(SERVER_SYNC_PORT);
    
    if (bind(pc_server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "Failed to bind PC server socket" << std::endl;
        close(pc_server_socket);
        return;
    }
    
    // Listen for connections
    if (listen(pc_server_socket, 5) < 0) {  // Allow up to 5 queued connections
        std::cerr << "Failed to listen on PC server socket" << std::endl;
        close(pc_server_socket);
        return;
    }
    
    safe_print("AWS Server listening for PC clients on ", SERVER_IP, ":", SERVER_SYNC_PORT);
    
    try {
        while (running) {
            // Accept new connection
            struct sockaddr_in client_addr;
            socklen_t client_addr_len = sizeof(client_addr);
            int client_socket = accept(pc_server_socket, (struct sockaddr*)&client_addr, &client_addr_len);
            
            if (client_socket < 0) {
                if (running) {
                    safe_print("Failed to accept PC client connection");
                }
                continue;
            }
            
            // Start a new thread to handle this client using a lambda
            std::thread client_handler([=]() {
                struct sockaddr_in addr_copy = client_addr;
                handle_pc_client(client_socket, addr_copy);
            });
            client_handler.detach();  // Don't wait for thread to finish
        }
    } catch (const std::exception& e) {
        safe_print("Error in PC server: ", e.what());
    }
    
    // Close the server socket
    close(pc_server_socket);
    safe_print("PC server shutting down...");
}

// Function to listen for phone client connections
void listen_for_phone_clients() {
    // Create TCP socket for phone clients
    int phone_server_socket = socket(AF_INET, SOCK_STREAM, 0);
    if (phone_server_socket < 0) {
        std::cerr << "Failed to create phone server socket" << std::endl;
        return;
    }
    
    // Set socket options
    int opt = 1;
    setsockopt(phone_server_socket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    
    // Disable Nagle algorithm
    setsockopt(phone_server_socket, IPPROTO_TCP, TCP_NODELAY, &opt, sizeof(opt));
    
    // Bind socket to address and port
    struct sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PHONE_SERVER_PORT);
    
    if (bind(phone_server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "Failed to bind phone server socket" << std::endl;
        close(phone_server_socket);
        return;
    }
    
    // Listen for connections
    if (listen(phone_server_socket, 5) < 0) {  // Allow up to 5 queued connections
        std::cerr << "Failed to listen on phone server socket" << std::endl;
        close(phone_server_socket);
        return;
    }
    
    safe_print("AWS Server listening for phone clients on ", SERVER_IP, ":", PHONE_SERVER_PORT);
    
    try {
        while (running) {
            // Accept new connection
            struct sockaddr_in client_addr;
            socklen_t client_addr_len = sizeof(client_addr);
            int client_socket = accept(phone_server_socket, (struct sockaddr*)&client_addr, &client_addr_len);
            
            if (client_socket < 0) {
                if (running) {
                    safe_print("Failed to accept phone client connection");
                }
                continue;
            }
            
            // Start a new thread to handle this client using a lambda
            std::thread client_handler([=]() {
                struct sockaddr_in addr_copy = client_addr;
                handle_phone_client(client_socket, addr_copy);
            });
            client_handler.detach();  // Don't wait for thread to finish
        }
    } catch (const std::exception& e) {
        safe_print("Error in phone server: ", e.what());
    }
    
    // Close the server socket
    close(phone_server_socket);
    safe_print("Phone server shutting down...");
}

// Signal handler function
void signal_handler(int signal) {
    running = false;
    std::cerr << "Received signal " << signal << ", shutting down..." << std::endl;
}

int main() {
    // Set up signal handling
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    safe_print("AWS Server starting up...");
    
    // Start PC client listener thread
    std::thread pc_thread(listen_for_pc_clients);
    
    // Start phone client listener thread
    std::thread phone_thread(listen_for_phone_clients);
    
    safe_print("AWS Server running with both PC and phone listeners");
    
    // Wait for threads to finish (which they won't unless running becomes false)
    pc_thread.join();
    phone_thread.join();
    
    safe_print("Server shutting down...");
    
    return 0;
}
