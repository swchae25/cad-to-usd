import zlib

from cad_to_usd.container import read_streams, swap_nibbles
from synthetic import record


def test_swap_nibbles_is_its_own_inverse():
    data = bytes(range(256))
    assert swap_nibbles(swap_nibbles(data)) == data
    assert swap_nibbles(b"\x12") == b"\x21"


def test_reads_valid_streams():
    blob = b"\x00" * 7 + record("Contents/A", b"hello" * 20) + record("Contents/B", b"world")
    streams = read_streams(blob)
    assert streams == {"Contents/A": b"hello" * 20, "Contents/B": b"world"}


def test_rejects_corrupted_crc():
    rec = bytearray(record("Contents/A", b"payload"))
    rec[14:18] = (zlib.crc32(b"payload") ^ 1).to_bytes(4, "little")
    assert read_streams(bytes(rec)) == {}


def test_ignores_truncated_record():
    rec = record("Contents/A", b"payload" * 100)
    assert read_streams(rec[:-5]) == {}
