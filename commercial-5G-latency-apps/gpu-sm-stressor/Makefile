# GPU SM Usage Control Tool Makefile

# Compiler settings and flags
NVCC = nvcc
CFLAGS = -std=c++14 -O2 -Xcompiler -pthread
LIBS = -lcuda -lcudart -lm -lpthread

# Target file
TARGET = gpu_sm_stressor
SOURCE = gpu_sm_stressor.cu

# Default target
all: $(TARGET)

# Compile main program
$(TARGET): $(SOURCE)
	$(NVCC) $(CFLAGS) -o $(TARGET) $(SOURCE) $(LIBS)

# Clean compiled files
clean:
	rm -f $(TARGET)

# Install to system path (optional)
install: $(TARGET)
	sudo cp $(TARGET) /usr/local/bin/
	sudo chmod +x /usr/local/bin/$(TARGET)

# Uninstall
uninstall:
	sudo rm -f /usr/local/bin/$(TARGET)

# Run test (50% usage)
test: $(TARGET)
	./$(TARGET) 50

# Show help
help:
	@echo "GPU SM Usage Control Tool Build Instructions:"
	@echo ""
	@echo "Build commands:"
	@echo "  make          - Compile the program"
	@echo "  make clean    - Clean compiled files"
	@echo "  make install  - Install to system path"
	@echo "  make test     - Run test (50% usage)"
	@echo ""
	@echo "Usage:"
	@echo "  ./gpu_sm_stress <percentage 0-100>"
	@echo "  Example: ./gpu_sm_stress 75"
	@echo ""
	@echo "Dependencies:"
	@echo "  - NVIDIA GPU driver"
	@echo "  - CUDA Toolkit"
	@echo "  - GCC compiler"

.PHONY: all clean install uninstall test help