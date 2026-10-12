#include <string.h>

const unsigned long WATCHDOG_TIMEOUT_MS = 5000UL;
const unsigned long SERIAL_BAUD_RATE = 9600UL;
const size_t COMMAND_BUFFER_SIZE = 32;

struct SignalPins {
  uint8_t red;
  uint8_t yellow;
  uint8_t green;
};

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
char commandBuffer[COMMAND_BUFFER_SIZE];
size_t commandLength = 0;

void setDirection(const SignalPins &pins, bool red, bool yellow, bool green) {
  digitalWrite(pins.red, red ? HIGH : LOW);
  digitalWrite(pins.yellow, yellow ? HIGH : LOW);
  digitalWrite(pins.green, green ? HIGH : LOW);
}

void applyPhase(SignalPhase phase) {
  setDirection(NORTH, false, false, false);
  setDirection(SOUTH, false, false, false);
  setDirection(EAST, false, false, false);
  setDirection(WEST, false, false, false);

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

const char *phaseName(SignalPhase phase) {
  switch (phase) {
    case PHASE_NS_GREEN:
      return "NS_GREEN";
    case PHASE_NS_YELLOW:
      return "NS_YELLOW";
    case PHASE_EW_GREEN:
      return "EW_GREEN";
    case PHASE_EW_YELLOW:
      return "EW_YELLOW";
    case PHASE_ALL_RED:
    default:
      return "ALL_RED";
  }
}

bool parsePhase(const char *command, SignalPhase *phase) {
  if (strcmp(command, "SET_PHASE:ALL_RED") == 0) {
    *phase = PHASE_ALL_RED;
  } else if (strcmp(command, "SET_PHASE:NS_GREEN") == 0) {
    *phase = PHASE_NS_GREEN;
  } else if (strcmp(command, "SET_PHASE:NS_YELLOW") == 0) {
    *phase = PHASE_NS_YELLOW;
  } else if (strcmp(command, "SET_PHASE:EW_GREEN") == 0) {
    *phase = PHASE_EW_GREEN;
  } else if (strcmp(command, "SET_PHASE:EW_YELLOW") == 0) {
    *phase = PHASE_EW_YELLOW;
  } else {
    return false;
  }
  return true;
}

void processCommand(const char *command) {
  SignalPhase requestedPhase;
  if (!parsePhase(command, &requestedPhase)) {
    Serial.print("ERR:UNKNOWN_COMMAND\n");
    return;
  }

  applyPhase(requestedPhase);
  lastCommandMs = millis();
  watchdogTriggered = false;
  Serial.print("ACK:");
  Serial.print(phaseName(currentPhase));
  Serial.print('\n');
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());
    if (incoming == '\r') {
      continue;
    }
    if (incoming == '\n') {
      commandBuffer[commandLength] = '\0';
      if (commandLength > 0) {
        processCommand(commandBuffer);
      }
      commandLength = 0;
      continue;
    }
    if (commandLength < COMMAND_BUFFER_SIZE - 1) {
      commandBuffer[commandLength++] = incoming;
    } else {
      commandLength = 0;
      Serial.print("ERR:COMMAND_TOO_LONG\n");
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
  lastCommandMs = millis();
}

void loop() {
  readSerialCommands();
  if (!watchdogTriggered && millis() - lastCommandMs >= WATCHDOG_TIMEOUT_MS) {
    applyPhase(PHASE_ALL_RED);
    watchdogTriggered = true;
  }
}
