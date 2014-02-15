# -*- coding: utf-8 -*-

import argparse
import struct

def ascii_char(c):
    if ord(c) >= 32 and ord(c) <= 126: return c
    return '.'

def hex_dump(data, size= 16):
    def print_line(line):
        print "%s | %s" % (line.encode("hex"), "".join([ascii_char(c) for c in line]))

    for i in xrange(0, len(data)/size):
        data_line = data[i*size:i*size + size]
        print_line(data_line)
    
    if not len(data) % size == 0:
        print_line(data[(len(data) % size) * -1:])

class PFSFile(object):
    PFS_HEADER = "PFS.HDR."
    PFS_FOOTER = "PFS.FTR."

    def __init__(self, data):
        self.data = data

    def check_header(self):
        if len(self.data) < 32:
            return False

        hdr = self.data[:32]
        magic, spec, size = struct.unpack("<8sII16s", hdr)

        if magic != self.PFS_HEADER:
            return False
        return True

    def parse_chunks(self):
        """Chunks are assumed to contain a chunk header."""
        data = self.data[32:]

        while True:
            spec, ts, ctype, version, _u1 = struct.unpack("<IIhhI", data[:16])
            _u2, csize, size1, size2, size3 = struct.unpack("<8sIIII", data[16:16+24])
            crc = data[16+24:16+24+16]

            print "Spec (%d), TS (%d), Type (%d), Version (%d), U1 (%d)" % (spec, ts, ctype, version, _u1)
            print "U2 (0x%s)" % _u2.encode("hex")
            print "Size (%d) S1 (%d) S2 (%d) S3 (%d)" % (csize, size1, size2, size3)
            print "CRC (0x%s)" % crc.encode("hex")

            chunk_data = data[56:56+csize]

            # Not yet sure what the following three partitions are
            chunk1 = data[56+csize:56+csize+size1]
            chunk2 = data[56+csize+size1:56+csize+size1+size2]
            chunk3 = data[56+csize+size1+size2:56+csize+size1+size2+size3]
            
            total_chunk_size = csize+size1+size2+size3
            chunk_ftr = data[56+total_chunk_size:56+total_chunk_size+16]

            hex_dump(chunk_ftr)

            _u3, _u4 = struct.unpack("<12sI", chunk_ftr)
            print "U3 (0x%s) U4 (%d)" % (_u3.encode("hex"), _u4)

            data = data[56+16+total_chunk_size:]

            break

        t_chunk = data[:56]

        hex_dump(t_chunk)


        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Parse a Dell PFS update.")
    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()
    
    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)
        
    pfs = PFSFile(input_data)
    if not pfs.check_header(): sys.exit(1)

    pfs.parse_chunks()