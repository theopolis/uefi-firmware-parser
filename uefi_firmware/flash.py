# -*- coding: utf-8 -*-

import os
import sys, struct
import uuid

from .base import FirmwareObject, RawObject, BaseObject, StructuredObject
from .uefi import FirmwareVolume
from .utils import *
from .guids import get_guid_name
from .structs.flash_structs import *

FLASH_HEADER = "\x5A\xA5\xF0\x0F"

class RegionSection(StructuredObject):
    size = 20
    def __init__(self, data):
        self.parse_structure(data, FlashRegionSectionType)
    pass

class MasterSection(StructuredObject):
    size = 12
    def __init__(self, data):
        self.parse_structure(data, FlashMasterSectionType)
    pass

class DescriptorMap(StructuredObject):
    size = 16
    def __init__(self, data):
        self.parse_structure(data, FlashDescriptorMapType)
    pass

class FlashRegion(FirmwareObject, BaseObject):
    def __init__(self, data, region_name, region_details):
        self.sections = []
        self.data = data
        self.attrs = region_details
        self.name = region_name

    @property
    def objects(self):
        return self.sections

    def process(self):
        if self.name == "bios":
            data= self.data
            while True:
                volume_index = search_firmware_volumes(data, limit= 1)
                if len(volume_index) == 0:
                    break
                fv = FirmwareVolume(data[volume_index[0]-40:])
                if fv.valid_header:
                    self.sections.append(fv)
                    data = data[fv.size:]
                data = data[volume_index[0] + 8:]
        if self.name == "me":
            pass
        for section in self.sections:
            section.process()
        pass

    def showinfo(self, ts='', index= None):
        print "%s%s type= %s, size= 0x%x (%d bytes) details[ %s ]" % (
            ts, blue("Flash Region"), green(self.name),
            len(self.data), len(self.data),
            ", ".join(["%s: %s" % (k,v) for k,v in self.attrs.iteritems()])
        )
        for section in self.sections:
            section.showinfo(ts= "%s  " % ts)
        pass

    def dump(self, parent= ""):
        pass
    pass

class FlashDescriptor(FirmwareObject):
    def __init__(self, data):
        self.padding, self.header = struct.unpack("<16s4s", data[:16+4])
        #print self.header.encode("hex")

        self.valid_header = True
        if self.header != FLASH_HEADER:
            print "Error: Invalid flash descriptor header."
            self.valid_header = False
            return

        self.regions = []
        self.data = data

    @property
    def objects(self):
        return self.regions

    def process(self):
        def _region_size(base, limit):
            if limit: return (limit + 1 - base) * 0x1000
            return 0
        def _region_offset(base):
            return base * 0x1000
        self.map = DescriptorMap(self.data[20:20+DescriptorMap.size])
        region_offset = (self.map.structure.RegionBase * 0x10)
        self.region = RegionSection(self.data[region_offset:region_offset + RegionSection.size])
        master_offset = (self.map.structure.MasterBase * 0x10)
        self.master = MasterSection(self.data[master_offset:master_offset + MasterSection.size])

        bios_base = self.region.structure.BiosBase
        bios_limit = self.region.structure.BiosLimit
        bios = self.data[_region_offset(bios_base): _region_offset(bios_base) + _region_size(bios_base, bios_limit)]

        bios_region = FlashRegion(bios, "bios", {
            "base": bios_base, 
            "limit": bios_limit,
            "id": self.master.structure.BiosId,
            "read": self.master.structure.BiosRead,
            "write": self.master.structure.BiosWrite
        })
        bios_region.process()
        self.regions.append(bios_region)

        me_base = self.region.structure.MeBase
        me_limit = self.region.structure.MeLimit
        me = self.data[_region_offset(me_base): _region_offset(me_base) + _region_size(me_base, me_limit)]

        me_region = FlashRegion(me, "me", {
            "base": me_base, 
            "limit": me_limit,
            "id": self.master.structure.MeId,
            "read": self.master.structure.MeRead,
            "write": self.master.structure.MeWrite
        })
        me_region.process()
        self.regions.append(me_region)

        gbe_base = self.region.structure.GbeBase
        gbe_limit = self.region.structure.GbeLimit
        gbe = self.data[_region_offset(gbe_base): _region_offset(gbe_base) + _region_size(gbe_base, gbe_limit)]

        gbe_region = FlashRegion(gbe, "gbe", {
            "base": gbe_base, 
            "limit": gbe_limit,
            "id": self.master.structure.GbeId,
            "read": self.master.structure.GbeRead,
            "write": self.master.structure.GbeWrite
        })
        gbe_region.process()
        self.regions.append(gbe_region)

    def showinfo(self, ts= '', index= None):
        print "%s%s chips %d, regions %d, masters %d, PCH straps %d, PROC straps %d, ICC entries %d" % (
            ts, blue("Flash Descriptor (Intel PCH)"),
            self.map.structure.NumberOfFlashChips, 
            self.map.structure.NumberOfRegions, self.map.structure.NumberOfMasters,
            self.map.structure.NumberOfPchStraps, self.map.structure.NumberOfProcStraps,
            self.map.structure.NumberOfIccTableEntries
        )
        for region in self.regions:
            region.showinfo(ts= "%s  " % ts)

    pass

