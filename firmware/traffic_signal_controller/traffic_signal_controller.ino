#include <string.h>

const unsigned long WATCHDOG_TIMEOUT_MS = 3000UL;
const unsigned long SERIAL_BAUD_RATE = 9600UL;
const uint8_t COMMAND_BUFFER_SIZE = 16;

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
char commandBuffer[COMMAND_BUFFER_SIZE];
uint8_t commandLength = 0;
bool discardingCommand = false;

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

bool parsePhase(const char *command, SignalPhase *phase) {
  if (strcmp(command, "ALL_R") == 0) {
    *phase = PHASE_ALL_RED;
  } else if (strcmp(command, "NS_G") == 0) {
    *phase = PHASE_NS_GREEN;
  } else if (strcmp(command, "NS_Y") == 0) {
    *phase = PHASE_NS_YELLOW;
  } else if (strcmp(command, "EW_G") == 0) {
    *phase = PHASE_EW_GREEN;
  } else if (strcmp(command, "EW_Y") == 0) {
    *phase = PHASE_EW_YELLOW;
  } else {
    return false;
  }
  return true;
}

void processCommand(const char *command) {
  while (*command == ' ' || *command == '\t') {
    ++command;
  }
  size_t commandSize = strlen(command);
  while (commandSize > 0 && (command[commandSize - 1] == ' ' || command[commandSize - 1] == '\t')) {
    --commandSize;
  }
  char trimmedCommand[COMMAND_BUFFER_SIZE];
  memcpy(trimmedCommand, command, commandSize);
  trimmedCommand[commandSize] = '\0';
  command = trimmedCommand;

  SignalPhase requestedPhase;
  if (!parsePhase(command, &requestedPhase)) {
    if (strlen(command) == 3 && command[1] == ':') {
      const SignalPins *pins = NULL;
      if (command[0] == 'N') {
        pins = &NORTH;
      } else if (command[0] == 'S') {
        pins = &SOUTH;
      } else if (command[0] == 'E') {
        pins = &EAST;
      } else if (command[0] == 'W') {
        pins = &WEST;
      }

      if (pins != NULL && (command[2] == 'R' || command[2] == 'Y' || command[2] == 'G')) {
        setDirection(*pins, command[2] == 'R', command[2] == 'Y', command[2] == 'G');
        lastCommandMs = millis();
        watchdogTriggered = false;
        Serial.print("ACK:");
        Serial.println(command);
        return;
      }
    }
    Serial.println("ERR:UNKNOWN_COMMAND");
    return;
  }

  applyPhase(requestedPhase);
  lastCommandMs = millis();
  watchdogTriggered = false;
  Serial.print("ACK:");
  Serial.println(phaseCommand(currentPhase));
}

void processSingleByte(char command) {
  SignalPhase requestedPhase;
  switch (command) {
    case '0':
      requestedPhase = PHASE_ALL_RED;
      break;
    case '1':
      requestedPhase = PHASE_NS_GREEN;
      break;
    case '2':
      requestedPhase = PHASE_NS_YELLOW;
      break;
    case '3':
      requestedPhase = PHASE_EW_GREEN;
      break;
    case '4':
      requestedPhase = PHASE_EW_YELLOW;
      break;
    default:
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
    char incoming = static_cast<char>(Serial.read());
    if (incoming == '\n' || incoming == '\r' || incoming == ';') {
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
    } else if (commandLength == 0 && incoming >= '0' && incoming <= '4') {
      processSingleByte(incoming);
    } else if (commandLength < COMMAND_BUFFER_SIZE - 1) {
      commandBuffer[commandLength++] = incoming;
    } else {
      commandLength = 0;
      discardingCommand = true;
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
