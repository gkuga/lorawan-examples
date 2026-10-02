# gateway-hello

A fake LoRaWAN gateway and device in front of a **real ChirpStack**.

[hello](../hello/) faked everything below the application. This example
fakes only the radio side: a gateway that speaks the Semtech UDP packet
forwarder protocol, and an ABP device behind it that builds real LoRaWAN
1.0.3 frames — encrypted payload, MIC, frame counters. Everything above that
is the real thing, including the unchanged `hello/app.py`.

```
┌─────────────────────────────────────────────────────────────┐
│ Real deployment                     │ This example          │
│                                     │                       │
│  [ backend application ]            │  ../hello/app.py      │
│           ▲ MQTT (JSON)             │      ▲                │
│  [ MQTT broker ]                    │  Mosquitto  ┐         │
│           ▲                         │      ▲      │         │
│  [ ChirpStack ]                     │  ChirpStack │ Docker, │
│           ▲ MQTT                    │      ▲      │ all real│
│  [ ChirpStack Gateway Bridge ]      │  Bridge     ┘         │
│           ▲ UDP 1700 (Semtech)      │      ▲ UDP 1700       │
│  [ gateway ]                        │  gateway_mock.py      │
│           ▲ LoRa, 920MHz (AS923)    │  fakes the gateway    │
│  [ end device ]                     │  and the device       │
└─────────────────────────────────────────────────────────────┘
```

## Run it

```bash
# 1. ChirpStack, its bridge, Mosquitto, PostgreSQL and Redis
docker compose up -d --wait

# 2. register the gateway and the device (once)
uv sync
uv run provision.py

# 3. the application from the hello example, unchanged
(cd ../hello && uv sync && uv run app.py)

# 4. in another terminal, the fake gateway and device
uv run gateway_mock.py
```

`gateway_mock.py` prints the frames on the wire:

```
[device] uplink fCnt 0: b'hello #1'
         PHYPayload 40 40 94 18 00 00 00 00 01 73 ff f8 b5 f8 b9 7c 4b 37 51 e4 a2
[gateway] downlink 923.2 MHz SF10BW125 at uplink + 1.000 s, PHYPayload a0 40 94 18 00 80 00 00 01 d5 d3 ...
[device] confirmed downlink fCnt 0, FPort 1: b'hello from the app'
[device] uplink fCnt 1 +ACK: b'hello #2'
         PHYPayload 40 40 94 18 00 20 01 00 01 86 c9 40 25 29 62 67 e1 e7 84 de 81
```

and `app.py` the same events as in hello, now produced by ChirpStack:

```
[app] uplink from 0101010101010101 fCnt 0 via 0016c001f153a14c (RSSI -95, SNR 5.5): b'hello #1'
[app] downlink cbd2d4bb queued for 0101010101010101
[app] downlink cbd2d4bb transmitted by 0016c001f153a14c (fCntDown 0)
[app] uplink from 0101010101010101 fCnt 1 via 0016c001f153a14c (RSSI -95, SNR 5.5): b'hello #2'
[app] downlink cbd2d4bb acknowledged by the device: 'hello from the app'
```

The web UI is at <http://localhost:8080> (admin / admin). The device's
*LoRaWAN frames* tab shows the same frames decoded by ChirpStack.

Stop everything with `docker compose down`, or `docker compose down -v` to
also wipe the database.

## Reading a frame

The first uplink, byte by byte:

```
40           MHDR: MType 010 = unconfirmed data up, LoRaWAN R1
40 94 18 00  DevAddr 00189440, little-endian
00           FCtrl: ADR off, no ACK, no FOpts
00 00        FCnt 0 (low 16 bits)
01           FPort 1
73 ff .. 4b  FRMPayload "hello #1", encrypted with AppSKey
37 51 e4 a2  MIC: AES-CMAC with NwkSKey
```

The next uplink has FCtrl `20`: the ACK bit, answering the confirmed
downlink (MHDR `a0`, MType 101) it received in between.

## What happens

- **The gateway is a radio with a UDP socket.** It never decrypts, never
  checks a MIC and never knows which device sent what. It sends each frame
  it hears as a `PUSH_DATA` (`rxpk`: frequency, data rate, RSSI, SNR and a
  microsecond timestamp), and polls with `PULL_DATA` so the bridge knows
  where to send downlinks.
- **The network times the downlink, the gateway just obeys.** A downlink
  arrives as a `PULL_RESP` *before* it is due, with a timestamp to transmit
  at: the uplink's timestamp plus 1 s, i.e. the device's RX1 window. The
  gateway queues it and answers `TX_ACK`.
- **Two keys, two jobs.** NwkSKey signs every frame (the MIC), so the network
  can authenticate it. AppSKey encrypts the payload, so in principle only the
  application can read it. ChirpStack holds both here, which is why the
  integration hands `app.py` plaintext.
- **Counters make the crypto work.** The keystream is derived from the
  frame counter, so the same counter must never be used twice. That is also
  why the first uplink is byte-for-byte identical on every fresh start:
  same keys, same counter, same plaintext.
- **ABP devices must keep their counters.** `gateway_mock.py` saves them in
  `device-state.json`, as a real device would in flash. Delete the file and
  restart it, and ChirpStack drops every uplink with an
  `UPLINK_F_CNT_RESET` log event, which `app.py` prints. To recover, stop
  `gateway_mock.py` and run `uv run provision.py --reactivate`, which resets
  the counters on both sides.
- **…but that recovery reuses the keystream.** After a reactivation the
  counters start again under the *same* session keys, so `hello #1` at fCnt 3
  is encrypted with exactly the keystream an earlier `hello #4` at fCnt 3
  was. The two ciphertexts then differ only where the plaintexts do, by the
  same XOR (`'4' ^ '1'` = `e7 ^ e2` = `05`), and knowing one plaintext reveals
  the other. [otaa-hello](../otaa-hello/) avoids this: every join brings new
  keys.
- **The downlink can be quicker than expected.** ChirpStack waits about
  200 ms to collect copies of an uplink from other gateways before
  publishing it. Here, `app.py` reacts within that time and the reply makes
  it into the RX1 window of the very uplink it answers. Do not rely on that;
  usually it goes with the next uplink.

## Files

| File | Role |
|---|---|
| [gateway_mock.py](gateway_mock.py) | Fake gateway (Semtech UDP) and fake ABP device. |
| [lorawan.py](lorawan.py) | LoRaWAN 1.0.x data frames: build, parse, encrypt, MIC. |
| [provision.py](provision.py) | Registers the gateway, device profile, application and device through ChirpStack's gRPC API. |
| [common.py](common.py) | Addresses, identifiers and keys shared by both. |
| [compose.yaml](compose.yaml) | ChirpStack v4, Gateway Bridge, Mosquitto, PostgreSQL, Redis. |
| [configuration/](configuration/) | Their configuration, from [chirpstack-docker](https://github.com/chirpstack/chirpstack-docker), with only the AS923 region enabled. |

`lorawan.py` was checked against the
[lora-packet](https://github.com/anthonykirby/lora-packet) test frame
`40F17DBE4900020001954378762B11FF0D`, which decodes to `test`.

## What the mock does not do

- **MAC commands.** The device prints any it receives but never answers. ADR
  is off, so ChirpStack has no reason to send them here.
- **OTAA.** No join request or join accept; see [otaa-hello](../otaa-hello/).
- **RX2, Class B and C.** Downlinks are delivered at whatever time the
  network asks for.
- **Radio effects.** Every frame arrives, with the same RSSI and SNR.

## Dependencies

- [`chirpstack-api`](https://pypi.org/project/chirpstack-api/) — ChirpStack's
  gRPC client, used by `provision.py`.
- [`cryptography`](https://pypi.org/project/cryptography/) — AES and AES-CMAC.

The fake gateway uses only the standard library's `socket`.

## References

- LoRaWAN 1.0.3 specification, LoRa Alliance — sections 4 (frame format) and
  6.1.4 (encryption and MIC).
- [Semtech UDP packet forwarder protocol](https://github.com/Lora-net/packet_forwarder/blob/master/PROTOCOL.TXT)
- [chirpstack-docker](https://github.com/chirpstack/chirpstack-docker)
