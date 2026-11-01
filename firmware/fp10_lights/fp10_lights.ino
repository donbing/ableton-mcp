// FP10 Lights: USB MIDI -> SK9822 strip over the piano keys
// Waveshare ESP32-S3-Zero, USB Mode must be "USB-OTG (TinyUSB)". See README.md.
//
// Channel 1  play     lit while held, fades on release, held by sustain (CC64)
// Channel 2  hint     steady while held
// Channel 3  correct  short green flash
// Channel 4  wrong    short red flash
// CC120 / CC123 on any channel clears everything
//
// Wireless update mode (Wi-Fi is off otherwise):
//   hold BOOT for 2s, send CC119 >= 64 on channel 16 (< 64 turns it off), or type "update" on serial
//   onboard LED: amber blink = connecting, purple = ready, white = updating, red = failed
//   turns itself off after 10 minutes without an update
//
// Wi-Fi details live in the board's flash, never in this code. Set them once over USB serial:
//   set ssid <name> / set pass <password> / set otapass <password> / show / forget / update / help

#include <Arduino.h>
#include "USB.h"
#include "USBMIDI.h"
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <Preferences.h>
#include <FastLED.h>

#if ARDUINO_USB_MODE
#error Set Tools > USB Mode to "USB-OTG (TinyUSB)"
#endif

// ---- Strip ----
#define DATA_PIN     2
#define CLOCK_PIN    1
#define COLOR_ORDER  BGR
#define NUM_LEDS     144
#define MAX_MA       300     // 500mA hub port; SK9822s also idle at ~0.5-1mA each, which FastLED doesn't count
#define ONBOARD_PIN  21

// ---- Key mapping (calibrate these) ----
#define FIRST_NOTE      29     // MIDI note above LED 0 (29 = F1)
#define LEDS_PER_NOTE   2.02f  // 144/m strip over an 88-key keyboard
#define LEDS_PER_KEY    2
#define REVERSED        false  // true if the strip's input end is at the treble end

// ---- Wireless update ----
#define HOSTNAME        "fp10-lights"
#define BOOT_PIN        0
#define BOOT_HOLD_MS    2000
#define OTA_CHANNEL     15     // MIDI channel 16
#define OTA_CC          119
#define OTA_TIMEOUT_MS  (10UL * 60 * 1000)
#define WIFI_TIMEOUT_MS 20000

// ---- Look ----
const CRGB CH_COLOUR[4] = {
  CRGB(0, 140, 255),   // play
  CRGB(255, 110, 0),   // hint
  CRGB(0, 255, 40),    // correct
  CRGB(255, 0, 0),     // wrong
};
const float PLAY_FADE  = 0.03f;   // per 10ms frame, ~330ms to dark
const float FLASH_FADE = 0.025f;  // ~400ms
const float HINT_LEVEL = 0.6f;
const float MIN_LEVEL  = 0.2f;    // softest note still visible

USBMIDI MIDI("FP10 Lights");
Preferences prefs;
CRGB leds[NUM_LEDS];
CRGB onboard[1];

float level[4][128];     // brightness per channel per note
bool  held[4][128];      // key physically down (play) or hint on
bool  sustained[128];    // play notes released while pedal down
bool  pedal = false;
uint32_t lastMidiMs = 0;

enum OtaState { OTA_OFF, OTA_CONNECTING, OTA_READY, OTA_UPDATING, OTA_FAILED };
OtaState ota = OTA_OFF;
uint32_t otaSince = 0;

void clearAll() {
  memset(level, 0, sizeof(level));
  memset(held, 0, sizeof(held));
  memset(sustained, 0, sizeof(sustained));
}

// ---- Settings (NVS) ----

String setting(const char *key) {
  prefs.begin("fp10", true);
  String v = prefs.getString(key, "");
  prefs.end();
  return v;
}

void saveSetting(const char *key, const String &v) {
  prefs.begin("fp10", false);
  if (v.length()) prefs.putString(key, v);
  else prefs.remove(key);
  prefs.end();
}

// ---- Wireless update ----

void otaStop(OtaState next = OTA_OFF) {
  ArduinoOTA.end();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  ota = next;
  otaSince = millis();
  Serial.println("OTA: Wi-Fi off");
}

void otaStart() {
  if (ota == OTA_CONNECTING || ota == OTA_READY) return;
  String ssid = setting("ssid");
  if (!ssid.length()) {
    Serial.println("OTA: no Wi-Fi set, use: set ssid <name> / set pass <password>");
    ota = OTA_FAILED;
    otaSince = millis();
    return;
  }
  Serial.printf("OTA: connecting to %s\n", ssid.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.begin(ssid.c_str(), setting("pass").c_str());
  ota = OTA_CONNECTING;
  otaSince = millis();
}

void otaSetup() {
  ArduinoOTA.setHostname(HOSTNAME);
  ArduinoOTA.onStart([] {
    ota = OTA_UPDATING;
    clearAll();
    FastLED.clear();
    onboard[0] = CRGB(40, 40, 40);
    FastLED.show();
  });
  ArduinoOTA.onError([](ota_error_t e) {
    Serial.printf("OTA: error %u\n", e);
    otaStop(OTA_FAILED);
  });
}

void otaService() {
  uint32_t age = millis() - otaSince;
  switch (ota) {
    case OTA_CONNECTING:
      if (WiFi.status() == WL_CONNECTED) {
        String otaPass = setting("otapass");
        if (otaPass.length()) ArduinoOTA.setPassword(otaPass.c_str());
        ArduinoOTA.begin();
        ota = OTA_READY;
        otaSince = millis();
        Serial.printf("OTA: ready at %s.local (%s)\n", HOSTNAME, WiFi.localIP().toString().c_str());
      } else if (age > WIFI_TIMEOUT_MS) {
        Serial.println("OTA: Wi-Fi connect timed out");
        otaStop(OTA_FAILED);
      }
      break;
    case OTA_READY:
      ArduinoOTA.handle();
      if (age > OTA_TIMEOUT_MS) otaStop();
      break;
    case OTA_FAILED:
      if (age > 5000) ota = OTA_OFF;
      break;
    default:
      break;
  }
}

void checkBootButton() {
  static uint32_t pressedAt = 0;
  static bool fired = false;
  if (digitalRead(BOOT_PIN) == LOW) {
    if (!pressedAt) pressedAt = millis();
    if (!fired && millis() - pressedAt >= BOOT_HOLD_MS) {
      fired = true;
      otaStart();
    }
  } else {
    pressedAt = 0;
    fired = false;
  }
}

// ---- Serial commands ----

void runCommand(String line) {
  line.trim();
  if (line.startsWith("set ")) {
    String rest = line.substring(4);
    int sp = rest.indexOf(' ');
    String key = sp < 0 ? rest : rest.substring(0, sp);
    String value = sp < 0 ? "" : rest.substring(sp + 1);
    if (key == "ssid" || key == "pass" || key == "otapass") {
      saveSetting(key.c_str(), value);
      Serial.printf("%s %s\n", key.c_str(), value.length() ? "saved" : "cleared");
    } else {
      Serial.println("keys: ssid, pass, otapass");
    }
  } else if (line == "show") {
    String ssid = setting("ssid");
    Serial.printf("ssid: %s\npass: %s\notapass: %s\n",
                  ssid.length() ? ssid.c_str() : "(not set)",
                  setting("pass").length() ? "set" : "not set",
                  setting("otapass").length() ? "set" : "not set");
  } else if (line == "forget") {
    prefs.begin("fp10", false);
    prefs.clear();
    prefs.end();
    Serial.println("settings cleared");
  } else if (line == "update") {
    otaStart();
  } else if (line.length()) {
    Serial.println("commands: set ssid <name> | set pass <password> | set otapass <password> | show | forget | update");
  }
}

void readSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (line.length()) runCommand(line);
      line = "";
    } else if (line.length() < 128) {
      line += c;
    }
  }
}

// ---- MIDI ----

void noteOn(int ch, int note, int vel) {
  held[ch][note] = true;
  if (ch == 0) {
    sustained[note] = false;
    level[ch][note] = max(MIN_LEVEL, vel / 127.0f);
  } else if (ch == 1) {
    level[ch][note] = HINT_LEVEL;
  } else {
    level[ch][note] = 1.0f;
  }
}

void noteOff(int ch, int note) {
  held[ch][note] = false;
  if (ch == 0 && pedal) sustained[note] = true;
}

void sustainPedal(bool down) {
  pedal = down;
  if (!down) memset(sustained, 0, sizeof(sustained));
}

void handlePacket(const midiEventPacket_t &p) {
  uint8_t type = p.byte1 & 0xF0;
  uint8_t ch = p.byte1 & 0x0F;
  uint8_t d1 = p.byte2 & 0x7F, d2 = p.byte3 & 0x7F;

  if (type == 0xB0 && (d1 == 120 || d1 == 123)) { clearAll(); return; }
  if (type == 0xB0 && ch == OTA_CHANNEL && d1 == OTA_CC) {
    if (d2 >= 64) otaStart();
    else if (ota != OTA_OFF) otaStop();
    return;
  }
  if (ch > 3) return;
  lastMidiMs = millis();

  if (type == 0x90 && d2 > 0) noteOn(ch, d1, d2);
  else if (type == 0x80 || type == 0x90) noteOff(ch, d1);
  else if (type == 0xB0 && d1 == 64 && ch == 0) sustainPedal(d2 >= 64);
}

// ---- Lights ----

void updateLevels() {
  for (int n = 0; n < 128; n++) {
    if (!held[0][n] && !sustained[n]) level[0][n] = max(0.0f, level[0][n] - PLAY_FADE);
    if (!held[1][n]) level[1][n] = 0;
    level[2][n] = max(0.0f, level[2][n] - FLASH_FADE);
    level[3][n] = max(0.0f, level[3][n] - FLASH_FADE);
  }
}

CRGB statusColour() {
  bool blink = (millis() / 250) % 2;
  switch (ota) {
    case OTA_CONNECTING: return blink ? CRGB(40, 20, 0) : CRGB::Black;
    case OTA_READY:      return CRGB(30, 0, 40);
    case OTA_UPDATING:   return CRGB(40, 40, 40);
    case OTA_FAILED:     return CRGB(50, 0, 0);
    default:             return (millis() - lastMidiMs < 60) ? CRGB(0, 0, 40) : CRGB(0, 4, 0);
  }
}

void render() {
  FastLED.clear();
  for (int n = 0; n < 128; n++) {
    int first = lroundf((n - FIRST_NOTE) * LEDS_PER_NOTE);
    for (int ch = 0; ch < 4; ch++) {
      if (level[ch][n] <= 0) continue;
      CRGB c = CH_COLOUR[ch];
      c.nscale8_video(uint8_t(level[ch][n] * 255));
      for (int k = 0; k < LEDS_PER_KEY; k++) {
        int i = first + k;
        if (i < 0 || i >= NUM_LEDS) continue;
        leds[REVERSED ? NUM_LEDS - 1 - i : i] += c;
      }
    }
  }
  onboard[0] = statusColour();
  FastLED.show();
}

void bootSweep() {
  for (int i = 0; i < NUM_LEDS; i += 2) {
    FastLED.clear();
    leds[i] = CRGB(0, 40, 80);
    FastLED.show();
    delay(4);
  }
  FastLED.clear(true);
}

void setup() {
  Serial.begin(115200);
  pinMode(BOOT_PIN, INPUT_PULLUP);
  WiFi.mode(WIFI_OFF);
  FastLED.addLeds<SK9822, DATA_PIN, CLOCK_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.addLeds<WS2812, ONBOARD_PIN, RGB>(onboard, 1);
  FastLED.setMaxPowerInVoltsAndMilliamps(5, MAX_MA);
  FastLED.setDither(1);
  clearAll();
  otaSetup();
  MIDI.begin();
  USB.begin();
  bootSweep();
}

void loop() {
  midiEventPacket_t p;
  while (MIDI.readPacket(&p)) handlePacket(p);
  readSerial();
  checkBootButton();
  otaService();

  static uint32_t lastFrame = 0;
  if (millis() - lastFrame >= 10) {
    lastFrame = millis();
    updateLevels();
    render();
  }
}
