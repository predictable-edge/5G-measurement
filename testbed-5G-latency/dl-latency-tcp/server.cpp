#include <iostream>
#include <string>
#include <cstring>
#include <chrono>
#include <thread>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <memory>



// Header structure - sent first to indicate request metadata
struct RequestHeader {
    uint64_t timestamp;     // Timestamp when request is sent
    uint32_t request_id;    // Request ID
    uint32_t total_requests; // Total number of requests to be sent
    uint32_t data_size;     // Size of actual data in this request
};

// Function to send a single request
void send_request(int client_sockfd, int bytes_to_send, int request_id, int total_requests) {
    // Create header
    RequestHeader header;
    header.request_id = request_id;
    header.total_requests = total_requests;
    header.data_size = bytes_to_send;
    
    // Allocate memory for data
    std::unique_ptr<char[]> data(new char[bytes_to_send]);
    
    // Fill data with pattern for testing
    for (int j = 0; j < bytes_to_send; j++) {
        data[j] = 'A' + (j % 26);
    }
    
    // Get current timestamp right before sending
    header.timestamp = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
    
    // Send header first
    send(client_sockfd, &header, sizeof(RequestHeader), 0);
    
    // Then send data
    send(client_sockfd, data.get(), bytes_to_send, 0);
    
    std::cout << "Sent request " << request_id + 1 << "/" << total_requests 
              << " with timestamp " << header.timestamp 
              << " and size " << bytes_to_send << " bytes" << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc < 5) {
        std::cerr << "Usage: " << argv[0] << " <target_ip> <target_port> <bytes_to_send> <num_requests> [send_interval_ms]" << std::endl;
        return 1;
    }
    
    // Parse command line arguments
    std::string target_ip = argv[1];
    int target_port = std::stoi(argv[2]);
    int bytes_to_send = std::stoi(argv[3]);
    int num_requests = std::stoi(argv[4]);
    int send_interval_ms = (argc > 5) ? std::stoi(argv[5]) : 1000;  // Default 1000ms interval
    
    // Create TCP socket
    int sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) {
        std::cerr << "Error creating socket" << std::endl;
        return 1;
    }
    
    // Disable Nagle algorithm
    int flag = 1;
    if (setsockopt(sockfd, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag)) < 0) {
        std::cerr << "Error disabling Nagle algorithm" << std::endl;
        close(sockfd);
        return 1;
    }
    
    // Set up server address
    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(target_port);
    
    if (inet_pton(AF_INET, target_ip.c_str(), &server_addr.sin_addr) <= 0) {
        std::cerr << "Invalid address/ Address not supported" << std::endl;
        close(sockfd);
        return 1;
    }
    
    // Connect to server
    if (connect(sockfd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "Connection Failed" << std::endl;
        close(sockfd);
        return 1;
    }
    
    std::cout << "Connected to " << target_ip << ":" << target_port << std::endl;
    std::cout << "Server starting to send " << num_requests << " requests of " 
              << bytes_to_send << " bytes each with interval " << send_interval_ms << "ms" << std::endl;
    
    // Send requests
    for (int i = 0; i < num_requests; i++) {
        std::cout << "Sending request " << i+1 << "/" << num_requests << std::endl;
        send_request(sockfd, bytes_to_send, i, num_requests);
        
        // Wait for the interval before sending next request
        if (i < num_requests - 1) {
            std::this_thread::sleep_for(std::chrono::milliseconds(send_interval_ms));
        }
    }
    
    std::cout << "All requests sent successfully" << std::endl;
    close(sockfd);
    return 0;
}
