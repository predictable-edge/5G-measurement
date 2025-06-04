# GPU SM Usage Control Tool Makefile

# Compiler settings and flags
CXX = nvcc
TARGET = gpu_sm_stressor
SOURCE = gpu_sm_stressor.cu

# CUDA architecture settings (adjust based on your GPU)
CUDA_ARCH = -arch=sm_75

# Compiler flags
CXXFLAGS = -O3 -std=c++11 -Xcompiler -fPIC -Xcompiler -pthread
LDFLAGS = -lcuda -lcudart -lm

# Build targets
all: $(TARGET)

$(TARGET): $(SOURCE)
	$(CXX) $(CUDA_ARCH) $(CXXFLAGS) -o $(TARGET) $(SOURCE) $(LDFLAGS)

clean:
	rm -f $(TARGET)

install: $(TARGET)
	cp $(TARGET) /usr/local/bin/

# Uninstall
uninstall:
	sudo rm -f /usr/local/bin/$(TARGET)

# Run test (50% usage)
test: $(TARGET)
	./$(TARGET) -m 50

# Show help
help:
	@echo "Available targets:"
	@echo "  all     - Build the GPU SM stressor (default)"
	@echo "  clean   - Remove built files"
	@echo "  install - Install binary to /usr/local/bin"
	@echo "  help    - Show this help message"
	@echo ""
	@echo "Usage examples:"
	@echo "  make                    # Build the program"
	@echo "  ./gpu_sm_stressor -h    # Show program help"
	@echo "  ./gpu_sm_stressor -m 70 -s 15 -i 1.0  # 70% mean load, 15% std dev"

.PHONY: all clean install uninstall test help