"""Repair a .mdlg recorded with the stale 172 B twin-packet size against
a runtime that sends 180 B packets: the byte stream was captured
losslessly but split at wrong boundaries. Concatenate the twin bytes in
order and re-slice at 180 B, preserving ToF records and interleaving."""
import struct, sys

src, dst = sys.argv[1], sys.argv[2]
HDR = struct.Struct("<4sIQ")
REC = struct.Struct("<QBI")
TWIN = 180

data = open(src, "rb").read()
magic, ver, epoch = HDR.unpack_from(data, 0)
assert magic == b"MDLG" and ver == 1
out = [data[:HDR.size]]
off = HDR.size
twin_buf = bytearray()
twin_ts = []          # arrival ts of each byte in twin_buf
n_tof = n_twin = 0
while off + REC.size <= len(data):
    ts, sid, size = REC.unpack_from(data, off)
    off += REC.size
    payload = data[off:off + size]
    if len(payload) < size:
        print(f"truncated final record dropped ({len(payload)}/{size} B)")
        break
    off += size
    if sid == 0:
        out.append(REC.pack(ts, 0, size) + payload)
        n_tof += 1
    else:
        twin_buf.extend(payload)
        twin_ts.extend([ts] * size)
        while len(twin_buf) >= TWIN:
            pkt = bytes(twin_buf[:TWIN]); pts = twin_ts[0]
            del twin_buf[:TWIN]; del twin_ts[:TWIN]
            out.append(REC.pack(pts, 1, TWIN) + pkt)
            n_twin += 1
if twin_buf:
    print(f"{len(twin_buf)} trailing twin bytes dropped (partial packet)")
open(dst, "wb").write(b"".join(out))
print(f"repaired: {n_tof} ToF + {n_twin} twin records -> {dst}")
