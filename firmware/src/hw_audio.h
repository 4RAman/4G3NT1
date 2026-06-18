// I2S audio output for the ESP32-C3 + MAX98357A class-D amp - the firmware
// home of the synth. A FreeRTOS render task pulls cues from a queue, renders
// them through the synth Voice (sound_bank.cpp), and streams them to I2S; this
// is the live, generative replacement for the Pi's pre-rendered WAVs.
//
// SCAFFOLD: written against the ESP-IDF i2s_std driver; not yet compiled.
#pragma once

#include "sound_bank.h"

namespace aibutton {

class AudioEngine {
 public:
  // bclk/lrc/din are the I2S pins to the MAX98357A.
  bool begin(int bclk, int lrc, int din);
  void play(dsp::CueId cue);   // queue a one-shot cue
  void startRinging();         // loop the Alarm cue until stopRinging()
  void stopRinging();

 private:
  static void renderTask(void* arg);
  void* i2s_ = nullptr;        // i2s_chan_handle_t
  void* queue_ = nullptr;      // QueueHandle_t of CueId
  volatile bool ringing_ = false;
  dsp::Voice voice_;
};

}  // namespace aibutton
