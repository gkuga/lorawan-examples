"""LoRaWAN 1.0.x frames: join, then data. Build, parse, encrypt and sign.

Just enough of the LoRaWAN 1.0.3 specification (sections 4 and 6) for an
OTAA device. Joining (6.2):

    JoinRequest = MHDR | AppEUI (8, LE) | DevEUI (8, LE) | DevNonce (2, LE) | MIC
    JoinAccept  = MHDR | AppNonce (3) | NetID (3) | DevAddr (4, LE)
                       | DLSettings | RxDelay | [CFList (16)] | MIC

Both are signed with AppKey, and the accept is also encrypted with it. The
session keys are then derived from AppKey and the nonces of both sides, so
every join gives a fresh pair. Data frames after that:

    PHYPayload = MHDR | MACPayload | MIC
    MACPayload = FHDR | FPort | FRMPayload
    FHDR       = DevAddr (4, LE) | FCtrl (1) | FCnt (2, LE) | FOpts (0..15)

- FRMPayload is encrypted with AppSKey (or NwkSKey when FPort is 0) by XORing
  it with an AES-128 keystream.
- The MIC is the first 4 bytes of AES-CMAC(NwkSKey, B0 | MHDR..FRMPayload).

Both blocks fold in the direction, DevAddr and the full 32-bit frame counter,
of which only the low 16 bits travel in the frame.
"""

from dataclasses import dataclass, field

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC

JOIN_REQUEST = 0b000
JOIN_ACCEPT = 0b001
UNCONFIRMED_UP = 0b010
UNCONFIRMED_DOWN = 0b011
CONFIRMED_UP = 0b100
CONFIRMED_DOWN = 0b101

UPLINK = 0
DOWNLINK = 1

# FCtrl bits, uplink and downlink alike for the ones used here.
FCTRL_ADR = 0x80
FCTRL_ACK = 0x20
FCTRL_FPENDING = 0x10  # downlink only: more is waiting in the queue


class MicError(Exception):
    pass


@dataclass
class DataFrame:
    mtype: int
    dev_addr: bytes  # big-endian, as written in hex: 00189440
    f_ctrl: int
    f_cnt: int  # the full 32-bit counter; the frame carries the low 16 bits
    f_port: int | None
    payload: bytes = b""  # plaintext FRMPayload
    f_opts: bytes = field(default=b"")

    @property
    def direction(self) -> int:
        return UPLINK if self.mtype in (UNCONFIRMED_UP, CONFIRMED_UP) else DOWNLINK

    @property
    def confirmed(self) -> bool:
        return self.mtype in (CONFIRMED_UP, CONFIRMED_DOWN)


def encode(frame: DataFrame, nwk_s_key: bytes, app_s_key: bytes) -> bytes:
    """Build a PHYPayload, encrypting FRMPayload and appending the MIC."""
    msg = bytes([frame.mtype << 5])
    msg += frame.dev_addr[::-1]  # DevAddr travels little-endian
    msg += bytes([frame.f_ctrl | len(frame.f_opts)])
    msg += (frame.f_cnt & 0xFFFF).to_bytes(2, "little")
    msg += frame.f_opts
    if frame.f_port is not None:
        key = nwk_s_key if frame.f_port == 0 else app_s_key
        msg += bytes([frame.f_port])
        msg += crypt(key, frame.direction, frame.dev_addr, frame.f_cnt, frame.payload)
    return msg + mic(nwk_s_key, frame.direction, frame.dev_addr, frame.f_cnt, msg)


def decode(phy: bytes, nwk_s_key: bytes, app_s_key: bytes, f_cnt_high: int = 0) -> DataFrame:
    """Parse a PHYPayload, check its MIC and decrypt FRMPayload.

    `f_cnt_high` supplies the upper 16 bits of the frame counter, which the
    receiver has to know because the frame does not carry them.
    """
    if len(phy) < 12:
        raise ValueError(f"too short for a data frame: {phy.hex()}")
    mtype = phy[0] >> 5
    msg, received_mic = phy[:-4], phy[-4:]
    dev_addr = msg[1:5][::-1]
    f_ctrl = msg[5]
    f_opts_len = f_ctrl & 0x0F
    f_cnt = (f_cnt_high << 16) | int.from_bytes(msg[6:8], "little")
    f_opts = msg[8 : 8 + f_opts_len]
    rest = msg[8 + f_opts_len :]

    direction = UPLINK if mtype in (UNCONFIRMED_UP, CONFIRMED_UP) else DOWNLINK
    if mic(nwk_s_key, direction, dev_addr, f_cnt, msg) != received_mic:
        raise MicError(f"MIC mismatch for {phy.hex()}")

    f_port, payload = None, b""
    if rest:
        f_port = rest[0]
        key = nwk_s_key if f_port == 0 else app_s_key
        payload = crypt(key, direction, dev_addr, f_cnt, rest[1:])
    return DataFrame(mtype, dev_addr, f_ctrl & 0xF0, f_cnt, f_port, payload, f_opts)


@dataclass
class Session:
    """What a join produces: an address and two fresh session keys."""

    dev_addr: bytes
    nwk_s_key: bytes
    app_s_key: bytes
    rx1_dr_offset: int
    rx2_dr: int
    rx1_delay_s: int
    cf_list: bytes


def join_request(app_key: bytes, app_eui: bytes, dev_eui: bytes, dev_nonce: bytes) -> bytes:
    msg = bytes([JOIN_REQUEST << 5]) + app_eui[::-1] + dev_eui[::-1] + dev_nonce[::-1]
    return msg + cmac(app_key, msg)


def join_accept(phy: bytes, app_key: bytes, dev_nonce: bytes) -> Session:
    """Decrypt and check a JoinAccept, then derive the session keys.

    The network encrypts the accept with AES *decryption*, so that the device
    only needs the cheaper encryption direction to undo it.
    """
    if phy[0] >> 5 != JOIN_ACCEPT or len(phy) not in (17, 33):
        raise ValueError(f"not a join accept: {phy.hex()}")
    aes = Cipher(algorithms.AES(app_key), modes.ECB()).encryptor()
    plain = phy[:1] + aes.update(phy[1:])
    msg, received_mic = plain[:-4], plain[-4:]
    if cmac(app_key, msg) != received_mic:
        raise MicError(f"join accept MIC mismatch for {phy.hex()}")

    app_nonce, net_id = msg[1:4], msg[4:7]
    dev_addr = msg[7:11][::-1]
    dl_settings, rx_delay = msg[11], msg[12]

    def derive(prefix: int) -> bytes:
        block = bytes([prefix]) + app_nonce + net_id + dev_nonce[::-1]
        return aes.update(block.ljust(16, b"\0"))

    return Session(
        dev_addr=dev_addr,
        nwk_s_key=derive(0x01),
        app_s_key=derive(0x02),
        rx1_dr_offset=(dl_settings >> 4) & 0x07,
        rx2_dr=dl_settings & 0x0F,
        rx1_delay_s=rx_delay or 1,
        cf_list=msg[13:],
    )


def cmac(key: bytes, msg: bytes) -> bytes:
    c = CMAC(algorithms.AES(key))
    c.update(msg)
    return c.finalize()[:4]


def crypt(key: bytes, direction: int, dev_addr: bytes, f_cnt: int, data: bytes) -> bytes:
    """Encrypt or decrypt FRMPayload; XOR with the keystream works both ways."""
    aes = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    stream = b""
    for i in range(1, len(data) // 16 + 2):
        stream += aes.update(block(0x01, direction, dev_addr, f_cnt, i))
    return bytes(a ^ b for a, b in zip(data, stream))


def mic(nwk_s_key: bytes, direction: int, dev_addr: bytes, f_cnt: int, msg: bytes) -> bytes:
    return cmac(nwk_s_key, block(0x49, direction, dev_addr, f_cnt, len(msg)) + msg)


def block(first: int, direction: int, dev_addr: bytes, f_cnt: int, last: int) -> bytes:
    """The A_i (0x01) and B0 (0x49) blocks of the specification."""
    return (
        bytes([first, 0, 0, 0, 0, direction])
        + dev_addr[::-1]
        + f_cnt.to_bytes(4, "little")
        + bytes([0, last])
    )
