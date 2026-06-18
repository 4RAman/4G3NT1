# Host-native build of the portable firmware cores (gesture detector + synth
# DSP) and their unit tests - no ESP32 toolchain or PlatformIO required, so the
# algorithmic heart of the port can be verified anywhere with g++.
#
#   make test     # build + run the native tests
#   make clean
#
# The ESP32 build (Arduino glue in src/, hardware drivers) is a separate path -
# see README.md and platformio.ini - and is not built by this Makefile.

CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Ilib/gesture -Ilib/synth
BUILD := build

GESTURE_SRC := lib/gesture/trigger_detector.cpp
SYNTH_SRC := lib/synth/synth.cpp lib/synth/sound_bank.cpp

.PHONY: test clean
test: $(BUILD)/test_gesture $(BUILD)/test_synth
	@echo "--- gesture ---" && $(BUILD)/test_gesture
	@echo "--- synth ---" && $(BUILD)/test_synth

$(BUILD)/test_gesture: test/test_gesture.cpp $(GESTURE_SRC) | $(BUILD)
	$(CXX) $(CXXFLAGS) $^ -o $@

$(BUILD)/test_synth: test/test_synth.cpp $(SYNTH_SRC) | $(BUILD)
	$(CXX) $(CXXFLAGS) $^ -o $@

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(BUILD)
