#!/usr/bin/env python3

import argparse
import json
import struct
import sys


TARGET = "bundle.js"
REQUIRED_MARKERS = (
    "__discordLinuxLockBridgeLoaded",
    "org.freedesktop.login1",
    "POWER_MONITOR_LOCK_SCREEN",
    "POWER_MONITOR_UNLOCK_SCREEN",
    "[discord-linux-lock]",
)


def read_asar_file(path, target):
    with open(path, "rb") as f:
        header_size_size, header_block_size, _json_block_size, json_size = struct.unpack(
            "<IIII", f.read(16)
        )
        if header_size_size != 4:
            raise ValueError("unexpected ASAR header prefix")

        header = json.loads(f.read(json_size))
        f.seek(8 + header_block_size)
        payload = f.read()

    node = header
    for part in target.split("/"):
        node = node["files"][part]

    offset = int(node["offset"])
    size = int(node["size"])
    return payload[offset : offset + size]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asar")
    args = parser.parse_args()

    bundle = read_asar_file(args.asar, TARGET).decode("utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in bundle]
    if missing:
        print("Linux lock bridge verification failed.", file=sys.stderr)
        for marker in missing:
            print(f"missing marker: {marker}", file=sys.stderr)
        return 1

    print("Linux lock bridge verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
