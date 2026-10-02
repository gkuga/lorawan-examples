# lorawan-examples

Small, self-contained experiments for getting familiar with
[LoRaWAN](https://lora-alliance.org/about-lorawan/) and its network server
stack. Each directory is a uv project.

LoRaWAN is an open specification, and the server side is open source too
([ChirpStack](https://www.chirpstack.io/)), so every layer can be faked or run
for real.

```
  [ backend application ]
           ▲ MQTT (JSON)                        ← hello: fakes everything below this
  [ ChirpStack ] (network server)
           ▲ UDP packet forwarder / WebSocket   ← planned: fake a gateway
  [ gateway ]
           ▲ LoRa, 920MHz (AS923)
  [ end device ]
```

## Examples

| Name | Fakes | Description |
|---|---|---|
| [hello](hello/) | everything below MQTT | A backend app and a fake network exchanging ChirpStack integration events |

## How to run

This repo uses [uv](https://docs.astral.sh/uv/). Enter an example directory and
follow its README.

```bash
cd hello
uv sync
```

The broker binds port 1883, like the hello examples in
[wirepas-examples](https://github.com/gkuga/wirepas-examples); run one at a time.

## Notes on LoRaWAN

- **LoRa is not LoRaWAN.** LoRa is Semtech's chirp spread spectrum modulation,
  the physical layer. LoRaWAN is the MAC layer and network architecture on
  top, specified by the LoRa Alliance.
- **Star of stars, no mesh.** Devices talk to every gateway in range at once.
  Gateways forward what they hear to the network server, which drops the
  duplicates; they know nothing about devices or keys.
- **Class A is the default.** A device listens only right after it transmits,
  so downlinks wait for the next uplink. Class B adds scheduled windows;
  Class C listens all the time.
