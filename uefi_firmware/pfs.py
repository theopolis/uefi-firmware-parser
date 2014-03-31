import struct

from .utils import dump_data, fguid

PFS_GUIDS = {
    "FIRMWARE_VOLUMES": "7ec6c2b0-3fe3-42a0-16a3-22dd0517c1e8",
    "INTEL_ME":         "7439ed9e-70d3-4b65-339e-1963a7ad3c37",
    "BIOS_ROMS_1":      "08e56a30-62ed-41c6-4092-b7455ee653d7",
    "BIOS_ROMS_2":      "492261e4-0659-424c-b682-73274389e7a7"
}

class PFSSection(object):
    HEADER_SIZE = 72

    def __init__(self, data):
        self.data = data
        self.size = -1

    def process(self):
        hdr = self.data[:self.HEADER_SIZE]
        self.uuid = hdr[:16]

        # Spec seems to be a consistent 1, what I thought was a timestamp is not.
        # Version is static except for the first section in a PFS
        spec, ts, ctype, version, _u1 = struct.unpack("<IIhh4s", hdr[16:32])
        # U1, U2 might be flag containers
        _u2, csize, size1, size2, size3 = struct.unpack("<8sIIII", hdr[32:32+24])

        self.spec = spec
        self.ts = ts
        self.type = ctype
        self.version = version

        # This seems to be a set of 8byte CRCs for each chunk (4 total)
        self.crcs = hdr[32+24:self.HEADER_SIZE]
        self.chunk_data = self.data[self.HEADER_SIZE:self.HEADER_SIZE+csize]

        # Not yet sure what the following three partitions are
        self.chunk1 = self.data[self.HEADER_SIZE+csize:self.HEADER_SIZE+csize+size1]
        self.chunk2 = self.data[self.HEADER_SIZE+csize+size1:self.HEADER_SIZE+csize+size1+size2]
        self.chunk3 = self.data[self.HEADER_SIZE+csize+size1+size2:self.HEADER_SIZE+csize+size1+size2+size3]
        
        total_chunk_size = csize+size1+size2+size3

        # Unknown 8byte variable
        #_u3 = self.data[64+total_chunk_size:64+total_chunk_size+8]
        self.unknowns = [_u1, _u2]

        # Size of header, data, and footer
        self.section_size = self.HEADER_SIZE + total_chunk_size
        self.data = None

        pass

    def info(self, include_content= False):
        return {
            "_self": self,
            "guid": fguid(self.uuid),
            "type": "PFSSection",
            "content": self.chunk_data if include_content else "",
            "attrs": {
                "type": self.type,
                "size": len(self.chunk_data),
                "crcs": self.crcs.encode("hex"),
                "unknowns": [u.encode("hex") for u in self.unknowns],
                "ts": self.ts,
                "version": self.version
            },
            "chunks": [self.chunk1, self.chunk2, self.chunk3] if include_content else []
        }   

    def showinfo(self):
        print "UUID: (%s)" % fguid(self.uuid)
        print "Spec (%d), TS (%d), Type (%d), Version (%d)" % (self.spec, self.ts, self.type, self.version)
        print "Size (%d) S1 (%d) S2 (%d) S3 (%d)" % (len(self.chunk_data), len(self.chunk1), len(self.chunk2), len(self.chunk3))
        print "CRCs (0x%s)" % self.crcs.encode("hex")
        #print "MD5 (%s)" % hashlib.md5(self.chunk_data).hexdigest()

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

    def process(self):
        """Chunks are assumed to contain a chunk header."""
        data = self.data[16:-16]

        chunk_num = 0
        offset = 16
        while True:

            section = PFSSection(data)
            section.process()
            self.sections.append(section)
            #print "0x%X" % offset

            chunk_num += 1
            offset += section.section_size
            data = data[section.section_size:]

            if len(data) < 64:
              break

    @property
    def objects(self):
        return self.sections

    def showinfo(self):
        for section in self.sections:
            section.showinfo()
    
    def dump(self):
        for section in self.sections:
            section.dump()

