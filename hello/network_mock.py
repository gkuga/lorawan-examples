"""A fake LoRaWAN network.

It stands in for everything below the application -- the end device, the
gateway and the network server (ChirpStack) -- and speaks the same MQTT
integration ChirpStack does. That is enough to develop and test a backend
application without any hardware.

    uv run network_mock.py
"""

import base64
import itertools
import json
import random
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from common import (
    APPLICATION_ID,
    DEV_ADDR,
    DEV_EUI,
    DEVICE_PROFILE_ID,
    F_PORT,
    GATEWAY_ID,
    MQTT_HOST,
    MQTT_PORT,
    TENANT_ID,
    command_down_topic,
    event_topic,
)

UPLINK_INTERVAL_S = 5
RX1_DELAY_S = 1  # Class A: the device listens 1 s after its uplink, then 2 s

# AS923 (the Japanese 920MHz band) at DR2, i.e. spreading factor 10. A
# downlink at this data rate carries at most 51 bytes of application payload.
FREQUENCY_HZ = 923_200_000
DATA_RATE = 2
SPREADING_FACTOR = 10
MAX_PAYLOAD = 51

DEVICE_INFO = {
    "tenantId": TENANT_ID,
    "tenantName": "ChirpStack",
    "applicationId": APPLICATION_ID,
    "applicationName": "hello",
    "deviceProfileId": DEVICE_PROFILE_ID,
    "deviceProfileName": "Class A, AS923",
    "deviceName": "hello-device",
    "devEui": DEV_EUI,
    "deviceClassEnabled": "CLASS_A",
    "tags": {},
}


class Network:
    """The device's state as the network server tracks it."""

    def __init__(self, client: mqtt.Client) -> None:
        self.client = client
        self.lock = threading.Lock()
        self.queue: deque[dict] = deque()  # downlinks waiting for an uplink
        self.awaiting_ack: dict | None = None  # confirmed downlink sent, not yet acked
        self.f_cnt_up = itertools.count(0)
        self.f_cnt_down = itertools.count(0)

    def publish(self, event: str, body: dict) -> None:
        body = {"time": now(), "deviceInfo": DEVICE_INFO, **body}
        self.client.publish(
            event_topic(APPLICATION_ID, DEV_EUI, event), json.dumps(body), qos=1
        )

    def enqueue(self, command: dict) -> None:
        """Handle a downlink command from the application.

        Nothing is sent now. A Class A device only listens right after its
        own uplink, so the item waits in the device queue until then.
        """
        data = base64.b64decode(command.get("data", ""))
        item = {
            "id": command.get("id") or str(uuid.uuid4()),
            "confirmed": bool(command.get("confirmed")),
            "fPort": command["fPort"],
            "data": data,
        }
        if len(data) > MAX_PAYLOAD:
            print(f"[network] downlink {item['id']} too long ({len(data)} bytes), dropped")
            self.publish(
                "log",
                {
                    "level": "ERROR",
                    "code": "DOWNLINK_PAYLOAD_SIZE",
                    "description": f"payload is {len(data)} bytes, max is {MAX_PAYLOAD}",
                    "context": {"queue_item_id": item["id"]},
                },
            )
            return
        with self.lock:
            self.queue.append(item)
        print(f"[network] downlink queued: {data!r} (confirmed={item['confirmed']})")

    def uplink(self, payload: bytes) -> None:
        """Pretend the device transmitted and a gateway heard it."""
        f_cnt = next(self.f_cnt_up)

        # A confirmed downlink is acknowledged by an ACK bit in the device's
        # *next* uplink, so that is when the application learns about it.
        with self.lock:
            acked, self.awaiting_ack = self.awaiting_ack, None
        if acked is not None:
            self.publish(
                "ack",
                {
                    "deduplicationId": str(uuid.uuid4()),
                    "queueItemId": acked["id"],
                    "acknowledged": True,
                    "fCntDown": acked["fCntDown"],
                },
            )

        self.publish(
            "up",
            {
                "deduplicationId": str(uuid.uuid4()),
                "devAddr": DEV_ADDR,
                "adr": True,
                "dr": DATA_RATE,
                "fCnt": f_cnt,
                "fPort": F_PORT,
                "confirmed": False,
                "data": base64.b64encode(payload).decode(),
                "rxInfo": [
                    {
                        "gatewayId": GATEWAY_ID,
                        "uplinkId": random.getrandbits(32),
                        "rssi": random.randint(-110, -90),
                        "snr": round(random.uniform(-5, 8), 1),
                        "context": base64.b64encode(random.randbytes(4)).decode(),
                        "metadata": {"region_name": "as923", "region_common_name": "AS923"},
                    }
                ],
                "txInfo": {
                    "frequency": FREQUENCY_HZ,
                    "modulation": {"lora": lora_modulation()},
                },
            },
        )
        print(f"[network] uplink fCnt {f_cnt}: {payload!r}")

        time.sleep(RX1_DELAY_S)
        self.send_downlink()

    def send_downlink(self) -> None:
        """Use the device's receive window for at most one queued downlink."""
        with self.lock:
            item = self.queue.popleft() if self.queue else None
            if item is None:
                return
            item["fCntDown"] = next(self.f_cnt_down)
            if item["confirmed"]:
                self.awaiting_ack = item

        # txack only says the gateway transmitted it, not that the device
        # received it. For that, send it confirmed and wait for "ack".
        self.publish(
            "txack",
            {
                "downlinkId": random.getrandbits(32),
                "queueItemId": item["id"],
                "fCntDown": item["fCntDown"],
                "gatewayId": GATEWAY_ID,
                "txInfo": {
                    "frequency": FREQUENCY_HZ,
                    "power": 13,
                    "modulation": {
                        "lora": {**lora_modulation(), "polarizationInversion": True}
                    },
                    "timing": {"delay": {"delay": f"{RX1_DELAY_S}s"}},
                    "context": base64.b64encode(random.randbytes(4)).decode(),
                },
            },
        )
        print(f"[network] downlink sent in RX1, device got: {item['data']!r}")


def lora_modulation() -> dict:
    return {"bandwidth": 125000, "spreadingFactor": SPREADING_FACTOR, "codeRate": "CR_4_5"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
        print(f"[network] connection failed: {reason_code}")
        return

    print(f"[network] connected to {MQTT_HOST}:{MQTT_PORT}")
    client.subscribe(command_down_topic(APPLICATION_ID, DEV_EUI), qos=1)
    userdata["connected"].set()


def on_message(client, userdata, msg):
    try:
        command = json.loads(msg.payload)
    except ValueError as err:
        print(f"[network] cannot parse command on {msg.topic}: {err}")
        return

    # The same checks ChirpStack makes before queueing.
    if command.get("devEui") != DEV_EUI:
        print(f"[network] devEui {command.get('devEui')!r} does not match the topic")
        return
    if not 1 <= command.get("fPort", 0) <= 223:
        print(f"[network] fPort {command.get('fPort')!r} is not an application port")
        return

    userdata["network"].enqueue(command)


def main() -> None:
    connected = threading.Event()
    userdata = {"connected": connected}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata=userdata)
    client.on_connect = on_connect
    client.on_message = on_message
    network = Network(client)
    userdata["network"] = network

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    connected.wait()

    try:
        for counter in itertools.count(1):
            started = time.monotonic()
            network.uplink(f"hello #{counter}".encode())
            time.sleep(max(0, UPLINK_INTERVAL_S - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("\n[network] stopping")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
