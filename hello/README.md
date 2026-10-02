# hello

A LoRaWAN "Hello World" that runs **without any hardware**.

A backend application never sees LoRaWAN frames. It sees the network server's
integration, and with [ChirpStack](https://www.chirpstack.io/) v4 that is JSON
over MQTT. So an application can be written and tested against a fake network
that publishes the very same events ChirpStack would.

```
┌─────────────────────────────────────────────────────────────┐
│ Real deployment                     │ This example          │
│                                     │                       │
│  [ backend application ]            │  app.py               │
│           ▲                         │      ▲                │
│           │ MQTT (JSON)             │      │ MQTT (JSON)    │
│           ▼                         │      ▼                │
│  [ MQTT broker ]                    │  Mosquitto (Docker)   │
│           ▲                         │      ▲                │
│           │                         │      │                │
│  [ ChirpStack ] (network server)    │      │                │
│           ▲                         │      │                │
│           │ UDP / WebSocket         │      │ network_mock.py│
│  [ gateway ]                        │      │ fakes all of   │
│           ▲                         │      │ this           │
│           │ LoRa, 920MHz (AS923)    │      │                │
│  [ end device ]                     │      ▼                │
└─────────────────────────────────────────────────────────────┘
```

`app.py` is the part you keep when real hardware arrives: it only talks MQTT
and never touches the gateway, the radio or the device.

## Run it

Three terminals, in this order.

```bash
# 1. MQTT broker
docker compose up -d

# 2. the backend application (start it first so it sees every uplink)
uv sync
uv run app.py

# 3. the fake network
uv run network_mock.py
```

`app.py` prints something like:

```
[app] connected to localhost:1883
[app] uplink from 0101010101010101 fCnt 0 via 0016c001f153a14c (RSSI -110, SNR 1.9): b'hello #1'
[app] downlink 33128708 queued for 0101010101010101
[app] downlink 33128708 transmitted by 0016c001f153a14c (fCntDown 0)
[app] downlink 33128708 acknowledged by the device: 'hello from the app'
[app] uplink from 0101010101010101 fCnt 1 via 0016c001f153a14c (RSSI -108, SNR 0.9): b'hello #2'
```

Stop the broker with `docker compose down`.

## What happens

All topics start with `application/<application_id>/device/<dev_eui>/`.

| Direction | Topic | Message |
|---|---|---|
| network → app | `event/up` | An uplink: `fCnt`, `fPort`, `data` (base64), plus what each gateway heard (`rxInfo`) and how it was sent (`txInfo`). Every 5 s here. |
| app → network | `command/down` | A downlink to queue: `devEui`, `fPort`, `data`, `confirmed`, and an optional `id`. `app.py` sends one the first time it hears a device. |
| network → app | `event/txack` | The gateway transmitted the downlink. |
| network → app | `event/ack` | The device acknowledged a **confirmed** downlink. |
| network → app | `event/log` | Something went wrong, e.g. a downlink too long for the data rate. |

Details worth noticing:

- **A downlink waits for an uplink.** The device is Class A: it listens only
  in two short windows, 1 s and 2 s after each of its own uplinks. So a
  downlink is only queued until the next uplink, and goes out in that
  uplink's RX1 window. Only one goes out per uplink.
- **`txack` is not delivery.** It means a gateway put the frame on the air.
  Whether the device received it is only known for a *confirmed* downlink,
  and only when the device's **next** uplink carries the ACK bit. That is
  when `ack` arrives, about one uplink interval later.
- **You choose the `id`.** The command's `id` comes back as `queueItemId` in
  `txack` and `ack`, which is how `app.py` matches them. Without one,
  ChirpStack makes one up and the app cannot tell its downlinks apart.
- **Payloads are small and depend on the data rate.** Here it is AS923 DR2
  (spreading factor 10), which allows 51 bytes. Try a longer downlink and
  you get a `DOWNLINK_PAYLOAD_SIZE` log event instead.
- **`fPort`** plays the role of a port number. `0` is reserved for MAC
  commands, so applications use 1–223.
- **Counters.** `fCnt` counts uplinks and `fCntDown` counts downlinks. The
  real network uses them to reject replayed frames.
- **Topic wildcards** are how the backend discovers things: `app.py`
  subscribes with `+` for the application, device and event, so it works
  with any number of them without configuration.

## Files

| File | Role |
|---|---|
| [app.py](app.py) | The backend application — hardware-independent. |
| [network_mock.py](network_mock.py) | Fake network: fakes the device, the gateway and ChirpStack. |
| [common.py](common.py) | Broker settings, identifiers and topic helpers shared by both. |
| [compose.yaml](compose.yaml) | Mosquitto broker on `localhost:1883`, anonymous access. |

`MQTT_HOST` and `MQTT_PORT` override the broker location, e.g. to point
`app.py` at the broker of a real ChirpStack:

```bash
MQTT_HOST=192.168.1.10 uv run app.py
```

## What the mock does not do

- No frames, no encryption, no MIC: those live below this interface. See
  [gateway-hello](../gateway-hello/), which runs this same `app.py` against a
  real ChirpStack.
- One device, one gateway, no join (`join` event), no device status
  (`status` event) and no payload codec (`object`).
- The device always receives the downlink, so `ack` is always positive.

## Dependencies

- [`paho-mqtt`](https://pypi.org/project/paho-mqtt/) — the MQTT client.

ChirpStack's events are also available as protobuf; this example uses the
JSON form so the messages stay readable.

## References

- [ChirpStack MQTT integration](https://www.chirpstack.io/docs/chirpstack/integrations/mqtt.html)
- [ChirpStack event types](https://www.chirpstack.io/docs/chirpstack/integrations/events.html)
- [`integration.proto`](https://github.com/chirpstack/chirpstack/blob/master/api/proto/integration/integration.proto) —
  the field definitions behind the JSON.
