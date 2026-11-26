# Activity: the aarch64 binary and the host preview. No external libraries.
CXX ?= aarch64-linux-gnu-g++
CXXFLAGS ?= -O2 -std=c++17
LDFLAGS ?= -s
FONT_CFLAGS ?= $(shell pkg-config --cflags freetype2)
FONT_LIBS ?= $(shell pkg-config --libs freetype2)

all: banana-activity

banana-activity: banana-activity.cpp activity-font.h activity-logo.h ../../../ui/src/app-fallback-font.h
	$(CXX) $(CXXFLAGS) $(FONT_CFLAGS) $(LDFLAGS) -o $@ banana-activity.cpp $(FONT_LIBS)

# A build for the machine you are on, for --smoke renders (it draws, but has no DRM/evdev).
host: banana-activity.cpp activity-font.h activity-logo.h
	g++ -O2 -std=c++17 $(shell pkg-config --cflags freetype2) -o activity-host banana-activity.cpp $(shell pkg-config --libs freetype2)

clean:
	rm -f banana-activity activity-host

.PHONY: all host clean
