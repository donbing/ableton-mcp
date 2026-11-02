// FP10 Lights: USB MIDI -> SK9822 strip over the piano keys
// Waveshare ESP32-S3-Zero, USB Mode must be "USB-OTG (TinyUSB)". See README.md.
//
// Channel 1  play     lit while held, fades on release; with sustain (CC64) down, fades slowly instead
// Channel 2  hint     steady while held, brightness from velocity (127 = full)
// Channel 3  correct  short green flash
// Channel 4  wrong    short red flash
// CC120 / CC123 on any channel clears everything
//
// Wireless update mode (Wi-Fi is off otherwise):
//   hold BOOT for 2s, send CC119 >= 64 on channel 16 (< 64 turns it off), or type "update" on serial
//   onboard LED: amber blink = connecting, purple = ready, white = updating, red = failed
//   turns itself off after 10 minutes without an update
//
// Calibration mode: send CC118 >= 64 on channel 16 (< 64 cancels), or type "calibrate" on serial.
//   A white LED shows where C1 lights. Play any key below C1 to move it left, above to move it right,
//   then C1 to accept. The same for C6. Both points are saved on the board. Onboard LED: cyan.
//
// Options, saved on the board (board.sh split / sparks):
//   CC116 on channel 16 = split note: play notes below it (the left hand) light LEFT_COLOUR; 0 = off
//   CC115 on channel 16 >= 64 / < 64: sparks on / off: each play note throws sparks along the strip
//
// Restart: CC117 >= 64 on channel 16 (board.sh restart / restart-test, for testing how the Push takes it back).
//   If the Push hasn't set the board up 3 s after it starts, it restarts itself (usbWatch()).
//
// Wi-Fi details live in the board's flash, never in this code. Set them once over USB serial:
//   set ssid <name> / set pass <password> / set otapass <password> / show / forget / update / calibrate

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
#define MAX_MA       250     // strip cap, idle included (~1mA per LED); shares a 500mA hub port with the board
#define LED_MA       20.0f   // one SK9822 colour at full
#define BRIGHTNESS   128     // 0-255, for everything on the strip (not the status LED); also halves the current
#define ONBOARD_PIN  21

// ---- Key mapping ----
// Which LED sits under the middle of two C keys; keys in between follow the real keyboard layout at the
// back of the keys (see keyPos).
// The LEDs are set on the piano with calibration mode and saved on the board; these are the defaults.
#define CAL_LOW_NOTE    36     // MIDI 36 = C1 in Live's names
#define CAL_LOW_LED     14.1f
#define CAL_HIGH_NOTE   96     // MIDI 96 = C6 in Live's names
#define CAL_HIGH_LED    135.3f
#define CAL_CC          118    // on OTA_CHANNEL
#define CAL_TIMEOUT_MS  (5UL * 60 * 1000)
#define WHITE_SPAN      0.0f   // share of a white key's width to light; 0 = only the LED nearest the middle
#define BLACK_SPAN      0.0f   // the same for black keys (0.8 / 0.5 lights 2-3 LEDs per key)
#define REVERSED        false  // true if the strip's input end is at the treble end

// ---- Wireless update ----
#define HOSTNAME        "fp10-lights"
#define BOOT_PIN        0
#define BOOT_HOLD_MS    2000
#define OTA_CHANNEL     15     // MIDI channel 16
#define OTA_CC          119
#define RESTART_CC      117    // on OTA_CHANNEL
#define SPLIT_CC        116    // on OTA_CHANNEL
#define SPARKS_CC       115    // on OTA_CHANNEL
#define USB_SETUP_MS    3000   // not set up by the Push this long after starting: restart (see usbWatch())
#define OTA_TIMEOUT_MS  (10UL * 60 * 1000)
#define WIFI_TIMEOUT_MS 20000

// ---- Look ----
const CRGB CH_COLOUR[4] = {
  CRGB(0, 140, 255),   // play
  CRGB(255, 110, 0),   // hint
  CRGB(0, 255, 40),    // correct
  CRGB(255, 0, 0),     // wrong
};
// Play notes fade out evenly to the eye, all the way to dark: the fade runs in perceived brightness (light to the
// power 1/HD_GAMMA, the value the strip is sent), not in light, where most of it was too bright to see change.
// These are the times from full to dark; softer notes start lower and get there sooner.
const float RELEASE_MS = 450;     // key released
const float SUSTAIN_MS = 4000;    // key released with the pedal down, like a held piano note dying away
const float FLASH_FADE = 0.025f;  // ~400ms
const float HINT_LEVEL = 0.6f;    // a hint at velocity 127; softer hints are dimmer, on the same curve as play
// Velocity sets perceived brightness, evenly from MIN_SEEN at velocity 1 to full at 127. (Setting light from
// velocity instead left the softest note at ~56% of the loudest to the eye, so playing soft and loud looked alike.)
const float MIN_SEEN   = 0.3f;    // softest note, in perceived brightness (light^(1/HD_GAMMA))

const CRGB LEFT_COLOUR = CRGB(210, 0, 255);  // play notes below the split, when it's on: violet, away from the rest

// Sparks: each play note throws 2-4 from its key, out along the strip. They start white-hot, cool to the note's
// colour, slow down and fade. Harder notes throw more, faster and brighter.
#define MAX_SPARKS     48
const float SPARK_SPEED = 0.8f;   // LEDs per 10 ms frame at velocity 127, before the random spread
const float SPARK_DRAG  = 0.93f;  // speed kept per frame: a spark at full speed travels ~11 LEDs
const float SPARK_MS    = 500;    // average life

// The strip runs as FastLED's SK9822HD: it applies a 2.8 gamma to what it's sent and uses the chips' 5-bit global
// brightness, which gives fine steps near dark (plain SK9822 has ~128 steps at 50% brightness and dithering
// between them flickered at the end of fades). Everything below works in linear light, 0-1, and toHd() undoes
// the gamma so the look stays as it was.
const float HD_GAMMA = 2.8f;

// Power cap tiers, cut from the last up: hints and flashes keep their brightness longest, then held play notes;
// released play notes (fading, or held by the pedal) dim first.
enum Tier { TIER_GUIDE, TIER_HELD, TIER_FADING, TIERS };

USBMIDI MIDI("FP10 Lights");
Preferences prefs;
CRGB leds[NUM_LEDS];
float light[TIERS][NUM_LEDS][3];  // linear light per tier per LED, summed over the channels before going to leds[]
CRGB onboard[1];

int16_t keyFirst[128], keyLast[128];  // LED range per note, from the calibration
float calLowLed = CAL_LOW_LED, calHighLed = CAL_HIGH_LED;

// Calibration mode: which point is being set (-1 = off), and the LED it's on
int calStep = -1;
int calLed = 0;
uint32_t calSince = 0;

float level[4][128];     // brightness per channel per note
bool  held[4][128];      // key physically down (play) or hint on
bool  sustained[128];    // play notes released while pedal down: they fade slowly until it lifts
bool  pedal = false;
uint32_t lastMidiMs = 0;

uint8_t splitNote = 0;   // play notes below it get LEFT_COLOUR; 0 = off
bool sparksOn = false;

struct Spark {
  float pos, speed;  // LED (logical, before REVERSED), LEDs per frame (negative = left)
  float life, fade;  // 1 -> 0, and how much a frame takes off
  float bright;      // linear light at the start
  CRGB colour;       // what it cools to
};
Spark sparks[MAX_SPARKS];  // life <= 0 = free

enum OtaState { OTA_OFF, OTA_CONNECTING, OTA_READY, OTA_UPDATING, OTA_FAILED };
OtaState ota = OTA_OFF;
uint32_t otaSince = 0;

void clearAll() {
  memset(level, 0, sizeof(level));
  memset(held, 0, sizeof(held));
  memset(sustained, 0, sizeof(sustained));
  memset(sparks, 0, sizeof(sparks));
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

void loadCalibration() {
  prefs.begin("fp10", true);
  calLowLed = prefs.getFloat("cal_lo", CAL_LOW_LED);
  calHighLed = prefs.getFloat("cal_hi", CAL_HIGH_LED);
  prefs.end();
}

void saveCalibration() {
  prefs.begin("fp10", false);
  prefs.putFloat("cal_lo", calLowLed);
  prefs.putFloat("cal_hi", calHighLed);
  prefs.end();
}

void loadOptions() {
  prefs.begin("fp10", true);
  splitNote = prefs.getUChar("split", 0);
  sparksOn = prefs.getBool("sparks", false);
  prefs.end();
}

void saveOptions() {
  prefs.begin("fp10", false);
  prefs.putUChar("split", splitNote);
  prefs.putBool("sparks", sparksOn);
  prefs.end();
}

// ---- USB watchdog ----

// After about one restart in three the Push refuses the board ("can't set config #1, error -32"); the next restart
// usually comes up fine. So if the Push hasn't set the board up within USB_SETUP_MS, restart. (Disconnecting and
// reconnecting USB instead left the board off the Push for good, 2026-11-01.) Not while Wi-Fi update mode is on,
// which is the way back in if USB never works. Off a host (Push off, a charger) this repeats every few seconds.
// The flag survives the restart (not a power cut), so a watchdog restart can skip the boot sweep.
#define USB_RESTART_MAGIC 0xF10A5EED
RTC_NOINIT_ATTR uint32_t usbRestartFlag;
bool usbRestarted = false;  // this boot came from a watchdog restart

void usbWatchBoot() {
  usbRestarted = usbRestartFlag == USB_RESTART_MAGIC;
  usbRestartFlag = 0;
}

void usbWatch() {
  static uint32_t unsetSince = 0;
  if (tud_mounted() || (ota != OTA_OFF && ota != OTA_FAILED)) {
    unsetSince = 0;
    return;
  }
  if (!unsetSince) {
    unsetSince = millis() | 1;
    return;
  }
  if (millis() - unsetSince < USB_SETUP_MS) return;
  usbRestartFlag = USB_RESTART_MAGIC;
  ESP.restart();
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

// ---- Calibration ----

void buildKeyMap();

int calNote() { return calStep == 0 ? CAL_LOW_NOTE : CAL_HIGH_NOTE; }

void calStart() {
  clearAll();
  calStep = 0;
  calLed = lroundf(calLowLed);
  calSince = millis();
  Serial.println("Calibrate: move the light to the middle of C1 (keys below = left, above = right), then play C1");
}

void calStop() {
  calStep = -1;
  clearAll();
}

void calNoteOn(int note) {
  calSince = millis();
  if (note < calNote()) calLed = max(0, calLed - 1);
  else if (note > calNote()) calLed = min(NUM_LEDS - 1, calLed + 1);
  else if (calStep == 0) {
    calLowLed = calLed;
    calStep = 1;
    calLed = lroundf(calHighLed);
    Serial.printf("Calibrate: C1 = LED %d. Now C6, then play C6\n", int(calLowLed));
  } else {
    calHighLed = calLed;
    saveCalibration();
    buildKeyMap();
    Serial.printf("Calibrate: C6 = LED %d. Saved\n", int(calHighLed));
    calStop();
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
    Serial.printf("ssid: %s\npass: %s\notapass: %s\nC1 = LED %.1f, C6 = LED %.1f\nsplit: %d (0 = off)\nsparks: %s\n",
                  ssid.length() ? ssid.c_str() : "(not set)",
                  setting("pass").length() ? "set" : "not set",
                  setting("otapass").length() ? "set" : "not set",
                  calLowLed, calHighLed, splitNote, sparksOn ? "on" : "off");
  } else if (line == "forget") {
    prefs.begin("fp10", false);
    prefs.clear();
    prefs.end();
    loadCalibration();
    loadOptions();
    buildKeyMap();
    Serial.println("settings cleared (Wi-Fi, calibration, split and sparks)");
  } else if (line == "update") {
    otaStart();
  } else if (line == "calibrate") {
    calStart();
  } else if (line.length()) {
    Serial.println("commands: set ssid <name> | set pass <password> | set otapass <password> | show | forget | update | calibrate");
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

// Velocity (1-127) -> linear light, even steps to the eye
float velLevel(int vel) {
  return powf(MIN_SEEN + (1 - MIN_SEEN) * (vel - 1) / 126.0f, HD_GAMMA);
}

CRGB playColour(int note) { return splitNote && note < splitNote ? LEFT_COLOUR : CH_COLOUR[0]; }

float randomIn(float lo, float hi) { return lo + (hi - lo) * (esp_random() / 4294967296.0f); }

void throwSparks(int note, int vel) {
  int count = 2 + vel / 50;  // 2-4
  float from = (keyFirst[note] + keyLast[note]) / 2.0f;
  for (int k = 0; k < count; k++) {
    Spark *s = &sparks[0];  // a free one, or else the most faded
    for (int i = 0; i < MAX_SPARKS && s->life > 0; i++)
      if (sparks[i].life < s->life) s = &sparks[i];
    s->pos = from;
    s->speed = (k % 2 ? 1 : -1) * SPARK_SPEED * (0.3f + 0.7f * vel / 127) * randomIn(0.5f, 1.4f);
    s->life = 1;
    s->fade = 10 / (SPARK_MS * randomIn(0.6f, 1.4f));
    s->bright = velLevel(vel);
    s->colour = playColour(note);
  }
}

void noteOn(int ch, int note, int vel) {
  held[ch][note] = true;
  if (ch == 0) {
    sustained[note] = false;
    level[ch][note] = velLevel(vel);
    if (sparksOn) throwSparks(note, vel);
  } else if (ch == 1) {
    level[ch][note] = HINT_LEVEL * velLevel(vel);
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
  if (type == 0xB0 && ch == OTA_CHANNEL && d1 == RESTART_CC && d2 >= 64) ESP.restart();
  if (type == 0xB0 && ch == OTA_CHANNEL && (d1 == SPLIT_CC || d1 == SPARKS_CC)) {
    if (d1 == SPLIT_CC) splitNote = d2;
    else sparksOn = d2 >= 64;
    saveOptions();
    return;
  }
  if (type == 0xB0 && ch == OTA_CHANNEL && d1 == CAL_CC) {
    if (d2 >= 64) calStart();
    else if (calStep >= 0) calStop();
    return;
  }
  if (ch > 3) return;
  lastMidiMs = millis();
  if (calStep >= 0) {
    if (type == 0x90 && d2 > 0 && ch == 0) calNoteOn(d1);
    return;
  }

  if (type == 0x90 && d2 > 0) noteOn(ch, d1, d2);
  else if (type == 0x80 || type == 0x90) noteOff(ch, d1);
  else if (type == 0xB0 && d1 == 64 && ch == 0) sustainPedal(d2 >= 64);
}

// ---- Lights ----

bool isBlack(int note) { return (0x54A >> (note % 12)) & 1; }

// Key centre in white-key widths, along the back of the keys where the strip sits. There a piano splits C-E
// (3 white widths) into 5 equal slots and F-B (4 widths) into 7, black keys included, so white keys aren't
// centred on their fronts: B sits 0.2 of a white key right of its front's middle, C 0.2 left.
float keyPos(int note) {
  static const float POS[12] = {
    0.3, 0.9, 1.5, 2.1, 2.7,                                   // C C# D D# E: 3/5 each
    3 + 2 / 7.f, 3 + 6 / 7.f, 3 + 10 / 7.f, 3 + 14 / 7.f,      // F F# G G#: 4/7 each
    3 + 18 / 7.f, 3 + 22 / 7.f, 3 + 26 / 7.f,                  // A A# B
  };
  return (note / 12) * 7 + POS[note % 12];
}

void buildKeyMap() {
  float ledsPerWhite = (calHighLed - calLowLed) / (keyPos(CAL_HIGH_NOTE) - keyPos(CAL_LOW_NOTE));
  for (int n = 0; n < 128; n++) {
    float centre = calLowLed + (keyPos(n) - keyPos(CAL_LOW_NOTE)) * ledsPerWhite;
    float half = (isBlack(n) ? BLACK_SPAN : WHITE_SPAN) * ledsPerWhite / 2;
    keyFirst[n] = ceilf(centre - half);   // every LED whose centre falls inside the key
    keyLast[n] = floorf(centre + half);
    if (keyLast[n] < keyFirst[n]) keyFirst[n] = keyLast[n] = lroundf(centre);
  }
}

void updateLevels() {
  for (int n = 0; n < 128; n++) {
    if (!held[0][n] && level[0][n] > 0) {
      float seen = powf(level[0][n], 1 / HD_GAMMA) - 10 / (sustained[n] ? SUSTAIN_MS : RELEASE_MS);
      level[0][n] = seen > 0 ? powf(seen, HD_GAMMA) : 0;
    }
    if (!held[1][n]) level[1][n] = 0;
    level[2][n] = max(0.0f, level[2][n] - FLASH_FADE);
    level[3][n] = max(0.0f, level[3][n] - FLASH_FADE);
  }
  for (Spark &s : sparks) {
    if (s.life <= 0) continue;
    s.pos += s.speed;
    s.speed *= SPARK_DRAG;
    s.life -= s.fade;
    if (s.pos < -1 || s.pos > NUM_LEDS) s.life = 0;
  }
}

CRGB statusColour() {
  bool blink = (millis() / 250) % 2;
  if (calStep >= 0 && ota == OTA_OFF) return CRGB(0, 30, 30);
  switch (ota) {
    case OTA_CONNECTING: return blink ? CRGB(40, 20, 0) : CRGB::Black;
    case OTA_READY:      return CRGB(30, 0, 40);
    case OTA_UPDATING:   return CRGB(40, 40, 40);
    case OTA_FAILED:     return CRGB(50, 0, 0);
    default:             return (millis() - lastMidiMs < 60) ? CRGB(0, 0, 40) : CRGB(0, 4, 0);
  }
}

// Linear light (1 = full) -> the value SK9822HD turns back into that light
uint8_t toHd(float linear) {
  if (linear <= 0) return 0;
  return uint8_t(lroundf(255 * powf(min(linear, 1.0f), 1 / HD_GAMMA)));
}

// colour at a linear scale (0-1), sent as SK9822HD values
CRGB hdColour(CRGB c, float scale) {
  return CRGB(toHd(c.r / 255.0f * scale), toHd(c.g / 255.0f * scale), toHd(c.b / 255.0f * scale));
}

void render() {
  FastLED.clear();
  if (calStep >= 0) {
    leds[REVERSED ? NUM_LEDS - 1 - calLed : calLed] = hdColour(CRGB(90, 90, 90), BRIGHTNESS / 255.0f);
    onboard[0] = statusColour();
    FastLED.show();
    return;
  }
  memset(light, 0, sizeof(light));
  for (int n = 0; n < 128; n++) {
    for (int ch = 0; ch < 4; ch++) {
      if (level[ch][n] <= 0) continue;
      float scale = level[ch][n] * BRIGHTNESS / (255.0f * 255.0f);
      CRGB c = ch == 0 ? playColour(n) : CH_COLOUR[ch];
      int tier = ch > 0 ? TIER_GUIDE : held[0][n] ? TIER_HELD : TIER_FADING;
      for (int i = keyFirst[n]; i <= keyLast[n]; i++) {
        if (i < 0 || i >= NUM_LEDS) continue;
        float *l = light[tier][REVERSED ? NUM_LEDS - 1 - i : i];
        l[0] += c.r * scale;
        l[1] += c.g * scale;
        l[2] += c.b * scale;
      }
    }
  }
  // Sparks: between two LEDs, shared by how close each is, so they glide; in the tier that dims first
  for (const Spark &s : sparks) {
    if (s.life <= 0) continue;
    CRGB c = blend(CRGB::White, s.colour, uint8_t(255 * (1 - s.life)));  // white-hot, cooling to the note's colour
    float scale = s.bright * s.life * s.life * BRIGHTNESS / (255.0f * 255.0f);
    int first = floorf(s.pos);
    float share[2] = {1 - (s.pos - first), s.pos - first};
    for (int k = 0; k < 2; k++) {
      int i = first + k;
      if (i < 0 || i >= NUM_LEDS) continue;
      float *l = light[TIER_FADING][REVERSED ? NUM_LEDS - 1 - i : i];
      l[0] += c.r * scale * share[k];
      l[1] += c.g * scale * share[k];
      l[2] += c.b * scale * share[k];
    }
  }
  // Power cap, worked out here: FastLED's own would count the gamma-encoded values and dim chords far too soon.
  // Each tier gets what's left of the budget after the ones above it, so a big pedalled chord dims its own tail
  // before it touches the hint.
  float budget = MAX_MA - NUM_LEDS * 1.0f;
  float cap[TIERS];
  for (int t = 0; t < TIERS; t++) {
    float ma = 0;
    for (int i = 0; i < NUM_LEDS; i++) ma += (light[t][i][0] + light[t][i][1] + light[t][i][2]) * LED_MA;
    cap[t] = ma > budget ? budget / ma : 1;
    budget = max(0.0f, budget - ma * cap[t]);
  }
  for (int i = 0; i < NUM_LEDS; i++) {
    float sum[3] = {0, 0, 0};
    for (int t = 0; t < TIERS; t++)
      for (int k = 0; k < 3; k++) sum[k] += light[t][i][k] * cap[t];
    if (sum[0] > 0 || sum[1] > 0 || sum[2] > 0)
      leds[i] = CRGB(toHd(sum[0]), toHd(sum[1]), toHd(sum[2]));
  }
  onboard[0] = statusColour();
  FastLED.show();
}

void bootSweep() {
  for (int i = 0; i < NUM_LEDS; i += 2) {
    FastLED.clear();
    leds[i] = hdColour(CRGB(0, 40, 80), 1);
    FastLED.show();
    delay(4);
  }
  FastLED.clear(true);
}

void setup() {
  Serial.begin(115200);
  pinMode(BOOT_PIN, INPUT_PULLUP);
  WiFi.mode(WIFI_OFF);
  FastLED.addLeds<SK9822HD, DATA_PIN, CLOCK_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.addLeds<WS2812, ONBOARD_PIN, RGB>(onboard, 1);
  FastLED.setDither(0);  // SK9822HD has the steps; dithering only made them flicker
  clearAll();
  loadCalibration();
  loadOptions();
  buildKeyMap();
  otaSetup();
  MIDI.begin();
  USB.begin();
  usbWatchBoot();
  if (!usbRestarted) bootSweep();
}

void loop() {
  midiEventPacket_t p;
  while (MIDI.readPacket(&p)) handlePacket(p);
  readSerial();
  checkBootButton();
  otaService();
  usbWatch();
  if (calStep >= 0 && millis() - calSince > CAL_TIMEOUT_MS) calStop();

  static uint32_t lastFrame = 0;
  if (millis() - lastFrame >= 10) {
    lastFrame = millis();
    updateLevels();
    render();
  }
}
