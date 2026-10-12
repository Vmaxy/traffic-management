#include <string.h>

const unsigned long WATCHDOG_TIMEOUT_MS = 3000UL;
const unsigned long SERIAL_BAUD_RATE = 9600UL;
const unsigned long SERIAL_READ_TIMEOUT_MS = 5UL;

struct SignalPins {
  uint8_t red;
  uint8_t yellow;
  uint8_t green;
};

// Each road approach has its own three LEDs; opposing approaches share a phase.
const SignalPins NORTH = {2, 3, 4};
const SignalPins SOUTH = {5, 6, 7};
const SignalPins EAST = {8, 9, 10};
const SignalPins WEST = {11, 12, 13};

enum SignalPhase {
  PHASE_ALL_RED,
  PHASE_NS_GREEN,
  PHASE_NS_YELLOW,
  PHASE_EW_GREEN,
  PHASE_EW_YELLOW
};

SignalPhase currentPhase = PHASE_ALL_RED;
unsigned long lastCommandMs = 0;
bool watchdogTriggered = false;

void setDirection(const SignalPins &pins, bool red, bool yellow, bool green) {
  digitalWrite(pins.red, red ? HIGH : LOW);
  digitalWrite(pins.yellow, yellow ? HIGH : LOW);
  digitalWrite(pins.green, green ? HIGH : LOW);
}

void applyPhase(SignalPhase phase) {
  // Start from all-red so no transition can momentarily show conflicting greens.
  setDirection(NORTH, true, false, false);
  setDirection(SOUTH, true, false, false);
  setDirection(EAST, true, false, false);
  setDirection(WEST, true, false, false);

  if (phase == PHASE_NS_GREEN) {
    setDirection(NORTH, false, false, true);
    setDirection(SOUTH, false, false, true);
  } else if (phase == PHASE_NS_YELLOW) {
    setDirection(NORTH, false, true, false);
    setDirection(SOUTH, false, true, false);
  } else if (phase == PHASE_EW_GREEN) {
    setDirection(EAST, false, false, true);
    setDirection(WEST, false, false, true);
  } else if (phase == PHASE_EW_YELLOW) {
    setDirection(EAST, false, true, false);
    setDirection(WEST, false, true, false);
  }
  currentPhase = phase;
}

const char *phaseCommand(SignalPhase phase) {
  switch (phase) {
    case PHASE_NS_GREEN:
      return "NS_G";
    case PHASE_NS_YELLOW:
      return "NS_Y";
    case PHASE_EW_GREEN:
      return "EW_G";
    case PHASE_EW_YELLOW:
      return "EW_Y";
    case PHASE_ALL_RED:
    default:
      return "ALL_R";
  }
}

bool parsePhase(const String &command, SignalPhase *phase) {
  if (command == "ALL_R") {
    *phase = PHASE_ALL_RED;
  } else if (command == "NS_G") {
    *phase = PHASE_NS_GREEN;
  } else if (command == "NS_Y") {
    *phase = PHASE_NS_YELLOW;
  } else if (command == "EW_G") {
    *phase = PHASE_EW_GREEN;
  } else if (command == "EW_Y") {
    *phase = PHASE_EW_YELLOW;
  } else {
    return false;
  }
  return true;
}

void processCommand(String command) {
  command.trim();  // Removes whitespace and CR from serial terminal line endings.
  SignalPhase requestedPhase;
  if (!parsePhase(command, &requestedPhase)) {
    Serial.println("ERR:UNKNOWN_COMMAND");
    return;
  }

  applyPhase(requestedPhase);
  lastCommandMs = millis();
  watchdogTriggered = false;
  Serial.print("ACK:");
  Serial.println(phaseCommand(currentPhase));
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    // A short timeout bounds this read while still allowing complete newline frames.
    String command = Serial.readStringUntil('\n');
    if (command.length() > 0) {
      processCommand(command);
    }
  }
}

void setup() {
  for (uint8_t pin = 2; pin <= 13; ++pin) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  applyPhase(PHASE_ALL_RED);
  Serial.begin(SERIAL_BAUD_RATE);
  Serial.setTimeout(SERIAL_READ_TIMEOUT_MS);
  lastCommandMs = millis();
}

void loop() {
  readSerialCommands();
  if (!watchdogTriggered && millis() - lastCommandMs >= WATCHDOG_TIMEOUT_MS) {
    applyPhase(PHASE_ALL_RED);
    watchdogTriggered = true;
  }
}
