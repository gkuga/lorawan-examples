# Wiring a RAK5146 to a Raspberry Pi

Two ways to turn a Raspberry Pi into a gateway with a RAK5146 concentrator.
For which RAK5146 variant to buy and Japan's radio certification, see
[lorawan-hardware.md](lorawan-hardware.md). Checked against RAK's documents
on 2026-10-02.

| | A. Pi HAT (SPI) | B. USB adapter |
|---|---|---|
| RAK5146 variant | SPI: `RAK5146-11Z` for AS923 | USB: `RAK5146-12Z` for AS923 |
| Carrier | [RAK2287/RAK5146 Pi HAT](https://store.rakwireless.com/products/rak2287-pi-hat) | [mPCIe to USB Board](https://store.rakwireless.com/products/mpcie-to-usb-board) |
| Host sees | `/dev/spidev0.0` | `/dev/ttyACM0` |
| GPS | Wired to the Pi's UART | Not reachable from the host |
| Also works on | Raspberry Pi only | Any Linux host with USB, such as an Armadillo-IoT G4 |

Z is the feature digit: 0 none, 2 LBT, 5 GPS, 6 LBT and GPS. Use an LBT
variant in Japan. RAK's store lists LBT options for the USB variant; check
SPI + LBT availability before choosing option A.

Both carriers hold the module in an mPCIe slot. Antennas attach to the
module's own MHF (u.FL) connectors, LoRa and, on GPS variants, GPS. Never
transmit without the LoRa antenna attached.

## A. Pi HAT over SPI

The HAT stacks on the Pi's 40-pin header. No wires to run, but these are the
pins it uses, per the
[Pi HAT datasheet](https://docs.rakwireless.com/product-categories/wishat/rak2287-rak5146-pi-hat/datasheet/):

```
 HAT signal          Pi GPIO   pin  pin  Pi GPIO   HAT signal
 ------------------  --------  ---  ---  --------  ------------------
 -                   3V3         1  2    5V        5V power in
 -                   GPIO2       3  4    5V        5V power in
 -                   GPIO3       5  6    GND       GND
 -                   GPIO4       7  8    GPIO14    GPS UART RX
 GND                 GND         9  10   GPIO15    GPS UART TX
 SX1303 RESET        GPIO17     11  12   GPIO18    -
 -                   GPIO27     13  14   GND       GND
 -                   GPIO22     15  16   GPIO23    -
 -                   3V3        17  18   GPIO24    -
 SPI MOSI            GPIO10     19  20   GND       GND
 SPI MISO            GPIO9      21  22   GPIO25    GPS RESET (low)
 SPI CLK             GPIO11     23  24   GPIO8     SPI CE0
 -                   GND        25  26   GPIO7     SX1303 GPIO6
 -                   ID_SD      27  28   ID_SC     -
 -                   GPIO5      29  30   GND       -
 -                   GPIO6      31  32   GPIO12    GPS STANDBY (low)
 -                   ...     33-39  34-40  ...       -
```

`-` in a HAT signal column means the HAT leaves that pin unconnected.

| Pi pin | Pi GPIO | HAT signal | Notes |
|---|---|---|---|
| 2, 4 | 5V | 5V | Power for the HAT |
| 6, 9, 14, 20 | GND | GND | |
| 19 | GPIO10 (MOSI) | SPI_MOSI | |
| 21 | GPIO9 (MISO) | SPI_MISO | |
| 23 | GPIO11 (SCLK) | SPI_CLK | |
| 24 | GPIO8 (CE0) | SPI_CE | So the device is `/dev/spidev0.0` |
| 11 | GPIO17 | RESET_RAK2287 | SX1303 reset, active high, at least 100 ns |
| 26 | GPIO7 | SX1303 GPIO6 | |
| 8 | GPIO14 (TXD0) | GPS UART RX | GPS variants only |
| 10 | GPIO15 (RXD0) | GPS UART TX | GPS variants only |
| 22 | GPIO25 | GPS reset | Active low |
| 32 | GPIO12 | GPS standby | Active low |

The HAT takes 5 V from the Pi; it does not use the Pi's 3.3 V rail. The
RAK5146 draws about 0.5 A at 3.3 V while transmitting at 27 dBm, so use the
Pi's official power supply.

Setup:

1. Enable SPI, and the serial port for GPS without the login shell, with
   `sudo raspi-config` → Interface Options.
2. Build Semtech's [`sx1302_hal`](https://github.com/Lora-net/sx1302_hal),
   or install ChirpStack Gateway OS, which supports this HAT.
3. In the packet forwarder config, set `com_type` to `"SPI"` and `com_path`
   to `"/dev/spidev0.0"`. Set the reset GPIO in the reset script to 17, the
   HAT's `RESET_RAK2287`.
4. Point the forwarder at ChirpStack, as with
   [gateway-hello](../gateway-hello/)'s fake gateway (UDP port 1700), and
   register the gateway EUI in ChirpStack.

## B. USB adapter

```
[Raspberry Pi] USB-A ──USB cable── [mPCIe to USB Board] ══mPCIe══ [RAK5146 USB variant]
                                                                    │ MHF
                                                                    └── 920MHz LoRa antenna
```

- No GPIO wiring: power and data both come over USB.
- The module shows up as `/dev/ttyACM0`. The variant's onboard STM32L412
  bridges USB to the SX1303.
- In the packet forwarder config, set `com_type` to `"USB"` and `com_path` to
  `"/dev/ttyACM0"`.
- Prefer a port and cable that can supply the module's transmit current.

The same setup works on an Armadillo-IoT G4's USB 3.0 Type-A port; see
[lorawan-hardware.md](lorawan-hardware.md#on-an-armadillo-iot-g4).
