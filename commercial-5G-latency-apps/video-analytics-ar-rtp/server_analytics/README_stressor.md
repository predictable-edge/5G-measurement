# GPU Stressor Integration with server_analytics

This document explains how to use the integrated GPU stressor functionality with the server_analytics pipeline.

## Overview

The `run.py` script now supports automatically launching a GPU stressor when frame 101 is detected in the video processing pipeline. This allows for controlled GPU load testing during video analytics operations.

## Usage

### Basic Usage (No Stressor)
```bash
# Run without GPU stressor (original behavior)
python3 run.py rtp://0.0.0.0:9000
```

### With GPU Stressor
```bash
# Enable GPU stressor with 70% mean load, 15% standard deviation
python3 run.py rtp://0.0.0.0:9000 --stressor-mean 70

# Full configuration example
python3 run.py rtp://0.0.0.0:9000 \
    --stressor-mean 60 \
    --stressor-std 20 \
    --stressor-interval 1.0 \
    --stressor-time 300 \
    --stressor-quiet
```

## GPU Stressor Options

| Option | Description | Default |
|--------|-------------|---------|
| `--stressor-mean FLOAT` | Mean GPU load percentage (0-100) | Required to enable stressor |
| `--stressor-std FLOAT` | Standard deviation of load | 15 |
| `--stressor-interval FLOAT` | Load adjustment interval (seconds) | 1.0 |
| `--stressor-time INT` | Stressor duration (seconds, 0=unlimited) | 0 |
| `--stressor-quiet` | Run stressor in quiet mode | False |
| `--stressor-seed INT` | Random seed for reproducible results | Auto |

## Trigger Behavior

- The GPU stressor will **automatically start** when the output contains "Sent frame 101"
- This ensures the stressor begins after the video processing pipeline is fully initialized
- If no `--stressor-mean` is specified, no stressor will be compiled or started

## Example Scenarios

### Light Variable Load Testing
```bash
python3 run.py rtp://0.0.0.0:9000 --stressor-mean 30 --stressor-std 10
```
- Creates light GPU load with low variability
- Good for testing baseline performance impact

### Heavy Variable Load Testing  
```bash
python3 run.py rtp://0.0.0.0:9000 --stressor-mean 80 --stressor-std 20
```
- Creates heavy GPU load with high variability
- Tests system behavior under stress

### Controlled Duration Test
```bash
python3 run.py rtp://0.0.0.0:9000 \
    --stressor-mean 50 \
    --stressor-time 180 \
    --stressor-quiet
```
- Runs stressor for exactly 3 minutes
- Quiet mode reduces output noise

### Reproducible Testing
```bash
python3 run.py rtp://0.0.0.0:9000 \
    --stressor-mean 65 \
    --stressor-seed 12345
```
- Uses fixed random seed for consistent load patterns
- Useful for comparing test runs

## Monitoring

The script will show:
1. Compilation status for both server_analytics and GPU stressor
2. Configured stressor parameters (if enabled)
3. "=== DETECTED FRAME 101 - Starting GPU Stressor ===" when triggered
4. GPU stressor PID for monitoring
5. Clean termination of all processes on Ctrl+C

## Notes

- The stressor requires CUDA-capable GPU and proper CUDA toolkit installation
- Stressor compilation errors are treated as warnings (pipeline continues without stressor)
- All processes (server_analytics, yolo detection, GPU stressor) are terminated together
- The stressor uses the same normal distribution algorithm as the standalone version 