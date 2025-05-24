# Compiler
CXX := g++

# Compiler Flags
CXXFLAGS := -std=c++17 -Wall -O3 $(shell pkg-config --cflags libavformat libavcodec libavutil libswscale)

# Linker Flags
LDFLAGS := $(shell pkg-config --libs libavformat libavcodec libavutil libswscale)

# Target Executable
TARGET := server_transcoding

# Source Files
SRCS := server_transcoding.cpp

# Header Files
HDRS := $(wildcard *.h)

RESULT := frame*

# Object Files
OBJS := $(SRCS:.cpp=.o)

# Dependency Files
DEPS := $(SRCS:.cpp=.d)

# Default Target
all: $(TARGET)

# Link the target executable
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

# Generate dependency files
%.d: %.cpp
	@$(CXX) -MM $(CXXFLAGS) $< > $@

# Include dependency files
-include $(DEPS)

# Compile source files into object files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean up build artifacts
clean:
	rm -f $(OBJS) $(TARGET) $(RESULT) $(DEPS)

clog:
	rm -f $(RESULT)

# Phony Targets
.PHONY: all clean