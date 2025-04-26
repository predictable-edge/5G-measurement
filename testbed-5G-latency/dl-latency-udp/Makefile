CXX = g++
CXXFLAGS = -std=c++11 -Wall -Wextra -O2
LDFLAGS = -pthread

all: server client

server: server.cpp
	$(CXX) $(CXXFLAGS) -o server server.cpp $(LDFLAGS)

client: client.cpp
	$(CXX) $(CXXFLAGS) -o client client.cpp $(LDFLAGS)

clean:
	rm -f server client

.PHONY: all clean
