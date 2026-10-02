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
| [RAKwireless RAK5146](https://docs.rakwireless.com/certification/product-compliance-certification/wislink/rak5146/) | SX1303 concentrator (mPCIe; SPI or USB) | JRL listed by RAK: certificate 005-102990 for "RAK5146" (920MHz telemetry/data, 2022-03-15) | SKU `RAK5146-1YZ` for AS923: Y = 1 SPI / 2 USB; Z = 0 none / 2 LBT / 5 GPS / 6 LBT+GPS, e.g. `RAK5146-122` (USB + LBT). The USB variant adds an STM32L412 that bridges USB to the SX1303. Goes on a Raspberry Pi HAT or USB adapter. Run Semtech's `lora_pkt_fwd` or ChirpStack Concentratord, then point it at ChirpStack like [gateway-hello](../gateway-hello/)'s fake gateway. |
| [RAKwireless RAK2245](https://www.thethingsnetwork.org/docs/gateways/rak2245/) | Older SX1301 Pi HAT with GPS | Check the variant | Common second-hand; the SX1301 generation is superseded by SX1302/1303. |
| [Seeed Wio-E5 mini](https://akizukidenshi.com/catalog/g/g118092/) | STM32WL end-device board, USB | 技適 201-230184 (per Akizuki listing) | AT commands over USB serial: `AT+JOIN`, `AT+MSG`. Its test mode can also receive raw LoRa frames on one channel. Set it to AS923 before transmitting. |
| [RAKwireless RAK3172](https://docs.rakwireless.com/certification/product-compliance-certification/wisduo/rak3172/) | STM32WL end-device module | JRL listed by RAK; Japan variants support AS923-1 with LBT | Bare module; use an evaluation board or a USB-UART adapter for AT commands. |

A simple first real setup:

```
[Wio-E5 mini] ))) 920MHz ((( [RAK5146 on a Raspberry Pi] ── Ethernet ──> [ChirpStack from gateway-hello]
  end device                   lora_pkt_fwd / Concentratord
```

The two sides are not interchangeable. A Wio-E5 cannot be a gateway, since it
hears one channel at a time, and a RAK5146 cannot be a device, since it does
no LoRaWAN processing.

| | Wio-E5 | RAK5146 |
|---|---|---|
| Side | End device | Gateway concentrator |
| Chip | STM32WL: MCU + single-channel radio | SX1303 + SX1250: 8-channel receiver |
| LoRaWAN processing | Does it itself: join, encryption, MIC | None; relays frames as they are |
| Replaces in [otaa-hello](../otaa-hello/) | `Device` | `Gateway` |

### Connecting the Wio-E5 mini

Per [Seeed's wiki](https://wiki.seeedstudio.com/ja/LoRa_E5_mini/), all at
3.3 V logic:

| Connection | Use | Details |
|---|---|---|
| USB-C | Quick tests from a PC or Raspberry Pi | Onboard USB-UART; shows up as a serial port. AT commands at 9600 baud. |
| UART header (PB6/PB7) | Wiring to a Raspberry Pi or another MCU | On a Pi, GPIO14/15 (UART TX/RX), crossed over, plus a shared GND. |
| SWD | Your own firmware (STM32CubeWL) | Needs an ST-LINK. Erasing the factory AT firmware is irreversible. |

The Wio-E5 module itself is an STM32WLE5JC, an MCU and LoRa radio in one
chip, so it can also run your sensor code directly. Seeed sells it in other
forms too: Grove - Wio-E5, the Wio-E5 Dev Kit, and the bare module for your
own boards.

## Building your own gateway

A Linux board plus a concentrator is a gateway. RAKwireless sells
Raspberry Pi based developer gateways built this way.

- **Hardware:** a RAK5146 (mPCIe) on a Pi HAT or a USB adapter, a 920MHz
  antenna, and optionally a GPS antenna. In Japan, pick a variant with LBT.
  Wiring and setup: [rak5146-raspberry-pi.md](rak5146-raspberry-pi.md).
- **Software:** one of these.
  - ChirpStack Gateway OS supports Raspberry Pi with RAK concentrators.
  - Semtech's `sx1302_hal` includes `lora_pkt_fwd`. It speaks the same UDP
    protocol as [gateway-hello](../gateway-hello/)'s fake gateway.
  - LoRa Basics Station.
- **ChirpStack:** register the real gateway EUI, as with the fake one.

Fine for learning and pilots. As a product, it needs more work:

| Concern | What to do |
|---|---|
| 技適 | Use the certified concentrator variant (SPI/USB, GPS, LBT) with a certified antenna. The host's own Wi-Fi and Bluetooth need 技適 too. |
| Storage | SD cards wear out; use eMMC (Compute Module 4/5) or a read-only root filesystem. |
| Enclosure | Outdoors you need IP67, heat dissipation, lightning protection and grounding. |
| Power | Use PoE, and plan recovery after outages. |
| Operations | Plan remote monitoring, OS and forwarder updates, and backhaul recovery. |
| Supply and support | Plan part sourcing, replacements and support. |

Commercial gateways such as the RAK7268V2 or Milesight UG67 have already
solved these. For a handful of production sites, buying is usually cheaper
overall.

### On an Armadillo-IoT G4

The [Armadillo-IoT G4](https://armadillo.atmark-techno.com/armadillo-iot-g4/specs)
(Atmark Techno, i.MX 8M Plus) has no mPCIe or M.2 slot, so the RAK5146
connects over USB or SPI:

| Connection | Setup | Verdict |
|---|---|---|
| USB (recommended) | RAK5146 USB variant on an mPCIe-to-USB adapter, into the USB 3.0 Type-A port | Works with the case on; appears as `/dev/ttyACM0`. |
| SPI | RAK5146 SPI variant wired to the expansion header (SPI, plus a GPIO for reset) | The expansion header is unusable with the case fitted, so this suits prototypes only. |

- **Software:** Armadillo Base OS runs applications in podman containers.
  - Run `lora_pkt_fwd` (`com_type` USB) or ChirpStack Concentratord in a
    container built for arm64.
  - Pass `/dev/ttyACM0` into the container.
  - Check that the kernel has `cdc_acm`.
- **Strengths over a Raspberry Pi:**
  - An LTE model, for sites without a wired connection.
  - eMMC instead of an SD card.
  - DC 12 V input, and -20 to +60 °C on the LTE/WLAN models.
  - Long-term supply.
  - Safe OS updates.
  - 技適 for its own LTE and WLAN.
- **Still to solve:**
  - Mounting the 920MHz antenna and the adapter. In practice this means an
    external enclosure.
  - The RAK5146 variant's certification.
  - GNSS. On the GPS variants the PPS reaches the SX1303 on the module,
    but position and time (NMEA) come out on the mPCIe UART pins, not over
    USB. Only Class B or gateway geolocation needs them.
- **Not a gateway:** EASEL's
  [ES920LR3-AR](https://easel5.com/service/products-information/products/wireless-module/es920lr3-ar/)
  is a LoRa add-on for the Armadillo-IoT G3. It is a single-channel,
  device-type module, so it cannot act as a gateway.

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

### Is the Wio-E5 mini production-ready?

It is fine for a few indoor, USB-powered pilot units: it has 技適 and the
module inside is a production part rated -40 to 85 °C. Seeed positions the
board itself for rapid testing and small prototypes:

- The bundled antenna is for EU868/US915. Use a 920MHz antenna that the
  certification allows.
- It has no enclosure.
- The 2.1 µA sleep figure is the module's. The board's USB-UART and power
  circuits draw more.
- It expects 3.7 to 5 V or USB-C power.

### Mass-producing end devices

| Approach | Strengths | Costs |
|---|---|---|
| A. Buy commercial sensors | 技適, enclosure, battery design and codec done; fastest | The sensor you need may not exist; higher unit price |
| B. Certified module + host MCU (AT commands) | The module handles LoRaWAN; keep an existing MCU design | Two MCUs: more power and parts |
| C. Certified module running your firmware | One STM32WL does sensing and LoRaWAN: lowest power and part count | You own the LoRaWAN stack (STM32CubeWL, or RUI3 on RAK3172) |
| D. STM32WL chip-down | Lowest unit cost | Your own 技適, RF design and antenna tuning; pays off only at high volume |

C is the usual target. It reuses the module's 技適, as long as the module's
mark stays visible and the antenna is a certified one. A natural path is to
prototype with B (a Wio-E5 mini and AT commands), then move to C.

LoRaWAN-specific work for production:

- **Key provisioning:** give every device its own DevEUI and AppKey. Decide
  how the factory writes them and how they are bulk-registered in
  ChirpStack.
- **Key storage:** use a secure element where leaks matter.
- **FUOTA:** decide early whether firmware updates go over the air; it
  shapes the flash layout.
- **LoRa Alliance certification:** optional, but some operators require it.
- **Supply:** confirm the module's lifetime and keep a second source, such
  as RAK3172 alongside Wio-E5.

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
