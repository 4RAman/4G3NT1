// SCAFFOLD - requires the ESP-IDF/Arduino-ESP32 toolchain (i2s_std, FreeRTOS).
#include "hw_audio.h"

#include <Arduino.h>
#include <cmath>

#include "driver/i2s_std.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

namespace aibutton {

namespace {
constexpr int kSampleRate = static_cast<int>(dsp::kSampleRate);
constexpr int kChunk = 512;  // samples rendered per I2S write

// Float [-1,1] -> 16-bit, duplicated to L/R for the mono MAX98357A.
void writeChunk(i2s_chan_handle_t tx, const float* mono, int n) {
  static int16_t stereo[kChunk * 2];
  if (n > kChunk) n = kChunk;
  for (int i = 0; i < n; ++i) {
    int v = static_cast<int>(mono[i] * 30000.0f);
    if (v > 32767) v = 32767; if (v < -32768) v = -32768;
    stereo[2 * i] = stereo[2 * i + 1] = static_cast<int16_t>(v);
  }
  size_t wrote = 0;
  i2s_channel_write(tx, stereo, n * 2 * sizeof(int16_t), &wrote, portMAX_DELAY);
}
}  // namespace

bool AudioEngine::begin(int bclk, int lrc, int din) {
  dsp::initTables();
  voice_.setSampleRate(dsp::kSampleRate);

  i2s_chan_handle_t tx = nullptr;
  i2s_chan_config_t chanCfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  if (i2s_new_channel(&chanCfg, &tx, nullptr) != ESP_OK) return false;
  i2s_std_config_t stdCfg = {
      .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(kSampleRate),
      .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
          I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
      .gpio_cfg = {
          .mclk = I2S_GPIO_UNUSED,
          .bclk = static_cast<gpio_num_t>(bclk),
          .ws = static_cast<gpio_num_t>(lrc),
          .dout = static_cast<gpio_num_t>(din),
          .din = I2S_GPIO_UNUSED,
          .invert_flags = {false, false, false},
      },
  };
  if (i2s_channel_init_std_mode(tx, &stdCfg) != ESP_OK) return false;
  i2s_channel_enable(tx);
  i2s_ = tx;

  queue_ = xQueueCreate(8, sizeof(dsp::CueId));
  xTaskCreatePinnedToCore(renderTask, "synth", 4096, this, 5, nullptr, 0);
  return true;
}

void AudioEngine::play(dsp::CueId cue) {
  if (queue_) xQueueSend(static_cast<QueueHandle_t>(queue_), &cue, 0);
}

void AudioEngine::startRinging() { ringing_ = true; }
void AudioEngine::stopRinging() { ringing_ = false; }

void AudioEngine::renderTask(void* arg) {
  auto* self = static_cast<AudioEngine*>(arg);
  auto tx = static_cast<i2s_chan_handle_t>(self->i2s_);
  auto q = static_cast<QueueHandle_t>(self->queue_);
  static float buf[kSampleRate * 2];  // up to ~2 s per cue
  static float silence[kChunk] = {0};
  uint32_t rng = 0xA1B2C3D4u;

  for (;;) {
    dsp::CueId cue;
    if (self->ringing_) {
      // Re-render the Alarm cue continuously until dismissed.
      const int n = dsp::renderCue(dsp::CueId::Alarm, self->voice_, buf, kSampleRate * 2, rng);
      for (int off = 0; off < n && self->ringing_; off += kChunk) {
        writeChunk(tx, buf + off, n - off < kChunk ? n - off : kChunk);
      }
    } else if (xQueueReceive(q, &cue, pdMS_TO_TICKS(20)) == pdTRUE) {
      const int n = dsp::renderCue(cue, self->voice_, buf, kSampleRate * 2, rng);
      for (int off = 0; off < n; off += kChunk) {
        writeChunk(tx, buf + off, n - off < kChunk ? n - off : kChunk);
      }
    } else {
      writeChunk(tx, silence, kChunk);  // keep the DMA fed
    }
  }
}

}  // namespace aibutton
