#!/usr/bin/env python3
"""Rebuild a long Voice capture recording from the pieces in Drive's "Parts" folder.

    join_parts.py OUT.m4a PART [PART ...] [--sha256 HEX]

Parts can be given in any order: they are sorted by the sequence number of their first
MP4 fragment. Each part is the original's header (ftyp + moov) plus a run of whole
fragments, so the original is part 1 followed by every later part without its header.
The result is checked against the SHA-256 the recorder wrote into each part's
description (pass it with --sha256); a mismatch exits with an error.
"""
import argparse, hashlib, struct, sys


def boxes(d):
    off, out = 0, []
    while off < len(d):
        if off + 8 > len(d):
            raise ValueError("truncated box header")
        size, typ = struct.unpack(">I4s", d[off:off + 8])
        if size == 1:
            size = struct.unpack(">Q", d[off + 8:off + 16])[0]
        elif size == 0:
            size = len(d) - off
        if size < 8 or off + size > len(d):
            raise ValueError("bad box size")
        out.append((typ.decode("latin1"), off, off + size))
        off += size
    return out


def header_and_seq(d):
    bx = boxes(d)
    first = next(i for i, b in enumerate(bx) if b[0] == "moof")
    moof = bx[first]
    seq = None
    inner = moof[1] + 8
    while inner < moof[2]:  # mfhd holds the fragment sequence number
        size, typ = struct.unpack(">I4s", d[inner:inner + 8])
        if typ == b"mfhd":
            seq = struct.unpack(">I", d[inner + 12:inner + 16])[0]
            break
        inner += max(size, 8)
    return moof[1], seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--sha256")
    a = ap.parse_args()
    data = [open(p, "rb").read() for p in a.parts]
    info = [header_and_seq(d) for d in data]
    seqs = [s for _, s in info]
    order = list(range(len(data)))
    if None not in seqs and len(set(seqs)) == len(seqs):
        order.sort(key=lambda i: seqs[i])
    else:
        print("note: fragment numbers missing or repeated; keeping the order given", file=sys.stderr)
    h0 = info[order[0]][0]
    head = data[order[0]][:h0]
    for i in order[1:]:
        if data[i][:info[i][0]] != head:
            sys.exit(f"{a.parts[i]} has a different header; it isn't from the same recording")
    joined = data[order[0]] + b"".join(data[i][info[i][0]:] for i in order[1:])
    digest = hashlib.sha256(joined).hexdigest()
    if a.sha256 and digest != a.sha256.lower():
        sys.exit(f"SHA-256 mismatch: got {digest}, expected {a.sha256}")
    open(a.out, "wb").write(joined)
    print(f"wrote {a.out}  {len(joined)} bytes from {len(data)} parts  sha256 {digest}" + ("  (verified)" if a.sha256 else ""))


if __name__ == "__main__":
    main()
