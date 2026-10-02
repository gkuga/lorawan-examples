# TODO

What the examples do not cover yet, roughly in the order worth doing.

## Fake device and gateway

- [ ] **MAC commands.** Turn ADR on in the fake device and answer what
  ChirpStack sends: `LinkADRReq` (change data rate and power),
  `DevStatusReq` (battery and margin, which produces the `status` event) and
  `LinkCheckReq` from the device side. Today the device prints MAC commands
  and never answers.
- [ ] **RX2.** Let the device miss RX1 now and then, and see the network fall
  back to RX2 (923.2 MHz, DR2) or wait for the next uplink.
- [ ] **Class C.** A device that listens all the time, so a downlink goes out
  at once (`imme` in the `txpk`) instead of waiting for an uplink.
- [ ] **Two gateways, one uplink.** Run two fake gateways that both hear the
  same frame, and watch ChirpStack deduplicate it into one `up` event with
  two `rxInfo` entries and pick one gateway for the downlink.
- [ ] **Payload codec.** Add a JavaScript codec to the device profile so the
  `up` event carries a decoded `object`, and send downlinks as `object`.
- [ ] **LoRaWAN 1.0.4 / 1.1.** A DevNonce counter instead of a random nonce
  (1.0.4), then the 1.1 key hierarchy: NwkKey and AppKey, JoinEUI, three
  network session keys.
- [ ] **LoRa Basics Station.** The other gateway protocol, WebSocket instead
  of UDP, through the bridge's Basic Station backend.
- [ ] **API key.** `provision.py` logs in as admin/admin; create and use an
  API key instead, as a real integration would.

## Real hardware

See [docs/lorawan-hardware.md](docs/lorawan-hardware.md) for products and
技適. Use only certified AS923 variants.

- [ ] **Real gateway.** RAK5146 on a Raspberry Pi
  ([docs/rak5146-raspberry-pi.md](docs/rak5146-raspberry-pi.md)) running
  `lora_pkt_fwd` or ChirpStack Concentratord, pointed at gateway-hello's
  ChirpStack. Replaces `Gateway` in the mocks.
- [ ] **Real device.** Wio-E5 mini over USB serial with AT commands
  (`AT+JOIN`, `AT+MSG`), joining with otaa-hello's device keys. Replaces
  `Device`.
- [ ] **Both.** Wio-E5 mini → RAK5146 → ChirpStack → `hello/app.py`, with no
  fake left.
- [ ] **A Wio-E5 mock.** A PTY that answers the Wio-E5's AT commands, like
  zeta-examples' uart-hello does for a ZETA module, so the MCU side can be
  written before the board arrives.

## Docs

- [ ] hello/README.md: add the `join` event, which `app.py` now prints, to
  the topic table.
