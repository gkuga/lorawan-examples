# otaa-hello

A fake LoRaWAN device that **joins** a real ChirpStack over the air.

[gateway-hello](../gateway-hello/) used ABP: the device shipped with its
address and session keys, and had to keep its frame counters forever. This
example uses OTAA instead. The device ships with one long-term root key
(AppKey) and asks the network for a session every time it starts.

```
  device                          gateway       ChirpStack
    │  JoinRequest                   │               │
    │  DevEUI, AppEUI, DevNonce      │               │
    │  signed with AppKey            │               │
    ├───────────────────────────────►├──────────────►│ checks the MIC and that
    │                                │               │ DevNonce is new
    │                 JoinAccept, 5 s later (RX1)    │
    │      AppNonce, NetID, DevAddr, RX settings     │
    │      encrypted and signed with AppKey          │
    │◄───────────────────────────────┤◄──────────────┤
    │                                │               │
    │  both sides derive NwkSKey and AppSKey from    │
    │  AppKey, AppNonce, NetID and DevNonce          │
    │                                │               │
    │  data frames, fCnt from 0 ─────►──────────────►│ "join" event to the app
```

It uses gateway-hello's ChirpStack, and `hello/app.py` as the application,
both unchanged except that `app.py` now also prints `join` events.

## Run it

```bash
# 1. ChirpStack, from gateway-hello
(cd ../gateway-hello && docker compose up -d --wait)

# 2. register the device (once)
uv sync
uv run provision.py

# 3. the application from the hello example
(cd ../hello && uv run app.py)

# 4. in another terminal, the fake gateway and device
uv run gateway_mock.py
```

`gateway_mock.py` prints something like:

```
[device] join request, DevNonce e3ca
         PHYPayload 00 00 00 00 00 00 00 00 00 02 02 02 02 02 02 02 02 ca e3 c4 34 50 f7
[gateway] downlink 923.2 MHz SF10BW125 at uplink + 5.000 s, PHYPayload 20 4a 7b 8e 77 ca 65 16 34 ac cd 98 fc a1 41 fd e4
[device] joined: DevAddr 00f0ae8d
         NwkSKey 560fb24fba3853444733674bc5146d1b
         AppSKey c735ae7568cbf63455a8f2a5d37aab3f
         RX1 delay 1 s, RX1 DR offset 0, RX2 DR 2
[device] uplink fCnt 0: b'hello #1'
         PHYPayload 40 8d ae f0 00 00 00 00 01 ee e4 2b c9 2b 1b 41 a5 a1 8b 05 ad
[gateway] downlink 923.2 MHz SF10BW125 at uplink + 1.000 s, PHYPayload a0 8d ae f0 00 80 00 00 01 91 8f ...
[device] confirmed downlink fCnt 0, FPort 1: b'hello from the app'
```

Restart it and the DevAddr and both session keys are different.

## Reading the join frames

The join request is not encrypted, only signed:

```
00                       MHDR: MType 000 = join request
00 00 00 00 00 00 00 00  AppEUI, little-endian
02 02 02 02 02 02 02 02  DevEUI, little-endian
ca e3                    DevNonce e3ca, little-endian
c4 34 50 f7              MIC: AES-CMAC with AppKey
```

The join accept (`20 ...`, MType 001) is encrypted with AppKey. Decrypted it
holds AppNonce (3 bytes), NetID (3), DevAddr (4), DLSettings, RxDelay and,
in some regions, a CFList of extra channels, then the MIC.

## What happens

- **One root key, many sessions.** NwkSKey and AppSKey are each one AES block
  of AppKey over `prefix | AppNonce | NetID | DevNonce`. The network chooses
  AppNonce fresh for every join, so the keys change even if the device
  repeated its nonce.
- **Counters start from 0 every time, safely.** In gateway-hello, resetting
  an ABP device's counters reused the keystream. Here a reset always comes
  with new keys, so there is nothing to keep across power cycles and no
  keystream to reuse.
- **DevNonce is single-use.** ChirpStack remembers the DevNonces it has seen
  for a device and ignores a join request that repeats one, which defeats a
  replayed join. LoRaWAN 1.0.3 picks it at random; 1.0.4 turned it into a
  counter, because random 16-bit values collide sooner than you might think.
- **Joins wait longer.** The join accept comes 5 s after the request (RX1), or
  6 s (RX2), against 1 s for data. The mock retries after 8 s without an
  answer. Real devices back off much further; a fleet rejoining after a
  power cut is a known way to flood a network.
- **The accept tells the device how to listen.** RX1 delay, RX1 data-rate
  offset and RX2 data rate travel in the join accept. In gateway-hello they
  had to be written into the device profile by hand (`abp_rx1_delay` and
  friends) because an ABP device never receives them.
- **The 1.0.x AppKey goes in `nwk_key`.** LoRaWAN 1.1 split the root key into
  NwkKey and AppKey, and ChirpStack names its fields after 1.1. A 1.0.x
  device's AppKey belongs in `nwk_key`; put it in `app_key` and every join
  fails its MIC check.
- **Gateways need unique IDs.** This example's gateway is `...a14d`, not
  gateway-hello's `...a14c`, so both can run at once. With the same ID the
  bridge sends each downlink to whichever one polled last, and join accepts
  land on the wrong process.

## Files

| File | Role |
|---|---|
| [gateway_mock.py](gateway_mock.py) | Fake gateway (as in gateway-hello) and fake OTAA device. |
| [lorawan.py](lorawan.py) | gateway-hello's data frames plus join request, join accept and key derivation. |
| [provision.py](provision.py) | Registers the gateway, an OTAA device profile and the device with its AppKey. |
| [common.py](common.py) | Addresses, identifiers and the AppKey. |

`gateway_mock.py` and `lorawan.py` start as copies of gateway-hello's, so
each example reads on its own.

## What the mock does not do

- Rejoin while running, or join again after a lost session.
- A CFList. AS923's two default channels need none, so ChirpStack sends a
  17-byte accept without one.
- LoRaWAN 1.1, with its separate join server, JoinEUI and three network keys.

## Dependencies

- [`chirpstack-api`](https://pypi.org/project/chirpstack-api/) — ChirpStack's
  gRPC client, used by `provision.py`.
- [`cryptography`](https://pypi.org/project/cryptography/) — AES and AES-CMAC.

## References

- LoRaWAN 1.0.3 specification, LoRa Alliance — section 6.2 (over-the-air
  activation).
- [`device.proto`](https://github.com/chirpstack/chirpstack/blob/master/api/proto/api/device.proto) —
  the `DeviceKeys` note about 1.0.x AppKeys.
