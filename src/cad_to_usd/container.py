"""Read the compressed streams stored inside a modern SOLIDWORKS file.

Modern .SLDPRT/.SLDASM files store their data as a series of zip-like
records whose stream names are nibble-swapped. Each record carries a CRC-32
and the uncompressed size, so every stream we return has been verified.

Format notes are based on independent interoperability research:
https://github.com/blussyya/sldprt-format-research
"""
from __future__ import annotations

import re
import struct
import zlib

# Marker that precedes each record header (version / flags / method fields).
RECORD_SIGNATURE = b"\x14\x00\x06\x00\x08\x00"
# Stream names are stored with the two nibbles of every byte swapped.
_NIBBLE_SWAP = bytes(((x & 0x0F) << 4) | (x >> 4) for x in range(256))
_MAX_STREAM_BYTES = 128 * 1024 * 1024


def swap_nibbles(data: bytes) -> bytes:
    """Swap the high and low nibble of every byte (the operation is its own inverse)."""
    return data.translate(_NIBBLE_SWAP)


def read_streams(data: bytes) -> dict[str, bytes]:
    """Return {stream name: decompressed bytes} for every valid record in a file.

    Records that fail any check (name, size, inflate, CRC) are skipped, so
    random byte patterns that happen to match the signature are ignored.
    The first valid copy of a stream name wins.
    """
    streams: dict[str, bytes] = {}
    for hit in re.finditer(re.escape(RECORD_SIGNATURE), data):
        header = hit.start() - 4
        if header < 0 or header + 30 > len(data):
            continue
        crc, csize, usize, name_len, extra_len = struct.unpack_from("<IIIHH", data, header + 14)
        if not 0 < name_len < 300 or csize == 0 or usize > _MAX_STREAM_BYTES:
            continue
        raw_name = swap_nibbles(data[header + 30 : header + 30 + name_len])
        if not all(32 <= c < 127 for c in raw_name):
            continue
        name = raw_name.decode("ascii")
        start = header + 30 + name_len + extra_len
        if start + csize > len(data):
            continue
        try:
            payload = zlib.decompress(data[start : start + csize], -15)
        except zlib.error:
            continue
        if len(payload) != usize or zlib.crc32(payload) != crc:
            continue
        streams.setdefault(name, payload)
    return streams
