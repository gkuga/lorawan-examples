"""Shared settings for the gateway-hello example.

The gateway and the device are fake; ChirpStack is real. provision.py
registers both with ChirpStack using these values, and gateway_mock.py
pretends to be them.
"""

import os

# ChirpStack's gRPC API (the web UI is on the same port). The default admin
# account is created on first start.
CHIRPSTACK_API = os.environ.get("CHIRPSTACK_API", "localhost:8080")
CHIRPSTACK_USER = "admin"
CHIRPSTACK_PASSWORD = "admin"

# Where the gateway sends Semtech UDP packets: the ChirpStack Gateway Bridge.
BRIDGE_HOST = os.environ.get("BRIDGE_HOST", "localhost")
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "1700"))

# The gateway is identified by a 64-bit EUI, usually derived from its MAC.
GATEWAY_ID = "0016c001f153a14c"

# ABP (activation by personalization): the device ships with its address and
# session keys already set, so it can send without joining first.
DEV_EUI = "0101010101010101"
DEV_ADDR = "00189440"
NWK_S_KEY = "2b7e151628aed2a6abf7158809cf4f3c"  # integrity (MIC) and FPort 0
APP_S_KEY = "000102030405060708090a0b0c0d0e0f"  # FRMPayload on FPort 1-223

F_PORT = 1

# Where the fake device keeps its frame counters between runs, as a real one
# would in non-volatile memory.
STATE_FILE = "device-state.json"

# AS923 (the Japanese 920MHz band) at DR2: spreading factor 10, 125 kHz.
FREQUENCY_MHZ = 923.2
DATA_RATE = "SF10BW125"
