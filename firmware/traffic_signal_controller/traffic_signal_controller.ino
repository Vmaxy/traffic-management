#include <math.h>
#include <stdlib.h>
#include <string.h>

const unsigned long WATCHDOG_TIMEOUT_MS = 10000UL;
const unsigned long YELLOW_DURATION_MS = 3000UL;
const unsigned long ALL_RED_DURATION_MS = 1500UL;
const unsigned long SERIAL_BAUD_RATE = 9600UL;
const uint8_t COMMAND_BUFFER_SIZE = 32;
const uint16_t MIN_GREEN_SECONDS = 3;
const uint16_t MAX_GREEN_SECONDS = 30;

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
SignalPhase requestedGreen = PHASE_NS_GREEN;
SignalPhase latchedNextGreen = PHASE_NS_GREEN;
unsigned long phaseStartedMs = 0;
unsigned long lastValidCommandMs = 0;
unsigned long activeGreenMs = 5000UL;
unsigned long laneGreenMs[4] = {5000UL, 5000UL, 5000UL, 5000UL};
bool watchdogTriggered = false;
bool cycleStarted = false;
bool planReceived = false;
char commandBuffer[COMMAND_BUFFER_SIZE];
uint8_t commandLength = 0;
bool discardingCommand = false;

void setDirection(const SignalPins &pins, bool red, bool yellow, bool green) {
  digitalWrite(pins.red, red ? HIGH : LOW);
  digitalWrite(pins.yellow, yellow ? HIGH : LOW);
  digitalWrite(pins.green, green ? HIGH : LOW);
}

void applyPhase(SignalPhase phase) {
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
  phaseStartedMs = millis();
}

unsigned long boundedGreenMilliseconds(float value) {
  if (!isfinite(value) || value < MIN_GREEN_SECONDS || value > MAX_GREEN_SECONDS) {
    return 0;
  }
  return static_cast<unsigned long>(value * 1000.0f + 0.5f);
}

bool parseLane(const char *lane, uint8_t *index) {
  if (strcmp(lane, "N") == 0) {
    *index = 0;
  } else if (strcmp(lane, "S") == 0) {
    *index = 1;
  } else if (strcmp(lane, "E") == 0) {
    *index = 2;
  } else if (strcmp(lane, "W") == 0) {
    *index = 3;
  } else {
    return false;
  }
  return true;
}

SignalPhase parseTarget(const char *target) {
  if (strcmp(target, "NS") == 0) {
    return PHASE_NS_GREEN;
  }
  if (strcmp(target, "EW") == 0) {
    return PHASE_EW_GREEN;
  }
  return PHASE_ALL_RED;
}

unsigned long durationFor(SignalPhase phase) {
  if (phase == PHASE_NS_GREEN) {
    return laneGreenMs[0] > laneGreenMs[1] ? laneGreenMs[0] : laneGreenMs[1];
  }
  return laneGreenMs[2] > laneGreenMs[3] ? laneGreenMs[2] : laneGreenMs[3];
}

bool isGreenPhase() {
  return currentPhase == PHASE_NS_GREEN || currentPhase == PHASE_EW_GREEN;
}

void noteValidCommand() {
  unsigned long now = millis();
  lastValidCommandMs = now;
  if (watchdogTriggered) {
    watchdogTriggered = false;
    cycleStarted = false;
    planReceived = false;
    requestedGreen = PHASE_NS_GREEN;
    applyPhase(PHASE_ALL_RED);
  }
}

void processCommand(char *command) {
  char *first = strtok(command, ":");
  char *second = strtok(NULL, ":");
  char *third = strtok(NULL, ":");
  if (first == NULL || second == NULL) {
    Serial.println("ERR:BAD_COMMAND");
    return;
  }

  if (strcmp(first, "SET") == 0 && third != NULL && strtok(NULL, ":") == NULL) {
    uint8_t laneIndex;
    if (!parseLane(second, &laneIndex)) {
      Serial.println("ERR:BAD_LANE");
      return;
    }
    char *end = NULL;
    float seconds = static_cast<float>(strtod(third, &end));
    unsigned long bounded = boundedGreenMilliseconds(seconds);
    if (end == third || *end != '\0' || bounded == 0) {
      Serial.println("ERR:BAD_DURATION");
      return;
    }
    noteValidCommand();
    if (isGreenPhase() || !cycleStarted) {
      laneGreenMs[laneIndex] = bounded;
      planReceived = true;
    }
    Serial.print("ACK:SET:");
    Serial.println(second);
    return;
  }

  if (strcmp(first, "NEXT") == 0 && third == NULL) {
    SignalPhase target = parseTarget(second);
    if (target == PHASE_ALL_RED) {
      Serial.println("ERR:BAD_TARGET");
      return;
    }
    noteValidCommand();
    if (isGreenPhase() || !cycleStarted) {
      requestedGreen = target;
      planReceived = true;
    }
    Serial.print("ACK:NEXT:");
    Serial.println(second);
    return;
  }

  if (strcmp(first, "PRIORITY") == 0 && third == NULL) {
    SignalPhase target = parseTarget(second);
    if (target == PHASE_ALL_RED) {
      Serial.println("ERR:BAD_TARGET");
      return;
    }
    noteValidCommand();
    if (isGreenPhase() || !cycleStarted) {
      requestedGreen = target;
      if (isGreenPhase() && millis() - phaseStartedMs >= MIN_GREEN_SECONDS * 1000UL) {
        activeGreenMs = millis() - phaseStartedMs;
      }
    }
    Serial.print("ACK:PRIORITY:");
    Serial.println(second);
    return;
  }

  if (strcmp(first, "SAFE") == 0 && strcmp(second, "RED") == 0 && third == NULL) {
    noteValidCommand();
    cycleStarted = false;
    planReceived = false;
    applyPhase(PHASE_ALL_RED);
    Serial.println("ACK:SAFE:RED");
    return;
  }

  Serial.println("ERR:UNKNOWN_COMMAND");
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char incoming = static_cast<char>(Serial.read());
    if (incoming == '\n' || incoming == '\r') {
      if (discardingCommand) {
        Serial.println("ERR:COMMAND_TOO_LONG");
        discardingCommand = false;
      } else if (commandLength > 0) {
        commandBuffer[commandLength] = '\0';
        processCommand(commandBuffer);
        commandLength = 0;
      }
    } else if (discardingCommand) {
      continue;
    } else if (commandLength < COMMAND_BUFFER_SIZE - 1) {
      commandBuffer[commandLength++] = incoming;
    } else {
      commandLength = 0;
      discardingCommand = true;
    }
  }
}

void advanceSignalState() {
  unsigned long now = millis();
  unsigned long elapsed = now - phaseStartedMs;

  if (currentPhase == PHASE_ALL_RED && elapsed >= ALL_RED_DURATION_MS &&
      ((!cycleStarted && planReceived) || cycleStarted)) {
    SignalPhase next = requestedGreen;
    if (cycleStarted) {
      next = latchedNextGreen;
    }
    if (next != PHASE_NS_GREEN && next != PHASE_EW_GREEN) {
      next = PHASE_NS_GREEN;
    }
    activeGreenMs = durationFor(next);
    applyPhase(next);
    cycleStarted = true;
  } else if (currentPhase == PHASE_NS_GREEN && elapsed >= activeGreenMs) {
    latchedNextGreen = elapsed >= MAX_GREEN_SECONDS * 1000UL
                           ? PHASE_EW_GREEN
                           : requestedGreen;
    activeGreenMs = durationFor(latchedNextGreen);
    applyPhase(PHASE_NS_YELLOW);
  } else if (currentPhase == PHASE_EW_GREEN && elapsed >= activeGreenMs) {
    latchedNextGreen = elapsed >= MAX_GREEN_SECONDS * 1000UL
                           ? PHASE_NS_GREEN
                           : requestedGreen;
    activeGreenMs = durationFor(latchedNextGreen);
    applyPhase(PHASE_EW_YELLOW);
  } else if ((currentPhase == PHASE_NS_YELLOW || currentPhase == PHASE_EW_YELLOW) &&
             elapsed >= YELLOW_DURATION_MS) {
    applyPhase(PHASE_ALL_RED);
  }
}

void setup() {
  for (uint8_t pin = 2; pin <= 13; ++pin) {
    pinMode(pin, OUTPUT);
  }
  applyPhase(PHASE_ALL_RED);
  Serial.begin(SERIAL_BAUD_RATE);
  lastValidCommandMs = millis();
}

void loop() {
  readSerialCommands();
  unsigned long now = millis();
  if (!watchdogTriggered && now - lastValidCommandMs >= WATCHDOG_TIMEOUT_MS) {
    watchdogTriggered = true;
    cycleStarted = false;
    applyPhase(PHASE_ALL_RED);
  }
  if (!watchdogTriggered) {
    advanceSignalState();
  }
}
