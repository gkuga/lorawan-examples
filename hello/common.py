"""Shared settings and topic helpers for the LoRaWAN hello example.

Topic names and payloads follow ChirpStack v4's MQTT integration, which is
what a backend application sees of a LoRaWAN network:

    application/<application_id>/device/<dev_eui>/event/<event>
    application/<application_id>/device/<dev_eui>/command/down

Events used here: up, txack, ack and log. Payloads are JSON, with binary
fields in base64.
"""

import os

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))

# Identifiers the fake network pretends to have. ChirpStack names tenants,
# applications and device profiles by UUID; devices by their 8-byte DevEUI.
TENANT_ID = "52f14cd4-c6f1-4fbd-8f87-4025e1d49242"
APPLICATION_ID = "17c82e96-be03-4f38-aef3-f83d48582d97"
DEVICE_PROFILE_ID = "14855bf7-d10d-4aee-b618-ebfcb64dc7ad"
DEV_EUI = "0101010101010101"
DEV_ADDR = "00189440"  # the short address the network assigned at join
GATEWAY_ID = "0016c001f153a14c"

# FPort is the LoRaWAN equivalent of a port number. 0 is reserved for MAC
# commands, so applications use 1-223.
F_PORT = 1


def event_topic(application_id: str = "+", dev_eui: str = "+", event: str = "+") -> str:
    return f"application/{application_id}/device/{dev_eui}/event/{event}"


def command_down_topic(application_id: str = "+", dev_eui: str = "+") -> str:
    return f"application/{application_id}/device/{dev_eui}/command/down"
