// 4G3NT1 firmware entry point (ESP32-C3) - wires the GPIO button through the
// portable gesture detector to the LED + generative audio. This is the
// hardware I/O shell; the full mode machine (templates, activations, takeovers,
// the scheduler) is ported from aibutton/config.py + aibutton/main.py as the
// next step - see README.md "Port plan". For now it demonstrates the verified
// cores end to end: gestures -> cues + LED, and the 5-tap on/off toggle.
//
// SCAFFOLD: requires the Arduino-ESP32 toolchain; not yet compiled/flashed.
#include <Arduino.h>

#include "hw_audio.h"
#include "hw_button.h"
#include "hw_led.h"
#include "sound_bank.h"

// Pin map - adjust to your wiring (see README.md "Hardware").
#define PIN_BUTTON 9     // momentary button to GND (active low)
#define PIN_LED_R 3
#define PIN_LED_G 4
#define PIN_LED_B 5
#define PIN_I2S_BCLK 0   // -> MAX98357A BCLK
#define PIN_I2S_LRC 1    // -> MAX98357A LRC
#define PIN_I2S_DIN 2    // -> MAX98357A DIN

using namespace aibutton;

static LedController led;
static AudioEngine audio;
static ButtonInput button;

static bool deviceOn = true;          // 5-tap toggles this (the global on/off)
static uint32_t lastChatterMs = 0;

void setup() {
  Serial.begin(115200);
  dsp::initTables();
  led.begin(PIN_LED_R, PIN_LED_G, PIN_LED_B, /*activeHigh=*/true);
  audio.begin(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DIN);
  button.begin(PIN_BUTTON, /*activeLow=*/true);
  led.setState(LedState::Idle);
  audio.play(dsp::CueId::Wake);
}

void loop() {
  const uint32_t now = millis();
  const Trigger g = button.poll(now);

  if (g == Trigger::Quintuple) {
    // The global escape: toggle the device off/on (matches the Pi's contextual
    // 5-tap; a full port also uses it to exit an active takeover).
    deviceOn = !deviceOn;
    led.setState(deviceOn ? LedState::Idle : LedState::Off);
    audio.play(deviceOn ? dsp::CueId::Wake : dsp::CueId::Sleep);
  } else if (deviceOn && g != Trigger::None) {
    switch (g) {
      case Trigger::Short:  led.setState(LedState::Listening); audio.play(dsp::CueId::Ack); break;
      case Trigger::Long:   led.setState(LedState::Success);   audio.play(dsp::CueId::Success); break;
      case Trigger::Double: led.setState(LedState::Success);   audio.play(dsp::CueId::Phase); break;
      default: break;
    }
  }

  // A little R2-D2 idle chatter every ~30 s while on and resting.
  if (deviceOn && now - lastChatterMs > 30000) {
    lastChatterMs = now;
    audio.play(dsp::CueId::IdleChatter);
  }

  led.tick(now);
  delay(2);  // ~500 Hz poll; the audio runs on its own task
}
