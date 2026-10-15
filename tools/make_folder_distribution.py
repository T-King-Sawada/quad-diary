"""Convert this unsigned PyInstaller onefile release into a folder distribution.

Reuse its bundled dependencies and Python version; keep the input untouched.
Usage: python tools/make_folder_distribution.py INPUT.exe NEW_OUTPUT_DIRECTORY
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PureWindowsPath
import struct
import sys
import zlib

COOKIE = struct.Struct("!8sIIII64s")
ENTRY = struct.Struct("!IIIIBc")
MAGIC = b"MEI\014\013\012\013\016"


def convert(source: Path, destination: Path) -> None:
    data = source.read_bytes()
    cookie_at = data.rfind(MAGIC)
    if cookie_at < 0:
        raise ValueError("PyInstaller archive not found")
    magic, size, toc_offset, toc_size, version, library = COOKIE.unpack_from(data, cookie_at)
    if cookie_at + COOKIE.size != len(data):
        raise ValueError("Signed or trailing-data executables are not supported")
    start = cookie_at + COOKIE.size - size
    toc = data[start + toc_offset : start + toc_offset + toc_size]
    extracted = []
    retained = []
    position = 0
    while position < len(toc):
        length, offset, packed, unpacked, compressed, kind = ENTRY.unpack_from(toc, position)
        if length < ENTRY.size or position + length > len(toc):
            raise ValueError("Invalid archive entry")
        name_bytes = toc[position + ENTRY.size : position + length]
        name = name_bytes.rstrip(b"\0").decode("utf-8")
        payload = data[start + offset : start + offset + packed]
        if len(payload) != packed or offset + packed > toc_offset:
            raise ValueError("Invalid archive payload")
        if kind in (b"b", b"x"):
            relative = PureWindowsPath(name)
            if relative.is_absolute() or relative.drive or ".." in relative.parts:
                raise ValueError("Unsafe archive path")
            content = zlib.decompress(payload) if compressed else payload
            if len(content) != unpacked:
                raise ValueError("Incorrect uncompressed size")
            extracted.append((relative, content))
        elif kind in (b"m", b"M", b"s", b"z", b"o"):
            if kind == b"o" and name != "pyi-contents-directory _internal":
                raise ValueError("Unsupported runtime option: " + name)
            retained.append((length, packed, unpacked, compressed, kind, name_bytes, payload))
        else:
            raise ValueError("Unsupported archive type: " + repr(kind))
        position += length
    destination.mkdir(parents=True, exist_ok=False)
    for relative, content in extracted:
        target = destination / "_internal" / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(content).digest():
            raise ValueError("Extracted file verification failed")
    payloads = bytearray()
    new_toc = bytearray()
    for length, packed, unpacked, compressed, kind, name_bytes, payload in retained:
        new_toc.extend(ENTRY.pack(length, len(payloads), packed, unpacked, compressed, kind))
        new_toc.extend(name_bytes)
        payloads.extend(payload)
    new_cookie = COOKIE.pack(magic, len(payloads) + len(new_toc) + COOKIE.size,
                             len(payloads), len(new_toc), version, library)
    output = destination / source.name
    output.write_bytes(data[:start] + payloads + new_toc + new_cookie)
    print(f"Created {output}: {len(extracted)} verified dependency files; Python {version}.")
    print("Input executable preserved. Launch validation still required.")


if __name__ == "__main__":
    convert(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
