"""The backend side of the LoRaWAN hello example.

This is the code you would keep when you swap the fake network for a real
ChirpStack: it only talks MQTT to the broker and never touches the gateway, the
radio or the device.

    uv run app.py
"""

import base64
import json
import uuid

import paho.mqtt.client as mqtt

from common import MQTT_HOST, MQTT_PORT, F_PORT, command_down_topic, event_topic

# Downlinks we queued and have not seen acknowledged yet, by queue item id.
pending: dict[str, str] = {}
greeted: set[str] = set()


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
        print(f"[app] connection failed: {reason_code}")
        return

    print(f"[app] connected to {MQTT_HOST}:{MQTT_PORT}")
    # Every event of every device in every application.
    client.subscribe(event_topic(), qos=1)


def on_up(client, event: dict) -> None:
    device = event["deviceInfo"]
    rx = event["rxInfo"][0]
    data = base64.b64decode(event.get("data", ""))
    print(
        f"[app] uplink from {device['devEui']} fCnt {event['fCnt']} "
        f"via {rx['gatewayId']} (RSSI {rx['rssi']}, SNR {rx['snr']}): {data!r}"
    )

    if device["devEui"] not in greeted:
        greeted.add(device["devEui"])
        say_hello(client, device["applicationId"], device["devEui"])


def on_join(client, event: dict) -> None:
    device = event["deviceInfo"]
    print(f"[app] {device['devEui']} joined with DevAddr {event['devAddr']}")


def on_txack(client, event: dict) -> None:
    print(
        f"[app] downlink {short(event['queueItemId'])} transmitted by "
        f"{event['gatewayId']} (fCntDown {event['fCntDown']})"
    )


def on_ack(client, event: dict) -> None:
    item_id = event["queueItemId"]
    result = "acknowledged" if event["acknowledged"] else "NOT acknowledged"
    print(f"[app] downlink {short(item_id)} {result} by the device: {pending.pop(item_id, '?')!r}")


def on_log(client, event: dict) -> None:
    print(f"[app] {event['level']} {event['code']}: {event['description']}")


HANDLERS = {"up": on_up, "join": on_join, "txack": on_txack, "ack": on_ack, "log": on_log}


def on_message(client, userdata, msg):
    # application/<application_id>/device/<dev_eui>/event/<event>
    event_type = msg.topic.rsplit("/", 1)[-1]
    handler = HANDLERS.get(event_type)
    if handler is None:
        print(f"[app] ignoring {event_type} event")
        return
    try:
        handler(client, json.loads(msg.payload))
    except (ValueError, KeyError) as err:
        print(f"[app] cannot handle {msg.topic}: {err!r}")


def say_hello(client: mqtt.Client, application_id: str, dev_eui: str) -> None:
    """Queue a confirmed downlink for a device."""
    item_id = str(uuid.uuid4())  # comes back as queueItemId in txack and ack
    data = "hello from the app"
    command = {
        "id": item_id,
        "devEui": dev_eui,
        "confirmed": True,
        "fPort": F_PORT,
        "data": base64.b64encode(data.encode()).decode(),
    }
    pending[item_id] = data
    client.publish(command_down_topic(application_id, dev_eui), json.dumps(command), qos=1)
    print(f"[app] downlink {short(item_id)} queued for {dev_eui}")


def short(item_id: str) -> str:
    return item_id[:8]


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[app] stopping")
        client.disconnect()


if __name__ == "__main__":
    main()
