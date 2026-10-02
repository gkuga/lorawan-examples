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
           ▲ UDP packet forwarder               ← gateway-hello: fakes everything below this
  [ gateway ]
           ▲ LoRa, 920MHz (AS923)
  [ end device ]
```

## Examples

| Name | Fakes | Description |
|---|---|---|
| [hello](hello/) | everything below MQTT | A backend app and a fake network exchanging ChirpStack integration events |
| [gateway-hello](gateway-hello/) | everything below the gateway bridge | A fake gateway and ABP device in front of a **real** ChirpStack, with real LoRaWAN frames |
| [otaa-hello](otaa-hello/) | everything below the gateway bridge | The same, with a device that joins over the air (OTAA) and gets fresh session keys |

## How to run

This repo uses [uv](https://docs.astral.sh/uv/). Enter an example directory and
follow its README.

```bash
cd hello
uv sync
```

hello and gateway-hello both bind port 1883, as do the hello examples in
[wirepas-examples](https://github.com/gkuga/wirepas-examples); run one at a
time. gateway-hello and otaa-hello share gateway-hello's ChirpStack, can run
side by side, and both use hello's `app.py` as the application.

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

For a longer walkthrough of the components, LoRa vs LoRaWAN, and ChirpStack's
concepts, see [docs/lorawan-basics.md](docs/lorawan-basics.md).
For real radios to buy and Japan's radio certification (技適), see
[docs/lorawan-hardware.md](docs/lorawan-hardware.md).

What is not covered yet is listed in [TODO.md](TODO.md).
