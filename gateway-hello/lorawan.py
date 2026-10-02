"""LoRaWAN 1.0.x data frames: build, parse, encrypt and sign.

Just enough of the LoRaWAN 1.0.3 specification (sections 4 and 6) for an
ABP-activated device:

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


def crypt(key: bytes, direction: int, dev_addr: bytes, f_cnt: int, data: bytes) -> bytes:
    """Encrypt or decrypt FRMPayload; XOR with the keystream works both ways."""
    aes = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    stream = b""
    for i in range(1, len(data) // 16 + 2):
        stream += aes.update(block(0x01, direction, dev_addr, f_cnt, i))
    return bytes(a ^ b for a, b in zip(data, stream))


def mic(nwk_s_key: bytes, direction: int, dev_addr: bytes, f_cnt: int, msg: bytes) -> bytes:
    cmac = CMAC(algorithms.AES(nwk_s_key))
    cmac.update(block(0x49, direction, dev_addr, f_cnt, len(msg)) + msg)
    return cmac.finalize()[:4]


def block(first: int, direction: int, dev_addr: bytes, f_cnt: int, last: int) -> bytes:
    """The A_i (0x01) and B0 (0x49) blocks of the specification."""
    return (
        bytes([first, 0, 0, 0, 0, direction])
        + dev_addr[::-1]
        + f_cnt.to_bytes(4, "little")
        + bytes([0, last])
    )
