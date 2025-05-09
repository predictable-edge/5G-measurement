CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -pedantic -pthread
LDFLAGS = -pthread

# Targets
.PHONY: all clean

all: aws_server

# C++ AWS Server
aws_server: aws_server.cpp
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

# Cleanup
clean:
	rm -f aws_server

# Help
help:
	@echo "Makefile for AWS Server"
	@echo ""
	@echo "Usage:"
	@echo "    make              - Build aws_server executable"
	@echo "    make clean        - Remove generated files"
	@echo "    make help         - Display this help message"
