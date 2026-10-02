# LoRaWAN hardware and Japan's radio certification (技適)

What to buy to move from the fake gateway and device in this repo to real
radios, and what Japanese radio law asks of them. Checked on 2026-10-02;
certifications change, so confirm the exact variant before buying.

## The short version

- Anything that **transmits** on 920MHz in Japan needs 技適 (technical
  conformity certification), shown as the 技適 mark and a number on the
  device. Gateways transmit too: downlinks and join accepts.
- A product existing, or being sold online, says nothing about 技適.
  Certification is per model **and variant**: the EU868 or US915 version of a
  board is usually not the certified one.
- **Receiving only** emits nothing, so a passive sniffer that never joins a
  network is not a 技適 issue. Anything that takes part in a LoRaWAN network
  transmits:
  - Sensors send every uplink.
  - Gateways send downlinks even when the application never does: OTAA
    join accepts, ACKs for confirmed uplinks, and MAC commands such as ADR's
    `LinkADRReq` or `DevStatusReq`.
  - Applications send commands: reporting intervals, thresholds, time sync,
    actuators, FUOTA firmware updates.
- For short experiments with uncertified gear there is a notification-based
  exemption (see [Using uncertified hardware](#using-uncertified-hardware)).

## Kinds of hardware

| Kind | Role | Talks to the host over | Typical chip |
|---|---|---|---|
| Gateway concentrator | Receives 8 channels and all SFs at once; transmits downlinks | SPI or USB (Semtech binary protocol) | SX1302 / SX1303 + SX1250 |
| Complete gateway | Concentrator + Linux host + backhaul + enclosure | Ethernet, Wi-Fi, LTE | as above |
| End-device module | Joins as a device; one channel and SF at a time | UART AT commands, often via USB-serial | STM32WL (SX126x inside) |

A concentrator is what turns a Raspberry Pi into a gateway. An end-device
module is what replaces `gateway_mock.py`'s fake device.

## Quick experiments with a Raspberry Pi or a PC

| Product | Kind | Japan certification | Notes |
|---|---|---|---|
| [RAKwireless RAK5146](https://docs.rakwireless.com/certification/product-compliance-certification/wislink/rak5146/) | SX1303 concentrator (mPCIe; SPI or USB) | JRL listed by RAK | Goes on a Raspberry Pi HAT or USB adapter. Run Semtech's `lora_pkt_fwd` or ChirpStack Concentratord, then point it at ChirpStack like [gateway-hello](../gateway-hello/)'s fake gateway. |
| [RAKwireless RAK2245](https://www.thethingsnetwork.org/docs/gateways/rak2245/) | Older SX1301 Pi HAT with GPS | Check the variant | Common second-hand; the SX1301 generation is superseded by SX1302/1303. |
| [Seeed Wio-E5 mini](https://akizukidenshi.com/catalog/g/g118092/) | STM32WL end-device board, USB | 技適 201-230184 (per Akizuki listing) | AT commands over USB serial: `AT+JOIN`, `AT+MSG`. Its test mode can also receive raw LoRa frames on one channel. Set it to AS923 before transmitting. |
| [RAKwireless RAK3172](https://docs.rakwireless.com/certification/product-compliance-certification/wisduo/rak3172/) | STM32WL end-device module | JRL listed by RAK; Japan variants support AS923-1 with LBT | Bare module; use an evaluation board or a USB-UART adapter for AT commands. |

A simple first real setup:

```
[Wio-E5 mini] ))) 920MHz ((( [RAK5146 on a Raspberry Pi] ── Ethernet ──> [ChirpStack from gateway-hello]
  end device                   lora_pkt_fwd / Concentratord
```

## Production

| Product | Kind | Japan certification | Notes |
|---|---|---|---|
| [RAKwireless RAK7268 / RAK7268V2](https://docs.rakwireless.com/certification/product-compliance-certification/wisgate/rak7268/) | Indoor 8-channel gateway | JTBL (RAK7268, V2) and JRL (also C and CV2 LTE variants) listed by RAK | Ethernet, Wi-Fi; LTE in the C variants. |
| [Milesight UG67](https://www.milesight.com/iot/product/lorawan-gateway/ug67) | Outdoor IP67 gateway | TELEC listed by Milesight | Optional LTE and GNSS; built-in network server, or forward to your own ChirpStack. |
| Kerlink, MultiTech and others | Indoor and outdoor gateways | Varies by model | Check each model before buying. |
| Commercial sensors | End devices | Must carry 技適 | Prefer devices sold for Japan (AS923) by a domestic distributor. |
| Your own board with a certified module (RAK3172, Wio-E5) | End device | The module's 技適 | Keep the module's mark visible and stay within its certified conditions, such as the antenna. |

Beyond certification, production adds: outdoor enclosures, lightning
protection and grounding, PoE, LTE backhaul where there is no wire, GNSS for
Class B or geolocation, and remote management.

## Japan's 920MHz rules

LoRaWAN in Japan uses the AS923 regional parameters, which follow ARIB
STD-T108. Per [ROHM's summary](https://techweb.rohm.co.jp/iot/tech-info/engineer/4604),
LoRaWAN devices pick one of two operating modes:

| Carrier sense before transmitting | Max per transmission | Max per hour |
|---|---|---|
| 5 ms or longer | 4 s | No limit |
| 128 µs or longer | 400 ms | 360 s |

Transmit power is limited to 20 mW, on 200 kHz unit channels. Carrier sense
(listen before talk, LBT) is why Japan-certified gateways and modules ship
Japan-specific firmware or variants. Certified products handle these rules
for you; do not change region settings away from AS923 on them.

## Using uncertified hardware

The Ministry of Internal Affairs and Communications runs an exemption for
experiments (技適未取得機器を用いた実験等の特例制度, the "180-day rule").
Per its [2026-03-19 presentation](https://www8.cao.go.jp/kisei-kaikaku/kisei/meeting/wg/2501_04startup/260319/startup12_01.pdf):

- You file a notification online **before** use. It is free, and individuals
  can file too.
- The purpose must be experiments, tests or research.
- The equipment must meet standards equivalent to Japan's technical
  standards, and you state how you confirmed that.
- Use is limited to 180 days from the notification. You cannot simply extend
  it for the same standard and purpose.
- 特定小電力無線局 for telemetry and data transmission, the 920MHz category,
  is among the eligible equipment. [This list](https://blog.osakana.net/archives/9746)
  names LoRaWAN AS923 explicitly.

It does not cover commercial operation. Production hardware needs 技適.

## How to check a product

1. Look for the 技適 mark and its number on the device, its label or its
   electronic display.
2. Search the number in the Ministry's database of certified equipment
   (技術基準適合証明等を受けた機器の検索).
3. Confirm the certified variant matches what you hold: frequency band
   (AS923 / 920MHz), and the LTE or GNSS options.
4. For a module inside a product, check that the module's mark is shown and
   that the antenna is one it was certified with.
