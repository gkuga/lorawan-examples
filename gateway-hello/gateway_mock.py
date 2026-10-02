"""A fake LoRaWAN gateway with one fake ABP device behind it.

The gateway speaks the Semtech UDP packet forwarder protocol, the oldest and
most common way a gateway talks to a network server, to a real ChirpStack
Gateway Bridge. The device builds real LoRaWAN 1.0.3 frames: encrypted
payload, MIC, frame counters. Nothing here is faked above the radio.

    uv run gateway_mock.py
"""

import base64
import itertools
import json
import os
import socket
import threading
import time
from datetime import datetime, timezone

import lorawan
from common import (
    APP_S_KEY,
    BRIDGE_HOST,
    BRIDGE_PORT,
    DATA_RATE,
    DEV_ADDR,
    F_PORT,
    FREQUENCY_MHZ,
    GATEWAY_ID,
    NWK_S_KEY,
    STATE_FILE,
)

UPLINK_INTERVAL_S = 10
PULL_INTERVAL_S = 5  # keepalive that also tells the bridge where to send downlinks
STAT_INTERVAL_S = 30

# Semtech UDP packet forwarder protocol, version 2. Every datagram starts with
# the protocol version, a random 2-byte token and an identifier.
PROTOCOL_VERSION = 2
PUSH_DATA, PUSH_ACK, PULL_DATA, PULL_RESP, PULL_ACK, TX_ACK = 0, 1, 2, 3, 4, 5


class Device:
    """An ABP device: session keys and DevAddr are fixed, counters persist.

    Losing the counters is the classic ABP failure. The network rejects an
    uplink whose counter is not higher than the last one it saw, so a device
    that restarts from 0 goes silent until it is reactivated.
    """

    def __init__(self) -> None:
        self.dev_addr = bytes.fromhex(DEV_ADDR)
        self.nwk_s_key = bytes.fromhex(NWK_S_KEY)
        self.app_s_key = bytes.fromhex(APP_S_KEY)
        self.lock = threading.Lock()
        self.ack_next = False  # owe the network an ACK for a confirmed downlink
        state = load_state()
        self.f_cnt_up = state.get("f_cnt_up", 0)
        self.f_cnt_down = state.get("f_cnt_down", -1)  # last downlink counter seen

    def uplink(self, payload: bytes) -> bytes:
        with self.lock:
            frame = lorawan.DataFrame(
                mtype=lorawan.UNCONFIRMED_UP,
                dev_addr=self.dev_addr,
                # ADR off, so the network does not start tuning the data rate.
                f_ctrl=lorawan.FCTRL_ACK if self.ack_next else 0,
                f_cnt=self.f_cnt_up,
                f_port=F_PORT,
                payload=payload,
            )
            phy = lorawan.encode(frame, self.nwk_s_key, self.app_s_key)
            ack = " +ACK" if self.ack_next else ""
            print(f"[device] uplink fCnt {frame.f_cnt}{ack}: {payload!r}")
            print(f"         PHYPayload {phy.hex(' ')}")
            self.ack_next = False
            self.f_cnt_up += 1
            self.save()
        return phy

    def receive(self, phy: bytes) -> None:
        with self.lock:
            # The frame carries 16 bits of the counter; assume no wrap since
            # the last one, as a device would.
            high = (self.f_cnt_down + 1) >> 16 if self.f_cnt_down >= 0 else 0
            try:
                frame = lorawan.decode(phy, self.nwk_s_key, self.app_s_key, high)
            except (lorawan.MicError, ValueError) as err:
                print(f"[device] dropped downlink: {err}")
                return
            if frame.dev_addr != self.dev_addr:
                return  # someone else's
            if frame.f_cnt <= self.f_cnt_down:
                print(f"[device] dropped replayed downlink fCnt {frame.f_cnt}")
                return
            self.f_cnt_down = frame.f_cnt
            if frame.confirmed:
                self.ack_next = True
            self.save()

        kind = "confirmed" if frame.confirmed else "unconfirmed"
        print(f"[device] {kind} downlink fCnt {frame.f_cnt}, FPort {frame.f_port}: {frame.payload!r}")
        if frame.f_opts or frame.f_port == 0:
            mac = frame.f_opts or frame.payload
            print(f"[device] MAC commands (not answered by this mock): {mac.hex(' ')}")
        if frame.f_ctrl & lorawan.FCTRL_FPENDING:
            print("[device] the network has more downlinks queued")

    def save(self) -> None:
        with open(STATE_FILE, "w") as f:
            json.dump({"f_cnt_up": self.f_cnt_up, "f_cnt_down": self.f_cnt_down}, f)


class Gateway:
    def __init__(self, device: Device) -> None:
        self.device = device
        self.eui = bytes.fromhex(GATEWAY_ID)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.connect((BRIDGE_HOST, BRIDGE_PORT))
        self.stats = {"rxnb": 0, "rxok": 0, "rxfw": 0, "dwnb": 0, "txnb": 0}
        self.last_uplink_tmst = 0

    def send(self, identifier: int, body: dict | None = None, token: bytes | None = None) -> None:
        datagram = bytes([PROTOCOL_VERSION]) + (token or os.urandom(2)) + bytes([identifier])
        datagram += self.eui
        if body is not None:
            datagram += json.dumps(body).encode()
        self.sock.send(datagram)

    def forward_uplink(self, phy: bytes) -> None:
        """Hand a received frame to the network server as an rxpk.

        The gateway does not decrypt or check anything. It reports what it
        heard and how: frequency, data rate, signal quality and its own
        microsecond counter, which the network uses to time the reply.
        """
        tmst = concentrator_time()
        self.last_uplink_tmst = tmst
        rxpk = {
            "tmst": tmst,
            "time": datetime.now(timezone.utc).isoformat(),
            "chan": 0,
            "rfch": 0,
            "freq": FREQUENCY_MHZ,
            "stat": 1,  # CRC OK
            "modu": "LORA",
            "datr": DATA_RATE,
            "codr": "4/5",
            "rssi": -95,
            "lsnr": 5.5,
            "size": len(phy),
            "data": base64.b64encode(phy).decode(),
        }
        self.stats["rxnb"] += 1
        self.stats["rxok"] += 1
        self.stats["rxfw"] += 1
        self.send(PUSH_DATA, {"rxpk": [rxpk]})

    def receive_loop(self) -> None:
        while True:
            datagram = self.sock.recv(65535)
            if len(datagram) < 4 or datagram[0] != PROTOCOL_VERSION:
                continue
            token, identifier = datagram[1:3], datagram[3]
            if identifier == PULL_RESP:
                self.handle_pull_resp(token, json.loads(datagram[4:])["txpk"])
            elif identifier not in (PUSH_ACK, PULL_ACK):
                print(f"[gateway] unexpected identifier {identifier}")

    def handle_pull_resp(self, token: bytes, txpk: dict) -> None:
        """A downlink to transmit at a given time.

        The network sends it ahead of time with a concentrator timestamp to
        transmit at; the gateway queues it and confirms with TX_ACK.
        """
        self.stats["dwnb"] += 1
        self.send(TX_ACK, {"txpk_ack": {"error": "NONE"}}, token=token)

        phy = base64.b64decode(txpk["data"])
        when = "now" if txpk.get("imme") else self.describe_timing(txpk["tmst"])
        print(
            f"[gateway] downlink {txpk['freq']} MHz {txpk['datr']} {when}, "
            f"PHYPayload {phy.hex(' ')}"
        )
        delay_s = 0 if txpk.get("imme") else max(0, (txpk["tmst"] - concentrator_time()) & 0xFFFFFFFF) / 1e6
        if delay_s > 10:  # counter wrapped or a stale timestamp
            delay_s = 0
        threading.Timer(delay_s, self.transmit, args=(phy,)).start()

    def describe_timing(self, tmst: int) -> str:
        after = ((tmst - self.last_uplink_tmst) & 0xFFFFFFFF) / 1e6
        return f"at uplink + {after:.3f} s"

    def transmit(self, phy: bytes) -> None:
        self.stats["txnb"] += 1
        self.device.receive(phy)

    def keepalive_loop(self) -> None:
        last_stat = 0.0
        while True:
            self.send(PULL_DATA)
            if time.monotonic() - last_stat >= STAT_INTERVAL_S:
                last_stat = time.monotonic()
                self.send(PUSH_DATA, {"stat": self.stat()})
            time.sleep(PULL_INTERVAL_S)

    def stat(self) -> dict:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S GMT")
        return {"time": now, "ackr": 100.0, **self.stats}


def concentrator_time() -> int:
    """The concentrator's free-running microsecond counter (32 bits)."""
    return (time.monotonic_ns() // 1000) & 0xFFFFFFFF


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def main() -> None:
    device = Device()
    gateway = Gateway(device)
    print(f"[gateway] {GATEWAY_ID} forwarding to {BRIDGE_HOST}:{BRIDGE_PORT}/udp")
    print(f"[device] DevAddr {DEV_ADDR}, next fCnt {device.f_cnt_up}")

    threading.Thread(target=gateway.receive_loop, daemon=True).start()
    threading.Thread(target=gateway.keepalive_loop, daemon=True).start()
    time.sleep(1)  # let the first PULL_DATA through so downlinks have a route

    try:
        for counter in itertools.count(1):
            gateway.forward_uplink(device.uplink(f"hello #{counter}".encode()))
            time.sleep(UPLINK_INTERVAL_S)
    except KeyboardInterrupt:
        print("\n[gateway] stopping")


if __name__ == "__main__":
    main()
