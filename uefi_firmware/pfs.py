import struct
import os

from .base import FirmwareObject, RawObject, BaseObject
from .uefi import FirmwareVolume
from .utils import print_error, dump_data, sguid, green, blue

PFS_GUIDS = {
    "FIRMWARE_VOLUMES": "7ec6c2b0-3fe3-42a0-a316-22dd0517c1e8",
    "INTEL_ME":         "7439ed9e-70d3-4b65-9e33-1963a7ad3c37",
    "BIOS_ROMS_1":      "08e56a30-62ed-41c6-9240-b7455ee653d7",
    "BIOS_ROMS_2":      "492261e4-0659-424c-82b6-73274389e7a7"
}

class PFSSection(FirmwareObject, BaseObject):
    HEADER_SIZE = 72

    def __init__(self, data):
        self.data = data
        self.size = -1

        ### Store parsed objects (if any)
        self.section_objects = []

    def process(self):
        hdr = self.data[:self.HEADER_SIZE]
        self.uuid = hdr[:16]
        self.header = hdr

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
        self.section_data = self.data[self.HEADER_SIZE:self.HEADER_SIZE+csize]

        # Not yet sure what the following three partitions are
        self.chunk1 = RawObject(self.data[self.HEADER_SIZE+csize:self.HEADER_SIZE+csize+size1])
        self.chunk2 = RawObject(self.data[self.HEADER_SIZE+csize+size1:self.HEADER_SIZE+csize+size1+size2])
        self.chunk3 = RawObject(self.data[self.HEADER_SIZE+csize+size1+size2:self.HEADER_SIZE+csize+size1+size2+size3])
        
        total_chunk_size = csize+size1+size2+size3

        # Unknown 8byte variable
        #_u3 = self.data[64+total_chunk_size:64+total_chunk_size+8]
        self.unknowns = [_u1, _u2]

        # Size of header, data, and footer
        self.section_size = self.HEADER_SIZE + total_chunk_size
        self.data = None

        if sguid(self.uuid) == PFS_GUIDS["FIRMWARE_VOLUMES"]:
            ### This is a series of firmware volumes
            fv_offset = 0
            while fv_offset < len(self.section_data):
                fv = FirmwareVolume(self.section_data[fv_offset:], hex(fv_offset))
                if not fv.valid_header:
                    break
                fv.process()
                self.section_objects.append(fv)
                fv_offset += fv.size
            pass
        else:
            self.section_objects.append(RawObject(self.section_data))
        pass

    @property
    def objects(self):
        return self.section_objects + [self.chunk1, self.chunk2, self.chunk3]

    def info(self, include_content= False):
        return {
            "_self": self,
            "guid": sguid(self.uuid),
            "type": "PFSSection",
            "content": self.section_data if include_content else "",
            "attrs": {
                "type": self.type,
                "size": self.section_size,
                "crcs": self.crcs.encode("hex"),
                "unknowns": [u.encode("hex") for u in self.unknowns],
                "ts": self.ts,
                "version": self.version
            },
            "chunks": [self.chunk1, self.chunk2, self.chunk3] if include_content else []
        }
        pass

    def build(self, generate_checksum= False, debug= False):
        body = ""
        for sub_object in self.section_objects:
            body += sub_object.build(generate_checksum, debug= debug)
        return self.header + body + \
            self.chunk1.build(generate_checksum) + \
            self.chunk2.build(generate_checksum) + \
            self.chunk3.build(generate_checksum)
        pass

    def showinfo(self, ts='', index= None):
        print "%s%s %s spec %d ts %d type %d version %d size 0x%x (%d bytes)" % (
            ts, blue("Dell PFSSection:"), green(sguid(self.uuid)),
            self.spec, self.ts, self.type, self.version,
            self.section_size, self.section_size
        )

        #print "Size (%d) S1 (%d) S2 (%d) S3 (%d)" % (len(self.section_data), len(self.chunk1), len(self.chunk2), len(self.chunk3))
        #print "CRCs (0x%s)" % self.crcs.encode("hex")
        #print "Unknowns (%s)" % ", ".join([u.encode("hex") for u in self.unknowns])
        for sub_object in self.section_objects:
            sub_object.showinfo("%s  " % ts)
        pass

    def dump(self, parent= "", index= None):
        path = os.path.join(parent, "%s" % sguid(self.uuid))
        dump_data("%s.data" % path, self.section_data)

        ### Instead of calling dump on each chunk RawObject, dump with a better name.
        if len(self.chunk1.data) > 0: 
            dump_data("%s.c1" % path, self.chunk1.data)
        if len(self.chunk2.data) > 0: 
            dump_data("%s.c2" % path, self.chunk2.data)
        if len(self.chunk3.data) > 0: 
            dump_data("%s.c3" % path, self.chunk3.data)

        path = os.path.join(parent, "section-%s" % sguid(self.uuid))
        for sub_object in self.section_objects:
            sub_object.dump(path)
        pass

class PFSFile(FirmwareObject):
    PFS_HEADER = "PFS.HDR."
    PFS_FOOTER = "PFS.FTR."

    def __init__(self, data):
        self.sections = []
        self.data = data

    def check_header(self):
        if len(self.data) < 32:
            print_error("Data does not contain a header.")
            return False

        hdr = self.data[:16]
        magic, spec, size = struct.unpack("<8sII", hdr)

        self.spec = spec
        self.size = size

        if magic != self.PFS_HEADER:
            print_error("Data does not contain the header magic (%s)." % self.PFS_HEADER)
            return False
        
        ftr = self.data[len(self.data)-16:]
        # U1 and U2 might be the same variable, a total CRC?
        _u1, _u2, ftr_magic = struct.unpack("<II8s", ftr)
        if ftr_magic != self.PFS_FOOTER:
            print_error("Data does not container the footer magic (%s)." % self.PFS_FOOTER)
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

            chunk_num += 1
            offset += section.section_size
            data = data[section.section_size:]

            if len(data) < 64:
              break

    @property
    def objects(self):
        return self.sections

    def build(self, generate_checksum= False    , debug= False):
        body = ""
        for section in self.sections:
            body += section.build(generate_checksum, debug= debug)
        return self.data[:16] + body + self.data[-16:]
        pass

    def showinfo(self, ts= '', index= None):
        print "%s%s spec 0x%x size 0x%x (%d bytes)" % (
            ts, blue("DellPFS:"), 
            self.spec, self.size, self.size
        )
        for section in self.sections:
            section.showinfo("%s  " % ts)
    
    def dump(self, parent= '', index= None):
        path = os.path.join(parent, "pfsobject.pfs")
        dump_data(path, self.data)

        path = os.path.join(parent, "pfsobject")
        for section in self.sections:
            section.dump(path)

