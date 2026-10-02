"""Shared settings for the otaa-hello example.

It runs against gateway-hello's ChirpStack, next to gateway-hello's own fake
gateway and device if those are running. provision.py registers the device,
and gateway_mock.py pretends to be the gateway and the device.
"""

import os

CHIRPSTACK_API = os.environ.get("CHIRPSTACK_API", "localhost:8080")
CHIRPSTACK_USER = "admin"
CHIRPSTACK_PASSWORD = "admin"

BRIDGE_HOST = os.environ.get("BRIDGE_HOST", "localhost")
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "1700"))

# A gateway of its own. Two gateways with the same ID confuse the bridge: it
# sends downlinks to whichever one polled last.
GATEWAY_ID = "0016c001f153a14d"

# OTAA (over-the-air activation): the device ships with identifiers and one
# long-term root key. Its address and session keys come from the join.
DEV_EUI = "0202020202020202"
APP_EUI = "0000000000000000"  # JoinEUI in LoRaWAN 1.1; ChirpStack's own join server ignores it
APP_KEY = "00112233445566778899aabbccddeeff"

F_PORT = 1

# AS923 (the Japanese 920MHz band) at DR2: spreading factor 10, 125 kHz.
FREQUENCY_MHZ = 923.2
DATA_RATE = "SF10BW125"
