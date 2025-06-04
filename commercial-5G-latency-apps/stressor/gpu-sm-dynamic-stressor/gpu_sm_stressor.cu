#include <cuda_runtime.h>
#include <cuda.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <sys/time.h>
#include <chrono>
#include <thread>
#include <math.h>
#include <random>
#include <string.h>

static volatile int keep_running = 1;

// Configuration structure for GPU stress test
struct StressConfig {
    float mean_load;        // Mean GPU load percentage (0-100)
    float std_load;         // Standard deviation of GPU load percentage
    float interval;         // Load adjustment interval in seconds
    int duration;          // Test duration in seconds (0 = unlimited)
    bool verbose;          // Enable verbose output
    bool validate_dist;    // Validate distribution before starting
    unsigned int seed;     // Random seed for reproducible results
};

void signal_handler(int sig) {
    keep_running = 0;
    printf("\nStopping GPU stress test...\n");
}

// Print usage information
void print_usage(const char* program_name) {
    printf("Usage: %s [OPTIONS]\n", program_name);
    printf("Normal Distribution GPU SM Load Stressor\n\n");
    printf("Options:\n");
    printf("  -m, --mean FLOAT     Mean GPU load percentage (0-100, default: 50)\n");
    printf("  -s, --std FLOAT      Standard deviation of GPU load percentage (default: 15)\n");
    printf("  -i, --interval FLOAT Load adjustment interval in seconds (default: 1.0)\n");
    printf("  -t, --time INT       Test duration in seconds (0=unlimited, default: 0)\n");
    printf("  -q, --quiet          Quiet mode - reduce output\n");
    printf("  --validate           Validate normal distribution before starting test\n");
    printf("  --seed INT           Random seed for reproducible results\n");
    printf("  -h, --help           Show this help message\n\n");
    printf("Examples:\n");
    printf("  %s                                    # Use default parameters\n", program_name);
    printf("  %s -m 80 -s 10 -i 1.0               # 80%% mean, 10%% std, 1s interval\n", program_name);
    printf("  %s -m 60 -s 20 -t 300               # Run for 5 minutes\n", program_name);
    printf("  %s --mean 70 --std 15 --quiet       # Quiet mode\n", program_name);
    printf("  %s --validate -m 20 -s 15           # Validate distribution with mean=20, std=15\n", program_name);
    printf("  %s --seed 12345                     # Use specific random seed\n\n", program_name);
    printf("Note:\n");
    printf("  - Load changes follow normal distribution every interval\n");
    printf("  - Values are clamped to [0, 100] range\n");
    printf("  - Use --validate to check distribution statistics\n");
    printf("  - Uses time-slicing method for precise GPU usage control\n");
    printf("  - Press Ctrl+C to stop the test\n");
}

// Parse command line arguments
bool parse_arguments(int argc, char* argv[], StressConfig& config) {
    // Set default values
    config.mean_load = 50.0f;
    config.std_load = 15.0f;
    config.interval = 1.0f;
    config.duration = 0;
    config.verbose = true;
    config.validate_dist = false;
    config.seed = (unsigned int)time(NULL);
    
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-m") == 0 || strcmp(argv[i], "--mean") == 0) {
            if (i + 1 >= argc) {
                printf("Error: Missing value for %s\n", argv[i]);
                return false;
            }
            config.mean_load = atof(argv[++i]);
            if (config.mean_load < 0 || config.mean_load > 100) {
                printf("Error: Mean load must be between 0 and 100\n");
                return false;
            }
        }
        else if (strcmp(argv[i], "-s") == 0 || strcmp(argv[i], "--std") == 0) {
            if (i + 1 >= argc) {
                printf("Error: Missing value for %s\n", argv[i]);
                return false;
            }
            config.std_load = atof(argv[++i]);
            if (config.std_load < 0) {
                printf("Error: Standard deviation must be >= 0\n");
                return false;
            }
        }
        else if (strcmp(argv[i], "-i") == 0 || strcmp(argv[i], "--interval") == 0) {
            if (i + 1 >= argc) {
                printf("Error: Missing value for %s\n", argv[i]);
                return false;
            }
            config.interval = atof(argv[++i]);
            if (config.interval <= 0) {
                printf("Error: Interval must be > 0\n");
                return false;
            }
        }
        else if (strcmp(argv[i], "-t") == 0 || strcmp(argv[i], "--time") == 0) {
            if (i + 1 >= argc) {
                printf("Error: Missing value for %s\n", argv[i]);
                return false;
            }
            config.duration = atoi(argv[++i]);
            if (config.duration < 0) {
                printf("Error: Test duration must be >= 0\n");
                return false;
            }
        }
        else if (strcmp(argv[i], "-q") == 0 || strcmp(argv[i], "--quiet") == 0) {
            config.verbose = false;
        }
        else if (strcmp(argv[i], "--validate") == 0) {
            config.validate_dist = true;
        }
        else if (strcmp(argv[i], "--seed") == 0) {
            if (i + 1 >= argc) {
                printf("Error: Missing value for %s\n", argv[i]);
                return false;
            }
            config.seed = (unsigned int)atoi(argv[++i]);
        }
        else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            print_usage(argv[0]);
            exit(0);
        }
        else {
            printf("Error: Unknown option %s\n", argv[i]);
            print_usage(argv[0]);
            return false;
        }
    }
    
    return true;
}

// Generate normally distributed load value using Box-Muller transform
float generate_normal_load(float mean, float std_dev, std::mt19937& rng) {
    // Use C++ standard library for more reliable normal distribution
    static std::normal_distribution<float> normal_dist(0.0f, 1.0f);
    
    // Generate standard normal value (mean=0, std=1)
    float z = normal_dist(rng);
    
    // Transform to desired mean and std_dev
    float load = mean + std_dev * z;
    
    // Clamp to valid range [0, 100]
    if (load < 0.0f) load = 0.0f;
    if (load > 100.0f) load = 100.0f;
    
    return load;
}

// Statistical validation function - for debugging
void print_distribution_stats(float mean, float std_dev, int samples = 1000) {
    std::mt19937 rng(12345); // Fixed seed for reproducible stats
    float sum = 0.0f;
    float sum_sq = 0.0f;
    float min_val = 1000.0f;
    float max_val = -1000.0f;
    int clamped_low = 0;
    int clamped_high = 0;
    
    for (int i = 0; i < samples; i++) {
        float val = generate_normal_load(mean, std_dev, rng);
        sum += val;
        sum_sq += val * val;
        
        if (val < min_val) min_val = val;
        if (val > max_val) max_val = val;
        if (val <= 0.0f) clamped_low++;
        if (val >= 100.0f) clamped_high++;
    }
    
    float actual_mean = sum / samples;
    float actual_std = sqrtf((sum_sq / samples) - (actual_mean * actual_mean));
    
    printf("Distribution validation (%d samples):\n", samples);
    printf("  Target: Mean=%.1f%%, StdDev=%.1f%%\n", mean, std_dev);
    printf("  Actual: Mean=%.1f%%, StdDev=%.1f%%\n", actual_mean, actual_std);
    printf("  Range: [%.1f%%, %.1f%%]\n", min_val, max_val);
    printf("  Clamped: %d low (%.1f%%), %d high (%.1f%%)\n", 
           clamped_low, clamped_low*100.0f/samples, 
           clamped_high, clamped_high*100.0f/samples);
    printf("  Theoretical 3-sigma range: [%.1f%%, %.1f%%]\n", 
           mean - 3*std_dev, mean + 3*std_dev);
    printf("\n");
}

// GPU workload kernel - enhanced version to fully utilize SMs
__global__ void gpu_stress_kernel(float *data, int size, int iterations) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int stride = blockDim.x * gridDim.x;
    
    // Ensure each thread has sufficient work
    for (int i = idx; i < size; i += stride) {
        float temp = data[i];
        
        // Execute intensive floating-point operations
        for (int iter = 0; iter < iterations; iter++) {
            temp = temp * 1.000001f + 0.000001f;
            temp = sqrtf(temp * temp + 1.0f);
            temp = sinf(temp) * cosf(temp);
            temp = expf(temp * 0.00001f);
            temp = logf(temp + 1.0f);
            temp = powf(temp, 1.001f);
        }
        
        data[i] = temp;
    }
}

// Print GPU device information
void print_gpu_info() {
    int device_count;
    cudaGetDeviceCount(&device_count);
    
    printf("Detected %d GPU device(s)\n", device_count);
    
    for (int i = 0; i < device_count; i++) {
        cudaDeviceProp prop;
        cudaGetDeviceProperties(&prop, i);
        
        printf("\nGPU %d: %s\n", i, prop.name);
        printf("  SM Count: %d\n", prop.multiProcessorCount);
        printf("  Max Threads/SM: %d\n", prop.maxThreadsPerMultiProcessor);
        printf("  Max Threads/Block: %d\n", prop.maxThreadsPerBlock);
        printf("  Max Blocks/SM: %d\n", prop.maxBlocksPerMultiProcessor);
        printf("  Global Memory: %.1f GB\n", prop.totalGlobalMem / (1024.0*1024.0*1024.0));
        printf("  Compute Capability: %d.%d\n", prop.major, prop.minor);
    }
}

// Get timestamp in milliseconds
long long get_timestamp_ms() {
    auto now = std::chrono::high_resolution_clock::now();
    auto duration = now.time_since_epoch();
    return std::chrono::duration_cast<std::chrono::milliseconds>(duration).count();
}

// Precise sleep function (milliseconds)
void precise_sleep_ms(int ms) {
    if (ms <= 0) return;
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

// Format timestamp for display
std::string format_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    
    char buffer[32];
    struct tm* tm_info = localtime(&time_t);
    strftime(buffer, sizeof(buffer), "%H:%M:%S", tm_info);
    
    char result[64];
    snprintf(result, sizeof(result), "%s.%03d", buffer, (int)ms.count());
    return std::string(result);
}

int main(int argc, char *argv[]) {
    StressConfig config;
    
    // Parse command line arguments
    if (!parse_arguments(argc, argv, config)) {
        return 1;
    }
    
    // Register signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // Initialize CUDA
    cudaSetDevice(0);
    
    if (config.verbose) {
        print_gpu_info();
    }
    
    // Get GPU properties
    cudaDeviceProp prop;
    cudaGetDeviceProperties(&prop, 0);
    
    int sm_count = prop.multiProcessorCount;
    
    if (config.verbose) {
        printf("\n");
        printf("======================================================================\n");
        printf("Normal Distribution GPU SM Load Stressor\n");
        printf("======================================================================\n");
        printf("Target load distribution: Mean=%.1f%%, StdDev=%.1f%%\n", 
               config.mean_load, config.std_load);
        printf("Load adjustment interval: %.1fs\n", config.interval);
        printf("Random seed: %u\n", config.seed);
        if (config.duration > 0) {
            printf("Test duration: %d seconds\n", config.duration);
        } else {
            printf("Test duration: Unlimited\n");
        }
        printf("Using time-slicing method for precise GPU usage control\n");
        printf("Press Ctrl+C to stop the test\n");
        printf("======================================================================\n");
        printf("\n\n");
    }
    
    // Initialize random number generator
    std::mt19937 rng(config.seed);
    
    // Validate distribution if requested
    if (config.validate_dist) {
        if (config.verbose) {
            printf("Validating normal distribution...\n");
        }
        print_distribution_stats(config.mean_load, config.std_load, 10000);
        if (!config.verbose) {
            // If we're just validating, exit after showing stats
            return 0;
        }
    }
    
    // Time-slicing parameters
    int base_cycle_time_ms = 100;  // 100ms per cycle
    
    // Configure kernel parameters - fully utilize GPU
    int threads_per_block = 512;
    int blocks_per_sm = 2;  // 2 blocks per SM
    int total_blocks = sm_count * blocks_per_sm;
    int total_threads = total_blocks * threads_per_block;
    
    if (config.verbose) {
        printf("Kernel configuration:\n");
        printf("  Block count: %d\n", total_blocks);
        printf("  Threads per block: %d\n", threads_per_block);
        printf("  Total threads: %d\n", total_threads);
        printf("  Data size: %d MB\n\n", (int)(total_threads * sizeof(float) / (1024*1024)));
    }
    
    // Allocate GPU memory
    float *d_data;
    size_t data_size = total_threads * sizeof(float);
    cudaMalloc(&d_data, data_size);
    
    // Initialize data
    float *h_data = (float*)malloc(data_size);
    for (int i = 0; i < total_threads; i++) {
        h_data[i] = (float)(i % 1000) / 1000.0f;
    }
    cudaMemcpy(d_data, h_data, data_size, cudaMemcpyHostToDevice);
    
    // Calculate kernel iterations to ensure full GPU load during work time
    int kernel_iterations = 5000;
    
    // Statistics
    long long start_time = get_timestamp_ms();
    int iteration_count = 0;
    float current_load = 0.0f;
    float min_load = 1000.0f;
    float max_load = -1000.0f;
    float sum_load = 0.0f;
    
    if (config.verbose) {
        printf("Starting dynamic load test...\n");
        printf("Expected 3-sigma range: [%.1f%%, %.1f%%] (99.7%% of values)\n", 
               fmaxf(0.0f, config.mean_load - 3*config.std_load), 
               fminf(100.0f, config.mean_load + 3*config.std_load));
        printf("Time        | Iter | Target Load | Work/Idle | Running Stats\n");
        printf("------------|------|-------------|-----------|---------------\n");
    }
    
    while (keep_running) {
        long long iteration_start = get_timestamp_ms();
        
        // Generate new load value
        current_load = generate_normal_load(config.mean_load, config.std_load, rng);
        iteration_count++;
        
        // Update statistics
        if (current_load < min_load) min_load = current_load;
        if (current_load > max_load) max_load = current_load;
        sum_load += current_load;
        float avg_load = sum_load / iteration_count;
        
        // Calculate time-slicing parameters for this iteration
        int work_time_ms = (int)(base_cycle_time_ms * current_load / 100.0f);
        int idle_time_ms = base_cycle_time_ms - work_time_ms;
        
        if (config.verbose) {
            printf("%s | %4d | %7.1f%%   | %3dms/%2dms | avg:%.1f%% [%.1f-%.1f%%]\n", 
                   format_timestamp().c_str(), iteration_count, current_load, 
                   work_time_ms, idle_time_ms, avg_load, min_load, max_load);
        }
        
        // Run for the specified interval
        long long interval_end = iteration_start + (long long)(config.interval * 1000);
        
        while (keep_running && get_timestamp_ms() < interval_end) {
            long long cycle_start = get_timestamp_ms();
            
            // Work phase - launch GPU kernel
            if (work_time_ms > 0) {
                long long work_start = get_timestamp_ms();
                
                // Continuously launch kernels until work time is reached
                while (keep_running && (get_timestamp_ms() - work_start) < work_time_ms) {
                    gpu_stress_kernel<<<total_blocks, threads_per_block>>>(
                        d_data, total_threads, kernel_iterations);
                    cudaDeviceSynchronize();
                }
            }
            
            // Idle phase - CPU sleep
            if (idle_time_ms > 0 && keep_running) {
                precise_sleep_ms(idle_time_ms);
            }
            
            // Check if we should exit the interval loop
            if (get_timestamp_ms() >= interval_end) {
                break;
            }
        }
        
        // Check duration limit
        if (config.duration > 0) {
            long long elapsed_seconds = (get_timestamp_ms() - start_time) / 1000;
            if (elapsed_seconds >= config.duration) {
                if (config.verbose) {
                    printf("\nTest duration completed (%d seconds)\n", config.duration);
                }
                break;
            }
        }
    }
    
    // Final statistics
    long long total_elapsed = get_timestamp_ms() - start_time;
    
    if (config.verbose) {
        printf("\n");
        printf("========================================\n");
        printf("=== Test Complete ===\n");
        printf("========================================\n");
        printf("Total runtime: %.1f seconds\n", total_elapsed / 1000.0f);
        printf("Total iterations: %d\n", iteration_count);
        printf("Average iterations per second: %.1f\n", 
               iteration_count * 1000.0f / total_elapsed);
        printf("\nLoad Distribution:\n");
        printf("  Target: Mean=%.1f%%, StdDev=%.1f%%\n", 
               config.mean_load, config.std_load);
        printf("  Actual: Mean=%.1f%%, Range=[%.1f%%, %.1f%%]\n", 
               sum_load / iteration_count, min_load, max_load);
        printf("  Expected 3-sigma range: [%.1f%%, %.1f%%]\n", 
               fmaxf(0.0f, config.mean_load - 3*config.std_load), 
               fminf(100.0f, config.mean_load + 3*config.std_load));
        printf("  Final load setting: %.1f%%\n", current_load);
        printf("\nConfiguration:\n");
        printf("  Load adjustment interval: %.1fs\n", config.interval);
        printf("  Random seed: %u\n", config.seed);
    }
    
    // Cleanup resources
    cudaFree(d_data);
    free(h_data);
    
    return 0;
}