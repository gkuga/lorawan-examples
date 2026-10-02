# LoRaWAN basics

Notes on the building blocks of a LoRaWAN network and how they map to
ChirpStack and to the examples in this repo.

## The big picture

LoRaWAN is a star-of-stars network: end devices talk to gateways over radio,
gateways forward everything to one network server over IP, and the network
server hands decoded data to your application.

```
[ end device ] ))) LoRa radio ((( [ gateway ] ── IP ──> [ network server ] ──> [ application ]
  sensor           920MHz (AS923)   antenna +   UDP/MQTT    ChirpStack       MQTT/HTTP  your code
                                    radio
```

## Components

| Component | What it is | What it does |
|---|---|---|
| End device | Battery-powered sensor or actuator | Broadcasts a few bytes over LoRa now and then. It is not paired with a gateway; every gateway in range hears it. |
| Gateway | Antenna + LoRa radio + IP uplink | Relays packets between radio and IP without decrypting them. On downlink it transmits exactly when and on the frequency the server says. |
| Network server (ChirpStack) | The brain of the network | Deduplicates packets heard by several gateways, checks the MIC, tracks frame counters, handles OTAA joins, runs ADR, schedules downlinks, and passes decrypted payloads to applications. |
| Application | Your own system | Receives data from ChirpStack over MQTT or HTTP and stores, visualises or acts on it. |

Devices join the network in one of two ways:

- **ABP (Activation By Personalization):** the device address and session keys
  are provisioned in advance. See [gateway-hello](../gateway-hello/).
- **OTAA (Over-The-Air Activation):** the device sends a Join Request and
  session keys are derived at join time. More secure and the usual choice in
  production. See [otaa-hello](../otaa-hello/).

| | ABP ([gateway-hello](../gateway-hello/)) | OTAA ([otaa-hello](../otaa-hello/)) |
|---|---|---|
| Provisioned on the device | DevAddr, NwkSKey, AppSKey | DevEUI, AppEUI (JoinEUI), AppKey |
| After a restart | Same keys. Resetting FCnt to 0 reuses the keystream, so counters must survive power cycles. | Joins again: new DevAddr and session keys, so FCnt from 0 is safe. |
| RX settings (RX1 delay, data rates) | Written into the device profile by hand (`abp_rx1_delay` and friends) | Delivered in the join accept |
| If session keys leak | Both the device and the server must be reprovisioned | A rejoin replaces them (unless AppKey itself leaked) |

ChirpStack v4 combines roles the LoRaWAN architecture treats as separate:
Network Server, Application Server and Join Server.

## LoRa vs LoRaWAN

LoRa is how bits travel over the air (physical layer). LoRaWAN is the network
protocol built on top of it (MAC layer and above).

```
┌──────────────────────────────────────────────┐
│ Application payload                          │
├──────────────────────────────────────────────┤
│ LoRaWAN  (MAC)       open spec, LoRa Alliance│
│   joins (OTAA/ABP), encryption, DevAddr,     │
│   frame counters, classes A/B/C, ADR,        │
│   regional parameters (AS923, EU868, ...)    │
├──────────────────────────────────────────────┤
│ LoRa     (PHY)       proprietary, Semtech    │
│   chirp spread spectrum, SF7-SF12,           │
│   bandwidth, TX power                        │
├──────────────────────────────────────────────┤
│ Radio spectrum (920MHz band in Japan)        │
└──────────────────────────────────────────────┘
```

**LoRa (physical layer)**

- A modulation technique based on chirp spread spectrum (CSS).
- Long range (several km) and low power, at the cost of low data rate
  (hundreds of bps to a few kbps).
- The spreading factor (SF7 to SF12) is the key knob: a higher SF reaches
  farther but is slower and occupies the channel longer.
- LoRa alone is enough for point-to-point links, but then addressing,
  security and retries are up to you.

**LoRaWAN (network layer)**

- Defines the star-of-stars topology above.
- Two session keys:
  - **NwkSKey**: used by the network server to compute and verify the MIC
    (message integrity).
  - **AppSKey**: encrypts the application payload end to end.
- DevAddr and frame counters identify devices and prevent replay attacks.
- Device classes trade power for downlink availability:
  - **Class A**: receives only right after an uplink.
  - **Class B**: also receives in scheduled slots.
  - **Class C**: is almost always listening.
- ADR lets the network server tune each device's SF and TX power.
- Regional parameters fix frequencies and duty-cycle / dwell-time limits per
  country.

**Common confusions**

- "We use LoRa" usually means LoRaWAN.
- Not everything on LoRa is LoRaWAN: raw point-to-point links and mesh
  projects such as Meshtastic use LoRa without LoRaWAN.
- LoRaWAN also defines non-LoRa PHYs (FSK, LR-FHSS).

In ChirpStack's frame view you see both layers side by side: SF, RSSI and SNR
come from LoRa, while DevAddr, FCnt and MIC come from LoRaWAN.

## ChirpStack concepts

```
ChirpStack
├─ Network Server (admin)   tenants, users, regions, global device profiles
└─ Tenant                   an isolated space for one organisation
   ├─ Gateways
   ├─ Device profiles       the "type" of a device: LoRaWAN version, region,
   │                        OTAA/ABP, payload codec
   └─ Applications          a group of devices + its integrations (MQTT/HTTP)
      └─ Devices            one device: DevEUI and keys
```

- **Tenant**: a partition for sharing one ChirpStack between organisations.
  Each tenant has its own gateways, applications, devices and users. Gateways
  can optionally be shared across tenants. For learning, the default
  `ChirpStack` tenant is enough.

## Reading the gateway list

| Column | Meaning |
|---|---|
| Status | Online while gateway stats keep arriving; it turns Offline once they stop for a while. |
| Last seen | When the last stats message or uplink arrived. |
| Gateway ID | The gateway's EUI64. Packets from an unregistered ID are ignored. |
| Name | Display name set at registration. |
| Region ID | ID of the region config in ChirpStack (for example `as923`), tied to the gateway bridge / MQTT topic prefix the gateway uses. |
| Region common-name | The LoRaWAN regional parameter set, for example AS923 in Japan. |
| Downlink priority | Tie-breaker when several gateways heard the same uplink and one must send the downlink. |

Clicking a gateway ID opens its details. The **LoRaWAN frames** tab shows raw
frames in real time.

## Where to run ChirpStack

What matters is that gateways can reach it over IP.

| Location | Good for |
|---|---|
| Local (Docker on a laptop) | Learning and development, as in this repo. |
| Cloud (AWS, GCP, ...) | Many sites, scattered gateways, remote access, central operations. The typical production setup is "gateways on site, ChirpStack in the cloud". |
| On-premises / on the gateway | Closed networks such as factories. Some gateways run ChirpStack themselves. |

You can also skip self-hosting and use a managed network server such as The
Things Network or a carrier's LoRaWAN service.

## Next steps

1. Open a gateway's **LoRaWAN frames** tab and watch the encrypted frames
   arrive.
2. Open a device's **Events** tab and compare with the decrypted payloads.

The contrast shows the division of labour: the gateway never sees the
payload; the network server uses the keys to recover it.
