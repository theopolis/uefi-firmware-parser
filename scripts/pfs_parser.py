# -*- coding: utf-8 -*-

# Dell PFS Firmware Update Parser
# Copyright Teddy Reed (teddy@prosauce.org)
#
# This script attempts to parse a DELL HDR file (BIOS/UEFI update).
# Newer versions of the DELL HDR format (see contrib script for extracting 
# from an update executable) use a PFS.HDR. magic value. The data seems to 
# have packed sections, the first of which contains a UEFI Firmware Volume. 
# By analyzing update sets, latter updates contain details/binary following
# each chunk. 

import argparse
import hashlib

import struct
import sys
import os

from uefi_firmware import fguid, dump_data

class PFSSection(object):
    def __init__(self, data):
        self.data = data
        self.size = -1

    def parse(self):
        self.uuid = self.data[:16]

        # Spec seems to be a consistent 1, what I thought was a timestamp is not.
        # Version is static except for the first section in a PFS
        spec, ts, ctype, version, _u1 = struct.unpack("<IIhh4s", self.data[16:32])
        # U1, U2 might be flag containers
        _u2, csize, size1, size2, size3 = struct.unpack("<8sIIII", self.data[32:32+24])

        self.spec = spec
        self.ts = ts
        self.type = ctype
        self.version = version

        # This seems to be a set of 8byte CRCs for each chunk (4 total)
        self.crcs = self.data[32+24:32+24+16]
        self.chunk_data = self.data[64:64+csize]

        # Not yet sure what the following three partitions are
        self.chunk1 = self.data[64+csize:64+csize+size1]
        self.chunk2 = self.data[64+csize+size1:64+csize+size1+size2]
        self.chunk3 = self.data[64+csize+size1+size2:64+csize+size1+size2+size3]
        
        total_chunk_size = csize+size1+size2+size3

        # Unknown 8byte variable
        _u3 = self.data[64+total_chunk_size:64+total_chunk_size+8]
        self.unknowns = [_u1, _u2, _u3]

        # Size of header, data, and footer
        self.section_size = 64+ total_chunk_size+8
        self.data = None

        pass

    def showinfo(self):
        print "UUID: (%s)" % fguid(self.uuid)
        print "Spec (%d), TS (%d), Type (%d), Version (%d)" % (self.spec, self.ts, self.type, self.version)
        print "Size (%d) S1 (%d) S2 (%d) S3 (%d)" % (len(self.chunk_data), len(self.chunk1), len(self.chunk2), len(self.chunk3))
        print "CRCs (0x%s)" % self.crcs.encode("hex")
        print "MD5 (%s)" % hashlib.md5(self.chunk_data).hexdigest()

        print "Unknowns (%s)" % ", ".join([u.encode("hex") for u in self.unknowns])
        pass

    def dump(self):
        dump_data("%s.data" % fguid(self.uuid), self.chunk_data)
        if len(self.chunk1) > 0: dump_data("%s.c1" % fguid(self.uuid), self.chunk1)
        if len(self.chunk2) > 0: dump_data("%s.c2" % fguid(self.uuid), self.chunk2)
        if len(self.chunk3) > 0: dump_data("%s.c3" % fguid(self.uuid), self.chunk3)
        pass


class PFSFile(object):
    PFS_HEADER = "PFS.HDR."
    PFS_FOOTER = "PFS.FTR."

    def __init__(self, data):
        self.sections = []
        self.data = data

    def check_header(self):
        if len(self.data) < 32:
            print "Data does not contain a header."
            return False

        hdr = self.data[:16]
        magic, spec, size = struct.unpack("<8sII", hdr)

        if magic != self.PFS_HEADER:
            print "Data does not contain the header magic (%s)." % self.PFS_HEADER
            return False
        
        ftr = self.data[len(self.data)-16:]
        # U1 and U2 might be the same variable, a total CRC?
        _u1, _u2, ftr_magic = struct.unpack("<II8s", ftr)
        if ftr_magic != self.PFS_FOOTER:
            print "Data does not container the footer magic (%s)." % self.PFS_FOOTER
            return False

        return True

    def parse(self):
        """Chunks are assumed to contain a chunk header."""
        data = self.data[16:-16]

        chunk_num = 0
        while True:
            print "Chunk: %d, Remaining length: %d" % (chunk_num, len(data))

            section = PFSSection(data)
            section.parse()
            #section.showinfo()
            #section.dump()
            self.sections.append(section)

            chunk_num += 1
            data = data[section.section_size:]
            print ""

            if len(data) < 64:
              break

    def showinfo(self):
        for section in self.sections:
            section.showinfo()
    
    def dump(self):
        for section in self.sections:
            section.dump()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Parse a Dell PFS update.")
    parser.add_argument("-e", "--extract", action="store_true", default=False, help="Dump all PFS sections.")
    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()
    
    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)
        
    pfs = PFSFile(input_data)
    if not pfs.check_header():
      sys.exit(1)

    pfs.parse()
    pfs.showinfo()

    if args.extract:
      pfs.dump()