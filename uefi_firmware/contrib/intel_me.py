# Intel ME ROM image dumper/extractor
# Copyright (c) 2012 Igor Skochinsky
# Version 0.1 2012-10-10
# Version 0.2 2013-08-15
#
# This software is provided 'as-is', without any express or implied
# warranty. In no event will the authors be held liable for any damages
# arising from the use of this software.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
#
#    1. The origin of this software must not be misrepresented; you must not
#    claim that you wrote the original software. If you use this software
#    in a product, an acknowledgment in the product documentation would be
#    appreciated but is not required.
#
#    2. Altered source versions must be plainly marked as such, and must not be
#    misrepresented as being the original software.
#
#    3. This notice may not be removed or altered from any source
#    distribution.
#
# Modified version 2013-12-29 Damien Zammit
# Modified version 2014-01-10 Teddy Reed

import ctypes
import struct
import sys
import os
import array
import itertools
from operator import itemgetter

from .intel_me_structs import *

class MeObject(object):
    """
    An ME Object is a combination of a parsing/extraction class and a ctype
    definding structure object. 

    This follows the same ctor, process, showinfo, dump calling convention.
    """

    def parse_structure(self, data, structure):
        '''Construct an instance object of the provided structure.'''
        struct_instance = structure()
        struct_size = ctypes.sizeof(struct_instance)

        struct_data = data[:struct_size]
        struct_length = min(len(struct_data), struct_size)
        ctypes.memmove(ctypes.addressof(struct_instance), struct_data, struct_length)
        self.structure = struct_instance
        self.fields = [field[0] for field in structure._fields_]

    def show_structure(self):
        for field in self.fields:
            print "%s: %s" % (field, getattr(self.structure, field, None))


class MeModuleHeader1(MeObject):
    def __init__(self):
        self.Offset = None

    def comptype(self):
        return COMP_TYPE_NOT_COMPRESSED

    def print_flags(self):
        print "    Disable Hash:   %d" % ((self.Flags>>0)&1)
        print "    Optional:       %d" % ((self.Flags>>1)&1)
        if self.Flags >> 2:
            print "    Unknown B2_31: %d" % ((self.Flags>>2))

    def pprint(self):
        print "Header tag:     %s" % (self.Tag)
        nm = self.Name.rstrip('\0')
        print "Module name:    %s" % (nm)
        print "Guid:           %s" % (" ".join("%02X" % v for v in self.Guid))
        print "Version:        %d.%d.%d.%d" % (self.MajorVersion, self.MinorVersion, self.HotfixVersion, self.BuildVersion)
        print "Hash:           %s" % (" ".join("%02X" % v for v in self.Hash))
        print "Size:           0x%08X" % (self.Size)
        if self.Offset != None:
            print "(Offset):       0x%08X" % (self.Offset)
        print "Flags:          0x%08X" % (self.Flags)
        self.print_flags()
        print "Unk48:          0x%08X" % (self.Unk48)
        print "Unk4C:          0x%08X" % (self.Unk4C)

class MeModuleFileHeader1(ctypes.LittleEndianStructure):
    _fields_ = [
        ("Tag",            char*4),   # $MOD
        ("Unk04",          uint32_t), #
        ("Unk08",          uint32_t), #
        ("MajorVersion",   uint16_t), #
        ("MinorVersion",   uint16_t), #
        ("HotfixVersion",  uint16_t), #
        ("BuildVersion",   uint16_t), #
        ("Unk14",          uint32_t), #
        ("CompressedSize", uint32_t), #
        ("UncompressedSize", uint32_t), #
        ("LoadAddress",    uint32_t), #
        ("MappedSize",     uint32_t), #
        ("Unk28",          uint32_t), #
        ("Unk2C",          uint32_t), #
        ("Name",           char*16),  #
        ("Guid",           uint8_t*16), #
    ]

    def pprint(self):
        print "Module tag:        %s" % (self.Tag)
        nm = self.Name.rstrip('\0')
        print "Module name:       %s" % (nm)
        print "Guid:              %s" % (" ".join("%02X" % v for v in self.Guid))
        print "Version:           %d.%d.%d.%d" % (self.MajorVersion, self.MinorVersion, self.HotfixVersion, self.BuildVersion)
        print "Unk04:             0x%08X" % (self.Unk04)
        print "Unk08:             0x%08X" % (self.Unk08)
        print "Unk14:             0x%08X" % (self.Unk14)
        print "Compressed size:   0x%08X" % (self.CompressedSize)
        print "Uncompressed size: 0x%08X" % (self.UncompressedSize)
        print "Mapped address:    0x%08X" % (self.LoadAddress)
        print "Mapped size:       0x%08X" % (self.MappedSize)
        print "Unk28:             0x%08X" % (self.Unk28)
        print "Unk2C:             0x%08X" % (self.Unk2C)

MeModulePowerTypes = ["POWER_TYPE_RESERVED", "POWER_TYPE_M0_ONLY", "POWER_TYPE_M3_ONLY", "POWER_TYPE_LIVE"]
MeCompressionTypes = ["COMP_TYPE_NOT_COMPRESSED", "COMP_TYPE_HUFFMAN", "COMP_TYPE_LZMA", "<unknown>"]
COMP_TYPE_NOT_COMPRESSED = 0
COMP_TYPE_HUFFMAN = 1
COMP_TYPE_LZMA = 2
MeModuleTypes      = ["DEFAULT", "PRE_ME_KERNEL", "VENOM_TPM", "APPS_QST_DT", "APPS_AMT", "TEST"]
MeApiTypes         = ["API_TYPE_DATA", "API_TYPE_ROMAPI", "API_TYPE_KERNEL", "<unknown>"]



class MeModuleHeader2(MeObject):
    def comptype(self):
        return (self.Flags>>4)&7

    def print_flags(self):
        print "    Unknown B0:     %d" % ((self.Flags>>0)&1)
        powtype = (self.Flags>>1)&3
        print "    Power Type:     %s (%d)" % (MeModulePowerTypes[powtype], powtype)
        print "    Unknown B3:     %d" % ((self.Flags>>3)&1)
        comptype = (self.Flags>>4)&7
        print "    Compression:    %s (%d)" % (MeCompressionTypes[comptype], comptype)
        modstage = (self.Flags>>7)&0xF
        if modstage < len(MeModuleTypes):
            smtype = MeModuleTypes[modstage]
        else:
            smtype = "STAGE %X" % modstage
        print "    Stage:          %s (%d)" % (smtype, modstage)
        apitype = (self.Flags>>11)&7
        print "    API Type:       %s (%d)" % (MeApiTypes[apitype], apitype)

        print "    Unknown B14:    %d" % ((self.Flags>>14)&1)
        print "    Unknown B15:    %d" % ((self.Flags>>15)&1)
        print "    Privileged:     %d" % ((self.Flags>>16)&1)
        print "    Unknown B17_19: %d" % ((self.Flags>>17)&7)
        print "    Unknown B20_21: %d" % ((self.Flags>>20)&3)
        if self.Flags >> 22:
            print "    Unknown B22_31: %d" % ((self.Flags>>22))

    def pprint(self):
        print "Header tag:     %s" % (self.Tag)
        nm = self.Name.rstrip('\0')
        print "Module name:    %s" % (nm)
        print "Hash:           %s" % (" ".join("%02X" % v for v in self.Hash))
        print "Unk34:          0x%08X" % (self.Unk34)
        print "Offset:         0x%08X" % (self.Offset)
        print "Unk3C:          0x%08X" % (self.Unk3C)
        print "Data length:    0x%08X" % (self.Size)
        print "Unk44:          0x%08X" % (self.Unk44)
        print "Unk48:          0x%08X" % (self.Unk48)
        print "LoadBase:       0x%08X" % (self.LoadBase)
        print "Flags:          0x%08X" % (self.Flags)
        self.print_flags()
        print "Unk54:          0x%08X" % (self.Unk54)
        print "Unk58:          0x%08X" % (self.Unk58)
        print "Unk5C:          0x%08X" % (self.Unk5C)


def extract_code_mods(nm, f, soff):
    try:
       os.mkdir(nm)
    except:
       pass
    os.chdir(nm)
    print " extracting CODE partition %s" % (nm)
    manif = get_struct(f, soff, MeManifestHeader)
    manif.parse_mods(f, soff)
    manif.pprint()
    manif.extract(f, soff)
    os.chdir("..")

class HuffmanOffsetBytes(ctypes.LittleEndianStructure):
    _fields_ = [
        ("Offset", uint32_t, 24),
        ("Length", uint8_t),
    ]

class HuffmanOffsets(ctypes.Union):
    _fields_ = [
        ("b", HuffmanOffsetBytes),
        ("asword", uint32_t),
    ]

class MeModule(MeObject):
    def __init__(self, data, structure_type):
        self.attrs = {}
        self.parse_structure(data, structure_type)
        self.structure_type = structure_type
        
        if structure_type == MeModuleHeader2Type:
            self.structure.Guid = "(none)"
            self.attrs["version"] = "0.0.0.0"
        elif structure_type == MeModuleHeader1Type:
            self.attrs["version"] = "%d.%d.%d.%d" % (self.structure.MajorVersion, self.structure.MinorVersion, self.structure.HotfixVersion, self.structure.BuildVersion)

        self.attrs["guid"] = self.structure.Guid
        self.attrs["name"] = self.structure.Name
        self.attrs["load_base"] = self.structure.LoadBase
        self.attrs["size"] = self.structure.Size
        self.attrs["tag"] = self.structure.Tag

        '''Parse flags and change output.'''
        self.attrs["flags"] = self.structure.Flags

        if structure_type == MeModuleHeader2Type:
            self.attrs["power_type"] = (self.structure.Flags>>1)&3 # MeModulePowerTypes
            self.attrs["compression"] = (self.structure.Flags>>4)&7 # MeCompressionTypes
            self.attrs["module_stage"] = (self.structure.Flags>>7)&0xF # MeModuleTypes (optional)
            self.attrs["api_type"] = (self.structure.Flags>>11)&7 # MeApiTypes
            self.attrs["privileged"] = ((self.structure.Flags>>16)&1)
        # There are unknown flags to parse, todo: revisit
        pass         

    @property
    def size(self):
        return ctypes.sizeof(self.structure_type)

    @property
    def compression(self):
        if self.structure_type == MeModuleHeader1Type:
            return COMP_TYPE_NOT_COMPRESSED
        else:
            return (self.structure.Flags>>4)&7

    def showinfo(self, ts=''):
        for attr in self.attrs:
            print "%s: %s" % (attr, self.attrs[attr])        

class MeVariableModule(MeObject):
    HEADER_SIZE = 8

    def __init__(self, data, structure_type):
        self.type = structure_type
        self.data = None
        self.size = 0

        hdr = data[:self.HEADER_SIZE]
        self.valid_header = True
        self.header_blank = False

        if hdr == '\xFF' * self.HEADER_SIZE:
            self.header_blank = True
            return

        if len(hdr) < self.HEADER_SIZE or hdr[0] != '$':
            print "Debug: invalid module header."
            #from ..utils import hex_dump
            #hex_dump(data[:64])
            self.valid_header = False
            return

        self.tag = hdr[:4]
        self.size = struct.unpack("<I", hdr[4:])[0]
        self.data = data[self.HEADER_SIZE:self.size*4]
        pass

    def add_update(self, tag, name, offset, size):
        pass

    def process(self):
        if self.tag == '$UDC':
            subtag, _hash, name, offset, size = struct.unpack(self.stype.udc_format, self.data[:self.type.udc_length])
            print "Debug: update code found: (%s) (%s), length: %d" % (subtag, name, size)
            self.add_update(subtag, name, offset, size)
        if self.size == 3:
            values = [struct.unpack("<I", self.data[:4])[0]]
        if self.size == 4:
            values = struct.unpack("<II", self.data[:8])[0]
        else:
            values = array.array("I", self.data)
        self.values = values
        pass


class MeManifestHeader(MeObject):
    _DATA_OFFSET = 12

    def __init__(self, data):
        self.attrs = {}
        self.parse_structure(data, MeManifestHeaderType)
        self.data = data[self.structure.HeaderLen*4 + self._DATA_OFFSET:]

        '''Set storage attributes.'''
        self.attrs["header_version"] = "%d.%d" % (self.structure.HeaderVersion>>16, self.structure.HeaderVersion&0xFFFF)
        self.attrs["version"] = "%d.%d.%d.%d" % (self.structure.MajorVersion, self.structure.MinorVersion, self.structure.HotfixVersion, self.structure.BuildVersion)
        self.attrs["flags"] = "0x%08X" % (self.structure.Flags)
        self.attrs["module_vendor"] = "0x%04X" % (self.structure.ModuleVendor)
        self.attrs["date"] = "%08X" % (self.structure.Date)

        '''Skipped.'''
        #ModuleType, ModuleSubType, size, tag, num_modules, keysize, scratchsize, rsa

        self.partition_name = self.structure.PartitionName.rstrip("\0")
        if not self.partition_name: self.partition_name = "(none)"

    def showinfo(self, ts=''):
        for attr in self.attrs:
            print "%s: %s" % (attr, self.attrs[attr])
        print "Partition Name: %s" % self.partition_name

    def process(self):
        self.modules = []

        if self.structure.Tag == '$MN2':
            print "...processing module header2"
            header_type = MeModuleHeader2Type
        elif self.structure.Tag == '$MAN':
            header_type = MeModuleHeader1Type
        else:
            '''Cannot parsing modules...'''
            return 

        module_offset = 0
        huffman_offset = 0

        ### Parse the module headers (two types of headers, specified by the manifest)
        for module_index in xrange(self.structure.NumModules):
            module = MeModule(self.data[module_offset:], header_type)
            if module.compression == COMP_TYPE_HUFFMAN:
                '''Todo: skipped precondition for huffman offsets.'''
                print "Debug: Setting huffman offset: %d" % module.structure.Offset
                self.huffman_offset = module.structure.Offset
            #module.showinfo()

            module_offset += module.size

        additional_header = self.structure.Size*4 - module_offset
        print "Debug: Remaining header: %d - %d = %d" % (self.structure.Size*4, module_offset, additional_header)

        partition_end = None
        while module_offset < self.structure.Size*4:
            '''There is more module header to process.'''
            module = MeVariableModule(self.data[module_offset:], header_type)
            if not module.valid_header:
                break

            module_offset += module.HEADER_SIZE
            if module.header_blank:
                continue

            print "Debug: found module (%s)." % module.tag
            module.process()
            if module.tag == '$MCP':
                partition_end = module.values[0] + module.values[1]

            module_offset += module.size

        pass

#class 

class OLDMANIFEST(object):
    def parse_mods(self, f, offset):
        self.modules = []
        self.updparts = []
        orig_off = offset
        offset += self.HeaderLen*4
        offset += 12
        if self.Tag == '$MN2':
            htype = MeModuleHeader2
            hdrlen = ctypes.sizeof(htype)
            udc_fmt = "<4s32s16sII"
            udc_len = 0x3C
        elif self.Tag == '$MAN':
            htype = MeModuleHeader1
            hdrlen = ctypes.sizeof(htype)
            udc_fmt = "<4s20s16sII"
            udc_len = 0x30
        else:
            raise Exception("Don't know how to parse modules for manifest tag %s!" % self.Tag)

        modmap = {}
        self.huff_start = 0
        for i in range(self.NumModules):
            mod = get_struct(f, offset, htype)
            if not [mod.Tag in '$MME', '$MDL']:
                raise Exception("Bad module tag (%s) at offset %08X!" % (mod.Tag, offset))
            nm = mod.Name.rstrip('\0')
            modmap[nm] = mod
            self.modules.append(mod)
            if mod.comptype() == COMP_TYPE_HUFFMAN:
                if self.huff_start and self.huff_start != orig_off + mod.Offset:
                    print "Warning: inconsistent start offset for Huffman modules!"
                self.huff_start = orig_off + mod.Offset
            offset += hdrlen

        self.partition_end = None
        hdr_end = orig_off + self.Size*4
        while offset < hdr_end:
            print "tags %08X" % offset
            hdr = f[offset:offset+8]
            if hdr == '\xFF' * 8:
                offset += hdrlen
                continue
            if len(hdr) < 8 or hdr[0] != '$':
                break
            tag, elen = hdr[:4], struct.unpack("<I", hdr[4:])[0]
            if elen == 0:
                break
            print "Tag: %s, data length: %08X (0x%08X bytes)" % (tag, elen, elen*4)
            if tag == '$UDC':
                subtag, hash, subname, suboff, size = struct.unpack(udc_fmt, f[offset+8:offset+8+udc_len])
                suboff += offset
                print "Update code part: %s, %s, offset %08X, size %08X" % (subtag, subname.rstrip('\0'), suboff, size)
                self.updparts.append((subtag, suboff, size))
            elif elen == 3:
                val = struct.unpack("<I", f[offset+8:offset+12])[0]
                print "%s: %08X" % (tag[1:], val)
            elif elen == 4:
                vals = struct.unpack("<II", f[offset+8:offset+16])
                print "%s: %08X %08X" % (tag[1:], vals[0], vals[1])
            else:
                vals = array.array("I", f[offset+8:offset+elen*4])
                print "%s: %s" % (tag[1:], " ".join("%08X" % v for v in vals))
                if tag == '$MCP':
                    self.partition_end = vals[0] + vals[1]
            offset += elen*4

        offset = hdr_end
        while True:
            print "mods %08X" % offset
            if f[offset:offset+4] != '$MOD':
                break
            mfhdr = get_struct(f, offset, MeModuleFileHeader1)
            mfhdr.pprint()
            nm = mfhdr.Name.rstrip('\0')
            mod = modmap[nm]
            mod.Offset = offset - orig_off
            mod.UncompressedSize = mfhdr.UncompressedSize
            offset += mod.Size
        
        # check for huffman LUT
        offset = self.huff_start
        self.chunksize = 0
        self.chunkcount = 0
        self.datalen = 0
        self.datastart = 0
        self.llutlen = 0
        if f[offset:offset+4] == 'LLUT':
            self.chunkcount, decompbase, unk0c, self.datalen, self.datastart, a,b,c,d,e,f, self.chunksize = struct.unpack("<IIIIIIIIIIII", f[offset+4:offset+52])
            self.huff_end = self.datastart + self.datalen
        else:
            self.huff_start = 0xFFFFFFFF
            self.huff_end = 0xFFFFFFFF

    def extract(self, f, offset):
        huff_end = self.huff_end
        nhuffs = 0
        for mod in self.modules:
            if mod.comptype() != COMP_TYPE_HUFFMAN:
                huff_end = min(huff_end, mod.Offset)
            else:
                print "Huffman module data:  %r %08X/%08X" % (mod.Name.rstrip('\0'), self.datastart, self.datalen)
                nhuffs += 1
        for imod in range(len(self.modules)):
            mod = self.modules[imod]
            nm = mod.Name.rstrip('\0')
            islast = (imod == len(self.modules)-1)
            print "Module:      %r %08X" % (nm, mod.Size),
            if mod.Offset in [0xFFFFFFFF, 0] or (mod.Size in [0xFFFFFFFF, 0] and not islast and mod.comptype() != COMP_TYPE_HUFFMAN):
                print " (skipping)"
            else:
                soff = offset + mod.Offset
                size = mod.Size
                if mod.comptype() == COMP_TYPE_LZMA:
                    ext = "lzma"
                elif mod.comptype() == COMP_TYPE_HUFFMAN:
                    if nhuffs != 1:
                        nm = self.PartitionName

                    soff = self.huff_start + 0x40
                    size = self.chunkcount*4
                    ext = "huffoff"
                    fnametab = "%s_mod.%s" % (nm, ext)
                    print " => %s" % (fnametab),
                    open(fnametab, "wb").write(f[soff:soff+size])

                    #ext = "huff"
                    #soff = self.huff_start
                    #size = huff_end - mod.Offset

                    ext = "huff"
                    soff = self.datastart
                    size = self.datalen
                else:
                    ext = "bin"
                if self.Tag == '$MAN':
                    ext = "mod"
                    moff = soff+0x50
                    if f[moff:moff+5] == '\x5D\x00\x00\x80\x00':
                        lzf = open("%s_mod.lzma" % nm, "wb")
                        lzf.write(f[moff:moff+5])
                        lzf.write(struct.pack("<Q", mod.UncompressedSize))
                        lzf.write(f[moff+5:moff+mod.Size-0x50])
                fnamemod = "%s_mod.%s" % (nm, ext)
                print " => %s" % (fnamemod)
                open(fnamemod, "wb").write(f[soff:soff+size])
        for subtag, soff, subsize in self.updparts:
            fname = "%s_udc.bin" % subtag
            print "Update part: %r %08X/%08X" % (subtag, soff, subsize),
            print " => %s" % (fname)
            open(fname, "wb").write(f[soff:soff+subsize])
            extract_code_mods(subtag, f, soff)

        # Huffman chunks
        fhufftab = open("%s_mod.huffchunksummary" % self.PartitionName, "w")
        fhufftab.write("Huffman chunks:\n")
        chunksize = self.chunksize

        huffmanoffsets = []
        for huffoff in range(self.chunkcount):
            soff = self.huff_start + 0x40 + huffoff*4
            huffmanoffsets.append([struct.unpack("<I", f[soff:soff+4])[0],struct.unpack("B", f[soff+3:soff+4])[0]])
            huffmanoffsets[huffoff][1] = (huffmanoffsets[huffoff][0] >> 24) & 0xFF
            huffmanoffsets[huffoff][0] = huffmanoffsets[huffoff][0] & 0xFFFFFF
            print "0x%04X 0x%02X    (0x%06X)"  % (huffoff, huffmanoffsets[huffoff][1], huffmanoffsets[huffoff][0])
            fhufftab.write("0x%04X 0x%02X    (0x%06X) 0x%04X\n"  % (huffoff, huffmanoffsets[huffoff][1], huffmanoffsets[huffoff][0], huffmanoffsets[huffoff][0] - huffmanoffsets[huffoff-1][0]))
        fhufftab.close()
        huffmanoffsets.append([self.datastart, 0x00])
        huffmanoffsets = sorted(huffmanoffsets, key=itemgetter(0))
        for huffoff in range(self.chunkcount):
            flag = huffmanoffsets[huffoff][1]
            if flag != 0x80:
                offset0 = huffmanoffsets[huffoff][0]
                offset1 = huffmanoffsets[huffoff+1][0]
                chunklen = offset1 - offset0
                open("%s_chunk_%02X_%04d.huff" % (self.PartitionName, flag, huffoff), "wb").write(f[offset0:offset1])


PartTypes = ["Code", "BlockIo", "Nvram", "Generic", "Effs", "Rom"]

PT_CODE    = 0
PT_BLOCKIO = 1
PT_NVRAM   = 2
PT_GENERIC = 3
PT_EFFS    = 4
PT_ROM     = 5

class MeFptEntry(ctypes.LittleEndianStructure):
    _fields_ = [
        ("Name",            char*4),   # 00 partition name
        ("Owner",           char*4),   # 04 partition owner?
        ("Offset",          uint32_t), # 08 from the start of FPT, or 0
        ("Size",            uint32_t), # 0C
        ("TokensOnStart",   uint32_t), # 10
        ("MaxTokens",       uint32_t), # 14
        ("ScratchSectors",  uint32_t), # 18
        ("Flags",           uint32_t), # 1C
    ]
    #def __init__(self, f, offset):
        #self.sig1, self.Owner,  self.Offset, self.Size  = struct.unpack("<4s4sII", f[offset:offset+0x10])
        #self.TokensOnStart, self.MaxTokens, self.ScratchSectors, self.Flags = struct.unpack("<IIII", f[offset+0x10:offset+0x20])

    def ptype(self):
        return self.Flags & 0x7F

    def print_flags(self):
        pt = self.ptype()
        if pt < len(PartTypes):
            stype = "%d (%s)" % (pt, PartTypes[pt])
        else:
            stype = "%d" % pt
        print "    Type:         %s" % stype
        print "    DirectAccess: %d" % ((self.Flags>>7)&1)
        print "    Read:         %d" % ((self.Flags>>8)&1)
        print "    Write:        %d" % ((self.Flags>>9)&1)
        print "    Execute:      %d" % ((self.Flags>>10)&1)
        print "    Logical:      %d" % ((self.Flags>>11)&1)
        print "    WOPDisable:   %d" % ((self.Flags>>12)&1)
        print "    ExclBlockUse: %d" % ((self.Flags>>13)&1)


    def pprint(self):
        print "Partition:      %r" % self.Name
        print "Owner:          %s" % [repr(self.Owner), "(none)"][self.Owner == '\xFF\xFF\xFF\xFF']
        print "Offset/size:    %08X/%08X" % (self.Offset, self.Size)
        print "TokensOnStart:  %08X" % (self.TokensOnStart)
        print "MaxTokens:      %08X" % (self.MaxTokens)
        print "ScratchSectors: %08X" % (self.ScratchSectors)
        print "Flags:              %04X" % self.Flags
        self.print_flags()

class MeFptTable:
    def __init__(self, f, offset):
        hdr = f[offset:offset+0x30]
        if hdr[0x10:0x14] == '$FPT':
            base = offset + 0x10
        elif hdr[0:4] == '$FPT':
            base = offset
        else:
            raise Exception("FPT format not recognized")
        num_entries = DwordAt(f, base+4)
        self.BCDVer, self.FPTEntryType, self.HeaderLen, self.Checksum = struct.unpack("<BBBB", f[base+8:base+12])
        self.FlashCycleLifetime, self.FlashCycleLimit, self.UMASize   = struct.unpack("<HHI", f[base+12:base+20])
        self.Flags = struct.unpack("<I", f[base+20:base+24])[0]
        offset = base + 0x20
        self.parts = []
        for i in range(num_entries):
            part = get_struct(f, offset, MeFptEntry) #MeFptEntry(f, offset)
            offset += 0x20
            self.parts.append(part)

    def extract(self, f, offset):
        for ipart in range(len(self.parts)):
            part = self.parts[ipart]
            print "Partition:      %r %08X/%08X" % (part.Name, part.Offset, part.Size),
            islast = (ipart == len(self.parts)-1)
            if part.Offset in [0xFFFFFFFF, 0] or (part.Size in [0xFFFFFFFF, 0] and not islast):
                print " (skipping)"
            else:
                nm = part.Name.rstrip('\0')
                soff  = offset + part.Offset
                fname = "%s_part.bin" % (part.Name)
                fname = replace_bad(fname, map(chr, range(128, 256) + range(0, 32)))
                print " => %s" % (fname)
                open(fname, "wb").write(f[soff:soff+part.Size])
                if part.ptype() == PT_CODE:
                    extract_code_mods(nm, f, soff)

    def pprint(self):
        print "===ME Flash Partition Table==="
        print "NumEntries: %d" % len(self.parts)
        print "Version:    %d.%d" % (self.BCDVer >> 4, self.BCDVer & 0xF)
        print "EntryType:  %02X"  % (self.FPTEntryType)
        print "HeaderLen:  %02X"  % (self.HeaderLen)
        print "Checksum:   %02X"  % (self.Checksum)
        print "FlashCycleLifetime: %d" % (self.FlashCycleLifetime)
        print "FlashCycleLimit:    %d" % (self.FlashCycleLimit)
        print "UMASize:    %d" % self.UMASize
        print "Flags:      %08X" % self.Flags
        print "    EFFS present:   %d" % (self.Flags&1)
        print "    ME Layout Type: %d" % ((self.Flags>>1)&0xFF)
        print "---Partitions---"
        for part in self.parts:
            part.pprint()
            print
        print "------End-------"


region_names = ["Descriptor", "BIOS", "ME", "GbE", "PDR", "Region 5", "Region 6", "Region 7" ]
region_fnames =["Flash Descriptor", "BIOS Region", "ME Region", "GbE Region", "PDR Region", "Region 5", "Region 6", "Region 7" ]

def print_flreg(val, name):
    print "%s region:" % name
    lim  = ((val >> 4) & 0xFFF000)
    base = (val << 12) & 0xFFF000
    if lim == 0 and base == 0xFFF000:
        print "  [unused]"
        return None
    lim |= 0xFFF
    print "  %08X - %08X (0x%08X bytes)" % (base, lim, lim - base + 1)
    return (base, lim)

def parse_descr(f, offset, extract):
    mapoff = offset
    if f[offset+0x10:offset+0x14] == "\x5A\xA5\xF0\x0F":
        mapoff = offset + 0x10
    elif f[offset:offset+0x4] != "\x5A\xA5\xF0\x0F":
        return -1
    print "Flash Descriptor found at %08X" % offset
    FLMAP0, FLMAP1, FLMAP2 = struct.unpack("<III", f[mapoff+4:mapoff+0x10])
    nr   = (FLMAP0 >> 24) & 0x7
    frba = (FLMAP0 >> 12) & 0xFF0
    nc   = (FLMAP0 >>  8) & 0x3
    fcba = (FLMAP0 <<  4) & 0xFF0
    print "Number of regions: %d (besides Descriptor)" % nr
    print "Number of components: %d" % (nc+1)
    print "FRBA: 0x%08X" % frba
    print "FCBA: 0x%08X" % fcba
    me_offset = -1
    for i in range(nr+1):
        FLREG = struct.unpack("<I", f[offset + frba + i*4:offset + frba + i*4 + 4])[0]
        r = print_flreg(FLREG, region_names[i])
        if r:
            base, lim = r
            if i == 2:
                me_offset = offset + base
            if extract:
                fname = "%s.bin" % region_fnames[i]
                print " => %s" % (fname)
                open(fname, "wb").write(f[offset + base:offset + base + lim + 1])
    return me_offset

class AcManifestHeader(ctypes.LittleEndianStructure):
    _fields_ = [
        ("ModuleType",     uint16_t), # 00
        ("ModuleSubType",  uint16_t), # 02
        ("HeaderLen",      uint32_t), # 04 in dwords
        ("HeaderVersion",  uint32_t), # 08
        ("ChipsetID",      uint16_t), # 0C
        ("Flags",          uint16_t), # 0E 0x80000000 = Debug
        ("ModuleVendor",   uint32_t), # 10
        ("Date",           uint32_t), # 14 BCD yyyy.mm.dd
        ("Size",           uint32_t), # 18 in dwords
        ("Reserved1",      uint32_t), # 1C
        ("CodeControl",    uint32_t), # 20
        ("ErrorEntryPoint",uint32_t), # 24
        ("GDTLimit",       uint32_t), # 28
        ("GDTBasePtr",     uint32_t), # 2C
        ("SegSel",         uint32_t), # 30
        ("EntryPoint",     uint32_t), # 34
        ("Reserved2",      uint32_t*16), # 38
        ("KeySize",        uint32_t), # 78
        ("ScratchSize",    uint32_t), # 7C
        ("RsaPubKey",      uint32_t*64), # 80
        ("RsaPubExp",      uint32_t),    # 180
        ("RsaSig",         uint32_t*64), # 184
        # 284
    ]

    def pprint(self):
        print "Module Type: %d, Subtype: %d" % (self.ModuleType, self.ModuleSubType)
        print "Header Length:       0x%02X (0x%X bytes)" % (self.HeaderLen, self.HeaderLen*4)
        print "Header Version:      %d.%d" % (self.HeaderVersion>>16, self.HeaderVersion&0xFFFF)
        print "ChipsetID:           0x%04X" % (self.ChipsetID)
        print "Flags:               0x%04X" % (self.Flags),
        print " [%s signed] [%s flag]" % (["production","debug"][(self.Flags>>15)&1], ["production","pre-production"][(self.Flags>>14)&1])
        print "Module Vendor:       0x%04X" % (self.ModuleVendor)
        print "Date:                %08X" % (self.Date)
        print "Total Module Size:   0x%02X (0x%X bytes)" % (self.Size, self.Size*4)
        print "Reserved1:           0x%08X" % (self.Reserved1)
        print "CodeControl:         0x%08X" % (self.CodeControl)
        print "ErrorEntryPoint:     0x%08X" % (self.ErrorEntryPoint)
        print "GDTLimit:            0x%08X" % (self.GDTLimit)
        print "GDTBasePtr:          0x%08X" % (self.GDTBasePtr)
        print "SegSel:              0x%04X" % (self.SegSel)
        print "EntryPoint:          0x%08X" % (self.EntryPoint)
        print "Key size:            0x%02X (0x%X bytes)" % (self.KeySize, self.KeySize*4)
        print "Scratch size:        0x%02X (0x%X bytes)" % (self.ScratchSize, self.ScratchSize*4)
        print "RSA Public Key:      [skipped]"
        print "RSA Public Exponent: %d" % (self.RsaPubExp)
        print "RSA Signature:       [skipped]"
        print "------End-------"
