# Compiler
CXX := g++

# Set pkg-config path to include Homebrew's pkgconfig directory
export PKG_CONFIG_PATH := /opt/homebrew/lib/pkgconfig:$(PKG_CONFIG_PATH)

# Additional include paths if pkg-config fails
FFMPEG_INCLUDE := -I/opt/homebrew/Cellar/ffmpeg/7.1.1_2/include
FFMPEG_LIBS := -L/opt/homebrew/Cellar/ffmpeg/7.1.1_2/lib -lavformat -lavcodec -lavutil -lswscale

# Compiler Flags
CXXFLAGS := -std=c++17 -Wall -O3 $(shell pkg-config --cflags libavformat libavcodec libavutil libswscale 2>/dev/null || echo "$(FFMPEG_INCLUDE)")

# Linker Flags
LDFLAGS := $(shell pkg-config --libs libavformat libavcodec libavutil libswscale 2>/dev/null || echo "$(FFMPEG_LIBS)")

# Target Executable
TARGET := client_streaming

# Source Files
SRCS := client_streaming.cpp

RESULT := frame*

# Object Files
OBJS := $(SRCS:.cpp=.o)

# Default Target
all: $(TARGET)

# Link the target executable
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

# Compile source files into object files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean up build artifacts
clean:
	rm -f $(OBJS) $(TARGET) $(RESULT)

clog:
	rm -f $(RESULT)

# Phony Targets
.PHONY: all clean