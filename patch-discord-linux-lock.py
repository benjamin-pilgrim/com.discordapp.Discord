#!/usr/bin/env python3

import argparse
import json
import os
import struct
import sys
from copy import deepcopy


TARGET = "bundle.js"
MARKER = "__discordLinuxLockBridgeLoaded"
ANCHOR = "electron.ipcMain.handle(POWER_MONITOR_GET_SYSTEM_IDLE_TIME"
BRIDGE = r'''(()=>{if("linux"!==process.platform||global.__discordLinuxLockBridgeLoaded)return;global.__discordLinuxLockBridgeLoaded=!0;let{execFile,spawn}=__webpack_require__(5317),dest="org.freedesktop.login1",mgrPath="/org/freedesktop/login1",mgrIface="org.freedesktop.login1.Manager",sessIface="org.freedesktop.login1.Session",debug="1"===process.env.DISCORD_LINUX_LOCK_DEBUG,last=null,mon=null,timer=null;function log(){debug&&console.error("[discord-linux-lock]",...arguments)}function sessions(out){let ret=[],re=/\('([^']+)',\s*(?:uint32\s+)?(\d+),\s*'([^']*)',\s*'([^']*)',\s*(?:objectpath\s+)?'([^']+)'\)/g,m;for(;null!=(m=re.exec(out));)ret.push({id:m[1],uid:Number(m[2]),user:m[3],seat:m[4],path:m[5]});return ret}function pick(all){let uid="function"==typeof process.getuid?process.getuid():null,sid=process.env.XDG_SESSION_ID,mine=null==uid?all:all.filter(s=>s.uid===uid);return mine.find(s=>sid&&s.id===sid)||mine.find(s=>s.seat)||mine[0]||all.find(s=>s.seat)||all[0]||null}function emit(locked){last!==locked&&(last=locked,log("send",locked?"lock-screen":"unlock-screen"),sendToAllWindows(locked?POWER_MONITOR_LOCK_SCREEN:POWER_MONITOR_UNLOCK_SCREEN))}function out(buf){let text=String(buf);text.includes(sessIface+".Lock")?emit(!0):text.includes(sessIface+".Unlock")?emit(!1):text.includes("LockedHint")&&text.includes("true")?emit(!0):text.includes("LockedHint")&&text.includes("false")&&emit(!1)}function retry(){null==timer&&(timer=setTimeout(()=>{timer=null,start()},1e4),timer.unref())}function monitor(path){mon=spawn("gdbus",["monitor","--system","--dest",dest,"--object-path",path],{stdio:["ignore","pipe","pipe"]}),mon.stdout.on("data",out),mon.stderr.on("data",b=>log("monitor stderr:",String(b).trim())),mon.on("error",e=>{log("monitor error:",e.message),mon=null,retry()}),mon.on("exit",(c,s)=>{log("monitor exit:",c,s),mon=null,retry()}),mon.unref(),log("monitoring",path)}function start(){null==mon&&execFile("gdbus",["call","--system","--dest",dest,"--object-path",mgrPath,"--method",mgrIface+".ListSessions"],{timeout:5e3},(err,stdout)=>{if(err)return log("ListSessions failed:",err.message),void retry();let sess=pick(sessions(stdout));null!=sess&&sess.path?monitor(sess.path):(log("no login1 session found"),retry())})}log("loaded","pid="+process.pid),electron.app.whenReady().then(()=>{setTimeout(start,3e3).unref()})})();'''


def read_asar(path):
    with open(path, "rb") as f:
        header_size_size, header_block_size, json_block_size, json_size = struct.unpack("<IIII", f.read(16))
        if header_size_size != 4:
            raise ValueError("unexpected ASAR header prefix")
        header = json.loads(f.read(json_size))
        f.seek(8 + header_block_size)
        payload = f.read()
    return header, payload


def iter_files(node, prefix=""):
    for name, entry in node.get("files", {}).items():
        path = f"{prefix}/{name}" if prefix else name
        if "files" in entry:
            yield from iter_files(entry, path)
        else:
            yield path, entry


def get_entry(header, path):
    node = header
    for part in path.split("/"):
        node = node["files"][part]
    return node


def ensure_file_entry(header, path):
    node = header
    parts = path.split("/")
    for part in parts[:-1]:
        node = node.setdefault("files", {}).setdefault(part, {"files": {}})
    node.setdefault("files", {})[parts[-1]] = {}
    return node["files"][parts[-1]]


def file_bytes(payload, entry):
    offset = int(entry["offset"])
    size = int(entry["size"])
    return payload[offset:offset + size]


def patch_bundle(content):
    text = content.decode("utf-8")
    if MARKER in text:
        return content
    if ANCHOR not in text:
        raise ValueError("could not find power monitor anchor in bundle.js")
    text = text.replace(ANCHOR, BRIDGE + ANCHOR, 1)
    return text.encode("utf-8")


def pack_header(header):
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    padded_string_size = (len(raw) + 3) & ~3
    header_payload_size = 4 + padded_string_size
    header_buffer_size = 4 + header_payload_size
    padding = b"\0" * (padded_string_size - len(raw))
    return struct.pack("<IIII", 4, header_buffer_size, header_payload_size, len(raw)) + raw + padding


def patch_asar(asar_path):
    header, payload = read_asar(asar_path)
    original_header = deepcopy(header)

    files = {}
    for path, entry in iter_files(header):
        files[path] = file_bytes(payload, entry)

    files[TARGET] = patch_bundle(files[TARGET])

    new_payload = bytearray()
    for path in sorted(files):
        entry = ensure_file_entry(header, path)
        entry["offset"] = str(len(new_payload))
        entry["size"] = len(files[path])
        new_payload.extend(files[path])

    tmp_path = asar_path + ".linux-lock.tmp"
    with open(tmp_path, "wb") as f:
        f.write(pack_header(header))
        f.write(new_payload)
    os.replace(tmp_path, asar_path)

    return original_header != header


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asar")
    args = parser.parse_args()
    changed = patch_asar(args.asar)
    print("patched Discord Linux lock bridge" if changed else "Discord Linux lock bridge already present")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"patch-discord-linux-lock: {exc}", file=sys.stderr)
        raise
