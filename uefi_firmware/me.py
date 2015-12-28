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
import os
import array

from .structs.intel_me_structs import *
from .utils import dump_data
from uefi_firmware import efi_compressor
from uefi_firmware.base import FirmwareObject, StructuredObject

MeModulePowerTypes = ["POWER_TYPE_RESERVED",
                      "POWER_TYPE_M0_ONLY", "POWER_TYPE_M3_ONLY", "POWER_TYPE_LIVE"]
MeCompressionTypes = ["COMP_TYPE_NOT_COMPRESSED",
                      "COMP_TYPE_HUFFMAN", "COMP_TYPE_LZMA", "<unknown>"]
COMP_TYPE_NOT_COMPRESSED = 0
COMP_TYPE_HUFFMAN = 1
COMP_TYPE_LZMA = 2
MeModuleTypes = ["DEFAULT", "PRE_ME_KERNEL",
                 "VENOM_TPM", "APPS_QST_DT", "APPS_AMT", "TEST"]
MeApiTypes = ["API_TYPE_DATA", "API_TYPE_ROMAPI",
              "API_TYPE_KERNEL", "<unknown>"]


class MeObject(StructuredObject, FirmwareObject):

    """
    An ME Object is a combination of a parsing/extraction class and a ctype
    definding structure object.

    This follows the same ctor, process, showinfo, dump calling convention.
    """
    pass


class MeModule(MeObject):

    def __init__(self, data, structure_type, offset):
        self.attrs = {}
        self.parse_structure(data, structure_type)
        self.structure_type = structure_type

        if structure_type == MeModuleHeader2Type:
            self.structure.Guid = "(none)"
            self.attrs["version"] = "0.0.0.0"
        elif structure_type == MeModuleHeader1Type:
            self.attrs["version"] = "%d.%d.%d.%d" % (
                self.structure.MajorVersion, self.structure.MinorVersion,
                self.structure.HotfixVersion,
                self.structure.BuildVersion
            )

        self.guid = self.structure.Guid
        self.name = self.structure.Name
        self.tag = self.structure.Tag

        self.attrs["module_size"] = self.structure.Size
        self.attrs["load_base"] = self.structure.LoadBase
        self.attrs["flags"] = self.structure.Flags
        if structure_type == MeModuleHeader2Type:
            self.attrs["power_type"] = (
                self.structure.Flags >> 1) & 3  # MeModulePowerTypes
            self.attrs["compression"] = (
                self.structure.Flags >> 4) & 7  # MeCompressionTypes
            # MeModuleTypes (optional)
            self.attrs["module_stage"] = (self.structure.Flags >> 7) & 0xF
            self.attrs["api_type"] = (
                self.structure.Flags >> 11) & 7  # MeApiTypes
            self.attrs["privileged"] = ((self.structure.Flags >> 16) & 1)
        # There are unknown flags to parse, todo: revisit
        pass

        # Must know the offset from given data (the start of the header) to
        # find data
        self.offset = self.structure.Offset - offset
        # print "Debug: module data 0x%08X - 0x%08X" % (
        #    self.offset, self.offset + self.structure.Size)
        self.data = data[self.offset:self.offset + self.structure.Size]

    @property
    def objects(self):
        return [self.data]

    def process(self):
        if self.compression == COMP_TYPE_HUFFMAN:
            # The individual modules are compressed together in a partition
            # chunk
            return True

        if self.structure_type == MeModuleHeader1Type:
            # It's possible for type 1 to include LZMA compression
            if self.data[0x50:0x55] == '\x5D\x00\x00\x80\x00':
                raw_data = self.data[0x50:0x55]
                raw_data += struct.pack("<Q", self.structure.UncompressedSize)
                raw_data += self.data[0x55:]
                self.data = raw_data
        return True

    @property
    def size(self):
        return ctypes.sizeof(self.structure_type)

    @property
    def compression(self):
        if self.structure_type == MeModuleHeader1Type:
            return COMP_TYPE_NOT_COMPRESSED
        else:
            return (self.structure.Flags >> 4) & 7

    def showinfo(self, ts=''):
        print "%sModule %s, GUID: %s, Version: %s, Size: %s" % (
            ts, self.name, self.guid, self.attrs["version"], self.attrs["module_size"]),
        if self.compression == COMP_TYPE_HUFFMAN:
            print " (huffman)"
        elif self.compression == COMP_TYPE_LZMA:
            print " (lzma)"
        else:
            print ""

    def dump(self, parent=""):
        if self.compression == COMP_TYPE_HUFFMAN:
            pass
        else:
            dump_data("%s.module.lzma" %
                      os.path.join(parent, self.name), self.data)
            try:
                data = efi_compressor.LzmaDecompress(self.data, len(self.data))
                dump_data("%s.module" % os.path.join(parent, self.name), data)
            except Exception as e:
                print "Cannot extract GUID (%s), %s" % (sguid(self.guid), str(e))
                return
            pass
        pass


class MeVariableModule(MeObject):
    HEADER_SIZE = 8

    def __init__(self, data, structure_type):
        self.update = {}
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
            # print "Debug: invalid module header."
            self.valid_header = False
            return

        self.tag = hdr[:4]
        # Note the elen size includes the header size
        self.size = struct.unpack("<I", hdr[4:])[0] * 4 - self.HEADER_SIZE
        self.data = data[self.HEADER_SIZE:self.size]
        pass

    def add_update(self, tag, name, offset, size):
        self.update["tag"] = tag
        self.update["name"] = name
        self.update["offset"] = offset
        self.update["size"] = size
        pass

    def process(self):
        if self.tag == '$UDC':
            subtag, _hash, name, offset, size = struct.unpack(
                self.stype.udc_format, self.data[:self.type.udc_length])
            # print "Debug: update code found: (%s) (%s), length: %d" %
            # (subtag, name, size)
            self.add_update(subtag, name, offset, size)
        if self.size == 3:
            values = [struct.unpack("<I", self.data[:4])[0]]
        if self.size == 4:
            values = struct.unpack("<II", self.data[:8])[0]
        else:
            values = array.array("I", self.data)

        self.values = values
        return True

    def showinfo(self, ts=''):
        print "%sVModule Tag: %s, size: %d" % (ts, self.tag, self.size)
        if self.tag == '$UDC':
            print "%s  Update Tag: %s, name: %s, offset: %d, size: %s" % (
                self.update["tag"], self.update["name"], self.update["offset"], self.update["size"])
        pass


class MeModuleFile(MeObject):

    def __init__(self, data):
        self.size = 0
        tag = data[:4]

        self.valid_header = True
        if tag != "$MOD":
            self.valid_header = False
            return

        self.parse_structure(data, MeModuleFileHeader1Type)
        self.name = self.structure.Name.rstrip('\0')
        self.size = self.structure.Size
        pass


class MeLLUT(MeObject):

    def __init__(self, data, relative_offset):
        #self.tag = data[:4]

        self.valid_header = True
        if data[:4] != 'LLUT':
            self.valid_header = False

        #hdr = data[4:52]
        # chunkcount, decompbase, unk0c, size, start, a,b,c,d,e,f, chunksize = struct.unpack(
        #    "<IIIIIIIIIIII", hdr)
        self.parse_structure(data, HuffmanLUTHeader)
        self.size = self.structure.Size

        # The start and end addresses are relative to the manifest.
        # The relative offset references the start of the manifest data (not
        # header).
        self.start = self.structure.DataStart
        self.offset = relative_offset

        self.chunkcount = self.structure.ChunkCount
        self.chunksize = self.structure.ChunkSize
        self.decompression_base = self.structure.DecompBase

        self.data = data[
            self.start - relative_offset:self.start - relative_offset + self.size]
        # The huffman look up table is stored following the header data.
        self.lut_data = data[
            self.structure_size:self.structure_size + self.chunkcount * 4]

    def showinfo(self, ts=''):
        print "%sLLUT chunks (%d), chunk size (%d), start (%d), size (%d), base (%08X)." % (
            ts, self.chunkcount, self.chunksize, self.start, self.size, self.decompression_base)

    def dump(self, parent='PART'):
        # print "Debug: relative (%d) absolute start (%d) len (%d)." % (
        #    self.offset, self.start, len(self.data))
        dump_data("%s.llut.table" % parent, self.lut_data)
        dump_data("%s.llut.compressed" % parent, self.data)


class MeManifestHeader(MeObject):
    _DATA_OFFSET = 12

    def __init__(self, data, container_offset=0):
        self.attrs = {}

        self.valid_header = True
        if data[:8] != "\x04\x00\x00\x00\xA1\x00\x00\x00":
            from .utils import hex_dump
            hex_dump(data[:32])
            # print "Debug: invalid partition."
            self.valid_header = False
            return

        self.parse_structure(data, MeManifestHeaderType)
        # Save the container offset as LLUT start is an absolute reference
        self.container_offset = container_offset
        self.data = data[self.partition_offset:]

        '''Set storage attributes.'''
        self.attrs["header_version"] = "%d.%d" % (
            self.structure.HeaderVersion >> 16, self.structure.HeaderVersion & 0xFFFF)
        self.attrs["version"] = "%d.%d.%d.%d" % (
            self.structure.MajorVersion,
            self.structure.MinorVersion,
            self.structure.HotfixVersion,
            self.structure.BuildVersion
        )
        self.attrs["flags"] = "0x%08X" % (self.structure.Flags)
        self.attrs["module_vendor"] = "0x%04X" % (self.structure.ModuleVendor)
        self.attrs["date"] = "%08X" % (self.structure.Date)
        self.size = self.structure.Size

        '''Skipped.'''
        #ModuleType, ModuleSubType, size, tag, num_modules, keysize, scratchsize, rsa

        self.partition_name = self.structure.PartitionName.rstrip("\0")
        if not self.partition_name:
            self.partition_name = "(none)"

        self.modules = []
        self.partition_end = 0

    @property
    def absolute_offset(self):
        return self.structure.HeaderLen * 4 + self._DATA_OFFSET + self.container_offset

    @property
    def partition_offset(self):
        return self.structure.HeaderLen * 4 + self._DATA_OFFSET

    def showinfo(self, ts=''):
        print "Module Manifest type: %d, subtype: %d, partition name: %s" % (
            self.structure.ModuleType, self.structure.ModuleSubType, self.structure.PartitionName)
        for module in self.modules:
            module.showinfo(ts="  %s" % ts)
        for module in self.variable_modules:
            module.showinfo(ts="  %s" % ts)
        self.huffman_llut.showinfo(ts="  %s" % ts)

    def _parse_mods(self):
        # Parse the module headers (two types of headers, specified by the
        # manifest).
        module_offset = 0
        huffman_offset = 0
        for module_index in xrange(self.structure.NumModules):
            module = MeModule(
                self.data[module_offset:],
                self.header_type, module_offset + self.partition_offset)
            # print "Debug: found me module header (%s) at (%d)." %
            # (module.tag, module_offset)
            if module.compression == COMP_TYPE_HUFFMAN:
                # Todo: skipped precondition for huffman offsets.
                # print "Debug: Setting huffman offset: %d" %
                # module.structure.Offset
                huffman_offset = module.structure.Offset
            if not module.process():
                return False
            self.modules.append(module)
            self.module_map[module.name] = module
            module_offset += module.size

        #additional_header = self.structure.Size*4 - module_offset
        # print "Debug: Remaining header: %d - %d = %d" % (
        #    self.structure.Size*4, module_offset, additional_header)

        self.module_offset = module_offset
        self.huffman_offset = huffman_offset
        return True

    def _parse_variable_mods(self, module_offset):
        # Parse additional tagged modules.
        self.variable_modules = []
        self.partition_end = 0
        while module_offset < self.structure.Size * 4:
            # There is more module header to process.
            module = MeVariableModule(
                self.data[module_offset:], self.header_type)
            if not module.valid_header:
                break
            module_offset += module.HEADER_SIZE
            if module.header_blank:
                continue

            # print "Debug: found module (%s) size (%d)." % (module.tag,
            # module.size)
            if not module.process():
                return False
            if module.tag == '$MCP':
                # The end of a manifest partition is stored in MCP
                self.partition_end = module.values[0] + module.values[1]
            self.variable_modules.append(module)
            module_offset += module.size
        return True

    def _parse_module_files(self):
        file_offset = self.structure.Size * 4
        # print "Debug: looking for module files at (%08X)." % file_offset
        while True:
            module_file = MeModuleFile(self.data[file_offset:])
            if not module_file.valid_header:
                break
            if module_file.name in module_map:
                # A module file header cooresponds to the module header
                self.module_map[module_file.name].file = module_file
            # print "Debug: found module file (%s) size (%d)." %
            # (module_file.name, module_file.size)
            file_offset += module_file.size
        return True

    def process(self):
        self.modules = []
        self.module_map = {}

        if self.structure.Tag == '$MN2':
            self.header_type = MeModuleHeader2Type
        elif self.structure.Tag == '$MAN':
            self.header_type = MeModuleHeader1Type
        else:
            # Cannot parse modules...
            return False

        # Parse the module headers (two types of headers, specified by the
        # manifest).
        if not self._parse_mods():
            return False
        if not self._parse_variable_mods(self.module_offset):
            return False
        if not self._parse_module_files():
            return False

        # Parse optional huffman LLUT.
        huffman_offset = self.huffman_offset - self.partition_offset
        huffman_llut = MeLLUT(
            self.data[huffman_offset:], huffman_offset + self.absolute_offset)
        # if huffman_llut.valid_header:
        #    print "Debug: huffman LLUT start (0x%08X) end (0x%08X)." % (
        #        huffman_llut.offset, huffman_llut.size + huffman_llut.start)
        # print "Debug: LLUT end (%08X) partition end (%08X)." % (
        #    huffman_llut.size + huffman_offset, self.partition_end)

        self.huffman_llut = huffman_llut
        return True

    def dump(self, parent=""):
        #huffman_end = self.huffman_llut.size + self.huffman_llut.start
        for module in self.modules:
            # if module.compression == COMP_TYPE_HUFFMAN:
                # print "Huffman module data: %r %08X/%08X" % (
                #    module.name, self.huffman_llut.start, self.huffman_llut.size)
            # else:
                #huffman_end = (min(huffman_end, module.structure.Offset))
                # print "Debug: decrementing huffman to %d" % huffman_end
            module.dump(parent)
        self.huffman_llut.dump(
            os.path.join(parent, self.structure.PartitionName))
        pass


class MeContainer(MeObject):

    def __init__(self, data):
        self.partitions = []
        self.data = data

    @property
    def objects(self):
        return self.partitions

    def process(self):
        offset = 0
        while True:
            partition_manifest = MeManifestHeader(self.data[offset:], offset)
            if not partition_manifest.valid_header:
                # print "Debug: ending at (%08X)." % offset
                break
            # print "Debug: Found valid partition (%08X)." % offset

            if not partition_manifest.process():
                return False
            self.partitions.append(partition_manifest)
            offset += partition_manifest.partition_end
        return True

    def showinfo(self, ts=''):
        for partition in self.partitions:
            partition.showinfo("  %s" % ts)

    def dump(self, parent=""):
        for partition in self.partitions:
            partition.dump(
                os.path.join(parent, partition.structure.PartitionName))
