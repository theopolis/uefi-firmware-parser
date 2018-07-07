#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This script finds the compressed data embedded in a Dell BIOS update program
# and decompresses it to an apparent HDR file. The main data seems to start
# at offset 0x58 in the HDR FWIW

import zlib
import sys
import re
import binascii

import os
import argparse

# The 0x789C at the end is the zlib header.
# It's necessary to check for that too because the string
# appears a couple times in the file.
HDR_PATTERN = re.compile(
    r'.{4}\xAA\xEE\xAA\x76\x1B\xEC\xBB\x20\xF1\xE6\x51.{1}\x78\x9C')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Extract Dell firmware update (HDR) from packaged PE.")
    parser.add_argument(
        '-o', '--output', default=None,
        help="Filename to write extracted HDR update.")
    parser.add_argument("file", help="The file to work on.")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print("Error: cannot open (%s)." % args.file)
        exit(1)

    with open(args.file, 'r') as fh:
        data = fh.read()

    # Once you find that string, the first 4 bytes are the little endian
    # size of the compressed data. The span will give you the starting
    # offset into the file where it is found
    match = HDR_PATTERN.search(data)
    if match is None:
        print("Failed: No Zlib header/footer found.")
        sys.exit(1)
    (start, stop) = match.span()

    # Now switch the order around since it's little endian
    # and also convert it to a hex string
    length = data[start:stop + 4]
    length = binascii.b2a_hex(length[::-1])
    # and then make it a proper number (separate lines for clarity)
    length = int(length, 16)

    hdr_data = data[start + 16:start + 16 + length]
    hdr_data = zlib.decompress(hdr_data)

    name = "%s.hdr" % args.file if args.output is None else args.output
    with open(name, 'wb') as fh:
        fh.write(hdr_data)
    print("Decompressed HDR and wrote output to (%s)." % name)
