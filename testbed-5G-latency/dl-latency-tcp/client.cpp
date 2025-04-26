#include <iostream>
#include <fstream>
#include <string>
#include <cstring>
#include <chrono>
#include <map>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <iomanip>
#include <signal.h>
#include <memory>

// Header structure - must match the server's structure
struct RequestHeader {
    uint64_t timestamp;     // Timestamp when request is sent
    uint32_t request_id;    // Request ID
    uint32_t total_requests; // Total number of requests to be sent
    uint32_t data_size;     // Size of actual data in this request
};

// Structure to track statistics for each request
struct RequestStats {
    uint64_t send_time = 0;         // Timestamp from sender
    uint64_t header_recv_time = 0;  // Time when header was received
    uint64_t data_complete_time = 0; // Time when all data was received
    bool is_complete = false;
};

// Global variables for signal handler
bool running = true;
std::map<int, RequestStats> requests;
std::string output_file;

// Signal handler for graceful shutdown
void signal_handler(int signal) {
    std::cout << "Received signal " << signal << ", shutting down..." << std::endl;
    running = false;
}

// Function to write results to file
void write_results() {
    std::ofstream outfile(output_file);
    if (!outfile.is_open()) {
        std::cerr << "Error opening output file: " << output_file << std::endl;
        return;
    }
    
    // Write header
    outfile << std::left << std::setw(15) << "Request_ID" 
            << std::setw(30) << "Transmission_Delay(us)" 
            << std::setw(30) << "Data_Reception_Duration(us)" 
            << "\n";
    
    // Write data for each request
    for (const auto& pair : requests) {
        uint32_t request_id = pair.first;
        const RequestStats& stats = pair.second;
        
        if (stats.is_complete) {
            uint64_t transmission_delay = stats.header_recv_time - stats.send_time;
            uint64_t data_reception_duration = stats.data_complete_time - stats.header_recv_time;
            
            outfile << std::left << std::setw(15) << request_id
                    << std::setw(30) << transmission_delay
                    << std::setw(30) << data_reception_duration
                    << "\n";
        }
    }
    
    outfile.close();
    std::cout << "Results written to " << output_file << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <listen_port> <output_file>" << std::endl;
        return 1;
    }
    
    // Parse command line arguments
    int listen_port = std::stoi(argv[1]);
    output_file = argv[2];
    
    // Set up signal handler
    signal(SIGINT, signal_handler);
    
    // Create TCP socket
    int server_sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_sockfd < 0) {
        std::cerr << "Error creating socket" << std::endl;
        return 1;
    }
    
    // Set socket options for reuse
    int opt = 1;
    if (setsockopt(server_sockfd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
        std::cerr << "Error setting socket options" << std::endl;
        close(server_sockfd);
        return 1;
    }
    
    // Set up server address
    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(listen_port);
    
    // Bind socket to address
    if (bind(server_sockfd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "Error binding socket to port " << listen_port << std::endl;
        close(server_sockfd);
        return 1;
    }
    
    // Listen for connections
    if (listen(server_sockfd, 10) < 0) {
        std::cerr << "Error listening on socket" << std::endl;
        close(server_sockfd);
        return 1;
    }
    
    std::cout << "Client listening on port " << listen_port << std::endl;
    std::cout << "Press Ctrl+C to stop and write results to file" << std::endl;
    
    uint64_t start_time = 0;
    uint64_t end_time = 0;
    uint32_t total_requests_received = 0;
    uint32_t expected_total_requests = 0;
    
    while (running) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        
        // Accept connection from client
        std::cout << "Waiting for connection..." << std::endl;
        int client_sockfd = accept(server_sockfd, (struct sockaddr*)&client_addr, &client_len);
        if (client_sockfd < 0) {
            std::cerr << "Error accepting connection" << std::endl;
            continue;
        }
        
        char client_ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, INET_ADDRSTRLEN);
        std::cout << "Connection established with " << client_ip << ":" << ntohs(client_addr.sin_port) << std::endl;
        
        // Process requests from this client
        while (running) {
            // First receive the header
            RequestHeader header;
            int header_bytes = recv(client_sockfd, &header, sizeof(RequestHeader), 0);
            
            if (header_bytes <= 0) {
                if (header_bytes == 0) {
                    std::cout << "Client disconnected" << std::endl;
                } else {
                    std::cerr << "Error receiving header: " << strerror(errno) << std::endl;
                }
                break;
            }
            
            // Get current timestamp when header is received
            uint64_t header_recv_time = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::system_clock::now().time_since_epoch()
            ).count();
            
            // Now receive the data portion
            std::unique_ptr<char[]> data(new char[header.data_size]);
            int remaining = header.data_size;
            int total_received = 0;
            
            while (remaining > 0) {
                int bytes_received = recv(client_sockfd, data.get() + total_received, remaining, 0);
                if (bytes_received <= 0) {
                    if (bytes_received == 0) {
                        std::cout << "Client disconnected during data transfer" << std::endl;
                    } else {
                        std::cerr << "Error receiving data: " << strerror(errno) << std::endl;
                    }
                    break;
                }
                
                total_received += bytes_received;
                remaining -= bytes_received;
            }
            
            // Get timestamp when all data is received
            uint64_t data_complete_time = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::system_clock::now().time_since_epoch()
            ).count();
            
            if (remaining > 0) {
                std::cerr << "Incomplete data received, expected " << header.data_size 
                          << " bytes but got " << total_received << " bytes" << std::endl;
                break;
            }
            
            // Initialize total session timing if this is the first request
            if (total_requests_received == 0) {
                start_time = header_recv_time;
                expected_total_requests = header.total_requests;
            }
            
            // Update session end time with each request
            end_time = data_complete_time;
            
            // Process the received request
            uint32_t request_id = header.request_id;
            
            std::cout << "Received request " << request_id + 1 << "/" << header.total_requests 
                      << " with timestamp " << header.timestamp
                      << " and size " << header.data_size << " bytes" << std::endl;
            std::cout << "  - Header transmission delay: " << (header_recv_time - header.timestamp) << " us" << std::endl;
            std::cout << "  - Data reception duration: " << (data_complete_time - header_recv_time) << " us" << std::endl;
            
            // Store request statistics
            requests[request_id].send_time = header.timestamp;
            requests[request_id].header_recv_time = header_recv_time;
            requests[request_id].data_complete_time = data_complete_time;
            requests[request_id].is_complete = true;
            
            total_requests_received++;
            
            // Check if we have received all expected requests
            if (expected_total_requests > 0 && total_requests_received >= expected_total_requests) {
                std::cout << "All " << expected_total_requests << " requests received." << std::endl;
                std::cout << "Total session duration: " << (end_time - start_time) << " microseconds" << std::endl;
                running = false;
                break;
            }
        }
        
        close(client_sockfd);
    }
    
    close(server_sockfd);
    
    // Write final results to file
    write_results();
    
    return 0;
}
