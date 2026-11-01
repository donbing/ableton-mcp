// SK9822 strip test for Waveshare ESP32-S3-Zero
//
// Stage 1: first 10 LEDs show red, green, blue (2s each) -> checks data/clock and colour order
// Stage 2: one dot runs along the whole strip              -> checks every LED and direction
//
// Strip dark?          swap DATA_PIN and CLOCK_PIN
// Colours in wrong order? change COLOR_ORDER (try BGR, RGB, GRB)

#include <FastLED.h>

#define DATA_PIN     2
#define CLOCK_PIN    1
#define COLOR_ORDER  BGR
#define NUM_LEDS     144

#define ONBOARD_PIN  21      // S3-Zero onboard WS2812, used as a heartbeat
#define BRIGHTNESS   40      // 0-255, kept low for testing
#define MAX_MA       400     // 500mA hub port, leave some margin

CRGB leds[NUM_LEDS];
CRGB onboard[1];

void fillFirst(CRGB colour, int count) {
  FastLED.clear();
  for (int i = 0; i < count; i++) leds[i] = colour;
}

void setup() {
  Serial.begin(115200);
  FastLED.addLeds<SK9822, DATA_PIN, CLOCK_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.addLeds<WS2812, ONBOARD_PIN, RGB>(onboard, 1);
  FastLED.setBrightness(BRIGHTNESS);
  FastLED.setMaxPowerInVoltsAndMilliamps(5, MAX_MA);
  FastLED.clear(true);
  delay(1000);
  Serial.println("SK9822 test starting");
}

void loop() {
  struct { CRGB colour; const char *name; } steps[] = {
    { CRGB::Red,   "RED"   },
    { CRGB::Green, "GREEN" },
    { CRGB::Blue,  "BLUE"  },
  };

  for (auto &s : steps) {
    Serial.printf("Stage 1: first 10 LEDs should be %s\n", s.name);
    fillFirst(s.colour, 10);
    onboard[0] = s.colour;
    FastLED.show();
    delay(2000);
  }

  Serial.println("Stage 2: dot running from input end to far end");
  for (int i = 0; i < NUM_LEDS; i++) {
    FastLED.clear();
    leds[i] = CRGB::White;
    onboard[0] = (i / 12) % 2 ? CRGB::Black : CRGB(0, 20, 0);
    FastLED.show();
    if (i % 12 == 0) Serial.printf("  LED %d\n", i);
    delay(30);
  }

  FastLED.clear(true);
  delay(500);
}
