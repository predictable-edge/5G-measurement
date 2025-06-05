#!/usr/bin/env python3
"""
Run script for video transcoding with CPU stress testing
Monitors transcoding output and starts CPU stressor when frame count exceeds threshold
"""

import subprocess
import sys
import argparse
import threading
import time
import signal
import os
import re
from typing import Optional

# Hardcoded path to the transcoding executable
TRANSCODING_EXECUTABLE = "./server_transcoding"

class TranscodingController:
    """Controller for managing transcoding and CPU stress processes"""
    
    def __init__(self, transcoding_args: list, frame_threshold: int, 
                 stressor_args: list, verbose: bool = True, enable_cpu_stressor: bool = True):
        """
        Initialize the transcoding controller
        
        Args:
            transcoding_args: Arguments for transcoding program
            frame_threshold: Frame count threshold to start CPU stressor
            stressor_args: Arguments for CPU stressor
            verbose: Enable verbose output
            enable_cpu_stressor: Enable CPU stressor functionality
        """
        self.transcoding_cmd = [TRANSCODING_EXECUTABLE] + transcoding_args
        self.frame_threshold = frame_threshold
        self.stressor_args = stressor_args
        self.verbose = verbose
        self.enable_cpu_stressor = enable_cpu_stressor
        
        self.transcoding_process: Optional[subprocess.Popen] = None
        self.stressor_process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.running = False
        self.stressor_started = False
        self.max_frame_seen = 0
        self.shutdown_requested = False
        
        # Register signal handlers for clean shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle termination signals"""
        if self.shutdown_requested:
            # If already shutting down and still receiving signals, force exit
            self._log("Force exit requested, terminating immediately...")
            os._exit(1)
        
        self.shutdown_requested = True
        if self.verbose:
            print(f"\nReceived signal {signum}, stopping processes...")
        self.stop()
        sys.exit(0)
    
    def _log(self, message: str) -> None:
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[RUN] {message}")
    
    def _start_cpu_stressor(self) -> bool:
        """Start the CPU stressor process"""
        if self.stressor_started:
            return True
            
        try:
            # Build CPU stressor command
            stressor_cmd = ['python3', 'cpu_stressor.py'] + self.stressor_args
            
            self._log(f"Starting CPU stressor: {' '.join(stressor_cmd)}")
            
            # Start CPU stressor process
            self.stressor_process = subprocess.Popen(
                stressor_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                preexec_fn=os.setsid  # Create new process group
            )
            
            self.stressor_started = True
            self._log("CPU stressor started successfully")
            return True
            
        except Exception as e:
            self._log(f"Error starting CPU stressor: {e}")
            return False
    
    def _monitor_transcoding_output(self) -> None:
        """Monitor transcoding process output in separate thread"""
        if not self.transcoding_process:
            return
            
        self._log("Starting transcoding output monitor")
        
        # Pattern to match "Encoded frame XX" - more flexible to catch different formats
        frame_pattern = re.compile(r'Encoded frame (\d+)')
        
        try:
            # Read stdout line by line
            while self.running and self.transcoding_process.poll() is None:
                try:
                    line = self.transcoding_process.stdout.readline()
                    if not line:
                        break
                        
                    line = line.strip()
                    if line:
                        # Print transcoding output
                        print(line)
                        
                        # Check for encoded frame messages
                        match = frame_pattern.search(line)
                        if match:
                            frame_number = int(match.group(1))
                            self.max_frame_seen = max(self.max_frame_seen, frame_number)
                            
                            # Start CPU stressor if threshold exceeded and CPU stressor is enabled
                            if (self.enable_cpu_stressor and 
                                frame_number >= self.frame_threshold and 
                                not self.stressor_started):
                                self._log(f"Frame {frame_number} >= threshold {self.frame_threshold}, starting CPU stressor")
                                self._start_cpu_stressor()
                                
                except Exception as e:
                    if self.running:  # Only log if we're still supposed to be running
                        self._log(f"Error reading line: {e}")
                    break
                    
        except Exception as e:
            if self.running:
                self._log(f"Error monitoring transcoding output: {e}")
        
        self._log("Transcoding output monitor stopped")
    
    def start(self) -> bool:
        """Start the transcoding process and monitoring"""
        if self.running:
            self._log("Already running")
            return False
            
        try:
            self._log("=" * 60)
            self._log("Starting Video Transcoding with CPU Stress Testing")
            self._log("=" * 60)
            self._log(f"Transcoding command: {' '.join(self.transcoding_cmd)}")
            self._log(f"Frame threshold: {self.frame_threshold}")
            if self.enable_cpu_stressor:
                self._log(f"CPU stressor args: {' '.join(self.stressor_args) if self.stressor_args else 'default'}")
            else:
                self._log("CPU stressor: DISABLED (only RTP input provided)")
            self._log("=" * 60)
            
            # Start transcoding process with new process group
            self.transcoding_process = subprocess.Popen(
                self.transcoding_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr to stdout
                text=True,
                bufsize=1,
                universal_newlines=True,
                preexec_fn=os.setsid  # Create new process group for easier cleanup
            )
            
            self.running = True
            
            # Start monitoring thread
            self.monitor_thread = threading.Thread(
                target=self._monitor_transcoding_output,
                daemon=True
            )
            self.monitor_thread.start()
            
            self._log("Transcoding process started, monitoring output...")
            self._log("Press Ctrl+C to stop (may take a moment to clean up)")
            
            # Wait for transcoding process to complete
            return_code = self.transcoding_process.wait()
            
            if return_code == 0:
                self._log("Transcoding completed successfully")
            else:
                self._log(f"Transcoding failed with return code: {return_code}")
                
            return return_code == 0
            
        except Exception as e:
            self._log(f"Error starting transcoding: {e}")
            return False
        finally:
            self.running = False
    
    def stop(self) -> None:
        """Stop all processes"""
        self.running = False
        
        # Stop CPU stressor process first (usually easier to kill)
        if (self.enable_cpu_stressor and 
            self.stressor_process and 
            self.stressor_process.poll() is None):
            self._log("Stopping CPU stressor process...")
            try:
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.stressor_process.pid), signal.SIGTERM)
                try:
                    self.stressor_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._log("Force killing CPU stressor process...")
                    os.killpg(os.getpgid(self.stressor_process.pid), signal.SIGKILL)
                    self.stressor_process.wait()
            except (OSError, ProcessLookupError):
                pass  # Process already terminated
        
        # Stop transcoding process
        if self.transcoding_process and self.transcoding_process.poll() is None:
            self._log("Stopping transcoding process...")
            try:
                # First try SIGTERM to process group
                os.killpg(os.getpgid(self.transcoding_process.pid), signal.SIGTERM)
                try:
                    self.transcoding_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._log("Transcoding process not responding, force killing...")
                    # Force kill the entire process group
                    os.killpg(os.getpgid(self.transcoding_process.pid), signal.SIGKILL)
                    self.transcoding_process.wait()
            except (OSError, ProcessLookupError):
                pass  # Process already terminated
        
        # Additional cleanup: kill any remaining processes
        try:
            # Kill any remaining server_transcoding processes
            subprocess.run(['pkill', '-f', 'server_transcoding'], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Kill any remaining stress-ng processes only if CPU stressor was enabled
            if self.enable_cpu_stressor:
                subprocess.run(['pkill', '-f', 'stress-ng'], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            pass
        
        # Wait for monitor thread with timeout
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
            
        self._log("All processes stopped")
        self._log(f"Maximum frame number seen: {self.max_frame_seen}")

def main():
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(
        description='Run video transcoding with CPU stress testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s rtp://192.168.2.3:9000
  %(prog)s rtp://192.168.2.3:9000 --threshold 100
  %(prog)s rtp://192.168.2.3:9000 --threshold 200 --cpu-args "-m 80 -s 10"
  %(prog)s rtp://192.168.2.3:9000 -t 150 --cpu-args "--mean 70 --std 15 --time 300"

CPU Stressor Arguments (passed to cpu_stressor.py):
  -m, --mean MEAN         Mean CPU load percentage (0-100, default: 50)
  -s, --std STD           Standard deviation of CPU load (default: 15)
  -i, --interval INTERVAL Load adjustment interval in seconds (default: 1)
  -c, --cores CORES       Number of CPU cores to use (0=auto, default: 0)
  -t, --time TIME         Test duration in seconds (0=unlimited, default: 0)
  -q, --quiet             Quiet mode
  --monitor-cpu           Enable real-time CPU monitoring

Note: The transcoding program may start multiple encoder threads for different resolutions.
      Use Ctrl+C to stop. If it doesn't respond immediately, press Ctrl+C again for force exit.
      The server_transcoding executable path is: {executable}
        """.format(executable=TRANSCODING_EXECUTABLE))
    
    parser.add_argument('input_url', 
                        help='Input URL for transcoding (e.g., rtp://192.168.2.3:9000)')
    parser.add_argument('extra_args', nargs='*',
                        help='Additional arguments for transcoding program')
    parser.add_argument('-t', '--threshold', type=int, default=200,
                        help='Frame count threshold to start CPU stressor (default: 200)')
    parser.add_argument('--cpu-args', type=str, default='',
                        help='Arguments for CPU stressor (in quotes, e.g., "-m 80 -s 10")')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Quiet mode - reduce output from runner')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show commands that would be run without executing')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.threshold < 0:
        print("Error: Threshold must be >= 0")
        sys.exit(1)
    
    # Build transcoding arguments
    transcoding_args = [args.input_url] + args.extra_args
    
    # Parse CPU stressor arguments
    stressor_args = []
    if args.cpu_args.strip():
        import shlex
        stressor_args = shlex.split(args.cpu_args.strip())
    
    # Determine if CPU stressor should be enabled
    # If only RTP input is provided (no extra args and no cpu args), disable CPU stressor
    enable_cpu_stressor = bool(args.extra_args or args.cpu_args.strip())
    
    # Check if transcoding executable exists
    if not os.path.isfile(TRANSCODING_EXECUTABLE):
        print(f"Error: Transcoding program not found: {TRANSCODING_EXECUTABLE}")
        print("Make sure you're running this script from the correct directory")
        print("and that server_transcoding has been compiled.")
        sys.exit(1)
    
    # Only check for cpu_stressor.py if CPU stressor is enabled
    if enable_cpu_stressor and not os.path.isfile('cpu_stressor.py'):
        print("Error: cpu_stressor.py not found in current directory")
        sys.exit(1)
    
    # Dry run mode
    if args.dry_run:
        print("DRY RUN MODE - Commands that would be executed:")
        print(f"Transcoding: {TRANSCODING_EXECUTABLE} {' '.join(transcoding_args)}")
        print(f"Frame threshold: {args.threshold}")
        if enable_cpu_stressor:
            print(f"CPU stressor: python3 cpu_stressor.py {' '.join(stressor_args)}")
        else:
            print("CPU stressor: DISABLED (only RTP input provided)")
        sys.exit(0)
    
    # Create and run controller
    controller = TranscodingController(
        transcoding_args=transcoding_args,
        frame_threshold=args.threshold,
        stressor_args=stressor_args,
        verbose=not args.quiet,
        enable_cpu_stressor=enable_cpu_stressor
    )
    
    try:
        success = controller.start()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received")
        controller.stop()
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        controller.stop()
        sys.exit(1)

if __name__ == "__main__":
    main() 