import os
import subprocess
import time
import signal
import sys
import argparse
import threading
import re

# Global variables
cpp_process = None
stressor_process = None

# Function to handle Ctrl+C gracefully
def signal_handler(sig, frame):
    print("\nCtrl+C detected. Terminating all processes...")
    if cpp_process:
        cpp_process.terminate()
    if stressor_process:
        stressor_process.terminate()
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

def run_command(command, shell=False):
    """Run a shell command and return its process"""
    if shell:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, 
                                 stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
    else:
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, 
                                 stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
    return process

def compile_project(directory, project_name):
    """Compile a project in the specified directory"""
    original_dir = os.getcwd()
    try:
        print(f"Compiling {project_name}...")
        print(f"Changing to directory: {directory}")
        os.chdir(directory)
        
        # Clean and compile
        subprocess.run("make clean", shell=True, check=False)  # Don't fail if clean fails
        subprocess.run("make", shell=True, check=True)
        print(f"{project_name} compilation successful")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error during {project_name} compilation: {e}")
        return False
    finally:
        os.chdir(original_dir)

def start_stressor(stressor_args, working_dir):
    """Start the GPU stressor with given arguments"""
    global stressor_process
    
    stressor_dir = os.path.join(working_dir, "gpu-sm-dynamic-stressor")
    stressor_path = os.path.join(stressor_dir, "gpu_sm_stressor")
    
    if not os.path.exists(stressor_path):
        print(f"Warning: GPU stressor not found at {stressor_path}")
        return None
    
    # Build stressor command
    cmd = [stressor_path] + stressor_args
    print(f"Starting GPU stressor: {' '.join(cmd)}")
    
    try:
        stressor_process = subprocess.Popen(cmd, cwd=stressor_dir)
        print(f"GPU stressor started with PID: {stressor_process.pid}")
        return stressor_process
    except Exception as e:
        print(f"Error starting GPU stressor: {e}")
        return None

def monitor_output(process, stressor_args, working_dir):
    """Monitor process output and start stressor when frame 101 is detected"""
    frame_101_started = False
    
    try:
        for line in iter(process.stdout.readline, ''):
            # Print the line immediately
            print(line.rstrip())
            
            # Check for "Sent frame 101" pattern
            if not frame_101_started and re.search(r'Sent frame 101\b', line):
                print("\n=== DETECTED FRAME 101 - Starting GPU Stressor ===")
                start_stressor(stressor_args, working_dir)
                frame_101_started = True
    except Exception as e:
        print(f"Error monitoring output: {e}")

def main():
    global cpp_process
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run server_analytics with YOLO and optional GPU stressor')
    parser.add_argument('input_url', type=str, help='Input URL for server_analytics (e.g. rtp://192.168.2.3:9000)')
    parser.add_argument('--port', type=int, default=9876, help='TCP result port (optional)')
    
    # GPU Stressor arguments
    stressor_group = parser.add_argument_group('GPU Stressor Options')
    stressor_group.add_argument('--stressor-mean', type=float, metavar='FLOAT',
                               help='Mean GPU load percentage (0-100, enables stressor)')
    stressor_group.add_argument('--stressor-std', type=float, default=15, metavar='FLOAT',
                               help='Standard deviation of GPU load percentage (default: 15)')
    stressor_group.add_argument('--stressor-interval', type=float, default=1.0, metavar='FLOAT',
                               help='Load adjustment interval in seconds (default: 1.0)')
    stressor_group.add_argument('--stressor-time', type=int, default=0, metavar='INT',
                               help='Stressor duration in seconds (0=unlimited, default: 0)')
    stressor_group.add_argument('--stressor-quiet', action='store_true',
                               help='Run stressor in quiet mode')
    stressor_group.add_argument('--stressor-seed', type=int, metavar='INT',
                               help='Random seed for stressor')

    args = parser.parse_args()

    # Working directory - where the cpp file is located
    working_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(working_dir)
    
    print("Working directory:", working_dir)
    
    # Compile server_analytics (main C++ code)
    if not compile_project(working_dir, "server_analytics"):
        print("Failed to compile server_analytics. Exiting...")
        return 1

    # Compile GPU SM dynamic stressor if stressor is enabled
    stressor_enabled = args.stressor_mean is not None
    stressor_args = []
    
    if stressor_enabled:
        stressor_dir = os.path.join(working_dir, "gpu-sm-dynamic-stressor")
        if os.path.exists(stressor_dir):
            if not compile_project(stressor_dir, "GPU SM dynamic stressor"):
                print("Warning: Failed to compile GPU SM dynamic stressor, disabling stressor...")
                stressor_enabled = False
            else:
                # Build stressor arguments
                stressor_args = ['-m', str(args.stressor_mean)]
                stressor_args.extend(['-s', str(args.stressor_std)])
                stressor_args.extend(['-i', str(args.stressor_interval)])
                stressor_args.extend(['-t', str(args.stressor_time)])
                
                if args.stressor_quiet:
                    stressor_args.append('-q')
                    
                if args.stressor_seed is not None:
                    stressor_args.extend(['--seed', str(args.stressor_seed)])
                
                print(f"GPU stressor will be started with: {' '.join(stressor_args)}")
        else:
            print(f"Warning: GPU SM dynamic stressor directory not found at {stressor_dir}")
            stressor_enabled = False
    else:
        print("GPU stressor disabled (no --stressor-mean specified)")

    time.sleep(3)
    
    # Run C++ program with command line arguments
    cpp_cmd = f"./server_analytics {args.input_url}"
    if args.port != 9876:  # Only add port if it's different from default
        cpp_cmd += f" {args.port}"
    
    print(f"Starting C++ program: {cpp_cmd}")
    cpp_process = run_command(cpp_cmd, shell=True)
    
    # Start output monitoring thread if stressor is enabled
    if stressor_enabled:
        monitor_thread = threading.Thread(target=monitor_output, 
                                         args=(cpp_process, stressor_args, working_dir), 
                                         daemon=True)
        monitor_thread.start()
        print("Output monitoring thread started, waiting for frame 101...")
    else:
        # If no stressor, just print output normally
        def print_output():
            try:
                for line in iter(cpp_process.stdout.readline, ''):
                    print(line.rstrip())
            except:
                pass
        
        output_thread = threading.Thread(target=print_output, daemon=True)
        output_thread.start()
    
    # Wait for 3 seconds
    print("Waiting for 3 seconds...")
    time.sleep(3)
    
    # Run Python script in conda environment
    print("Starting Python script in Conda environment...")
    conda_cmd = "python3 yolo_detection_shm.py"
    py_process = run_command(conda_cmd, shell=True)
    
    # Wait for both processes to complete
    py_process.wait()
    cpp_process.wait()
    
    # Clean up stressor if it's running
    if stressor_process and stressor_process.poll() is None:
        print("Terminating GPU stressor...")
        stressor_process.terminate()
        stressor_process.wait()
    
    print("All processes completed")
    return 0

if __name__ == "__main__":
    sys.exit(main())