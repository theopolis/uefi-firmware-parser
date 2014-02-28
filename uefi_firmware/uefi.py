# -*- coding: utf-8 -*-

import os
import sys, struct
import uuid

from .utils import *
from .structs.uefi_structs import *
#from .contrib import efi_decompressor
import efi_compressor
from .lzma import p7z_extract

def _get_file_type(file_type):
    return EFI_FILE_TYPES[file_type] if file_type in EFI_FILE_TYPES else ("unknown", "unknown")

def _get_section_type(section_type):
    return EFI_SECTION_TYPES[section_type] if section_type in EFI_SECTION_TYPES else ("unknown", "unknown.bin")

def uefi_name(s):
    try:
        name = s.decode("utf-16le").split("\0")[0]
        if len(name) == 0:
            return None
        for c in name:
            if ord(c) > 128: return None
        return name
    except Exception, e:
        return None

class FirmwareObject(object):
    data = None

    @property
    def content(self):
        if hasattr(self, "data"): return self.data
        return ""
    @property
    def objects(self):
        return []
    @property
    def label(self):
        if hasattr(self, "name"): 
            if self.name is None: return ""
            return self.name
        return ""
    @property
    def guid_label(self):
        if not hasattr(self, "guid"): return ""
        return fguid(self.guid)
    @property
    def type_label(self):
        return self.__class__.__name__
    @property
    def attrs_label(self):
        if hasattr(self, "attrs"): return self.attrs
        return {}

    def info(self, include_content= False):
        return {
            "_self": self,
            "label": self.label,
            "guid": self.guid_label,
            "type": self.type_label,
            "content": self.content if include_content else "",
            "attrs": self.attrs_label
        }   
    
    def iterate_objects(self, include_content= False):
        objects = []
        for _object in self.objects:
            if _object is None: continue
            _info = _object.info(include_content)
            _info["objects"] = _object.iterate_objects(include_content)
            objects.append(_info)
        return objects

class RawObject(FirmwareObject):
    def __init__(self, data):
        self.data = data
    pass

class EfiSection(FirmwareObject):
    subsections = []

    @property
    def objects(self):
        return self.subsections

    def process_subsections(self):
        self.subsections = []

        if not self.data: return

        subsection_offset = 0
        while subsection_offset < len(self.data):
            if subsection_offset % 4: subsection_offset += 4 - (subsection_offset % 4)
            if subsection_offset >= len(self.data): break

            subsection = FirmwareFileSystemSection(self.data[subsection_offset:], self.guid)
            if subsection.size == 0: break
            subsection.process()
            self.subsections.append(subsection)

            subsection_offset += subsection.size

    def process(self): pass
    def showinfo(self, ts= '', index=-1): pass

    def dump(self, parent= "", index=0):
        for i, subsection in enumerate(self.subsections):
            subsection.dump(parent, i)


class CompressedSection(EfiSection):
    name = None
    
    def __init__(self, data, guid):
        self.guid= guid
        self.data= None
        self.parsed_objects = []
        
        # http://dox.ipxe.org/PiFirmwareFile_8h_source.html
        self.decompressed_size, self.type = struct.unpack("<Ic", data[:5])
        self.type = ord(self.type)
        
        # Advance the byte pointer through the header
        self.uncompressed_data = data[5:]
        self.attrs = {"decompressed_size": self.decompressed_size, "type": self.type}
        
        pass
    
    def _try_again(self, data, offset):
        '''Warning: this is a massive hack.'''
        object = FirmwareFileSystemSection(self.data[offset+2:], self.guid)
        return object
    
    def process(self):        
        if self.type == 0x01:
            '''EFI or Tiano compression.'''
            try:
                #self.data = efi_decompressor.Decompress(self.uncompressed_data)
                self.data = efi_compressor.UefiDecompress(self.uncompressed_data, len(self.uncompressed_data))
            except Exception, e:
                print "Error: cannot decompress (%s) (%s)." % (fguid(self.guid), str(e))

        if self.type == 0x00:
            '''No compression.'''
            self.data = self.uncompressed_data

        if self.type == 0x02:
            self.data = p7z_extract(self.uncompressed_data)
            
        if self.data is None:
            '''No data was uncompressed.'''
            return
        
        self.process_subsections()
        pass

    def showinfo(self, ts):
        if self.name is not None:
            print "%s %s" % (blue("%sCompressed Name:" % ts), purple(self.name))
        for i, _object in enumerate(self.subsections):
            _object.showinfo(ts, i)
        
        pass

class FreeformGuidSection(EfiSection):
    """
    A firmware file section type (free-form GUID)

    struct { UCHAR GUID[16]; }
    """
    _CHAR_GUID = uuid.UUID("{059ef06e-c652-4a45-be9f-5975e369461c}")
    name = None

    def __init__(self, data):
        self.guid = struct.unpack("<16s", data[:16])[0]
        #print "FFGS", len(data), len(self.guid), fguid(self.guid)
        self.data = data[16:]

    def process(self):
        if uuid.UUID(fguid(self.guid)) == self._CHAR_GUID:
            self.guid_header = self.data[:12]
            self.name = uefi_name(self.data[12:])
        pass

    def showinfo(self, ts='', index=-1): 
        if self.name is not None:
            print "%sGUID Description: %s" % (ts, purple(self.name))
        pass

    pass

class GuidDefinedSection(EfiSection):
    """
    A firmware file section type (GUID-defined)

    struct { UCHAR GUID[16]; short offset; short attrs; }
    """
    LZMA_COMPRESSED_GUID = "ee4e5898-3914-4259-6e9d-dc7bd79403cf"
    STATIC_GUID = "fc1bcdb0-7d31-49aa-6a93-a4600d9dd083"

    def __init__(self, data):
        self.guid, self.offset, self.attrs = struct.unpack("<16sHH", data[:20])
        self.data = data[20:]

        self.subsections = []

    @property
    def objects(self):
        return self.subsections

    def process(self):
        if fguid(self.guid) == self.LZMA_COMPRESSED_GUID:
            self.data = p7z_extract(self.data)
            self.process_subsections()

        elif fguid(self.guid) == self.STATIC_GUID:
            self.process_subsections()
        pass

    def showinfo(self, ts='', index= 0):
        if len(self.subsections) > 0:
            for i, section in enumerate(self.subsections):
                section.showinfo(ts, index= i)

    pass

class FirmwareFileSystemSection(EfiSection):
    """
    A firmware file section
    
    struct { UINT8 Size[3]; EFI_SECTION_TYPE Type; } EFI_COMMON_SECTION_HEADER;
    """
    
    parsed_object = None
    '''For object sections, keep track of each.'''
    
    def __init__(self, data, guid):
        self.guid= guid
        
        header = data[:0x4]
        try:
            self.size, self.type = struct.unpack("<3sB", header)
            self.size = struct.unpack("<I", self.size + "\x00")[0]
        except Exception, e:
            print "Error: invalid FirmwareFileSystemSection header, expected size 4, got (%d)." % len(header)
            raise e
        
        self._data = data[:0x4 + self.size]
        self.data = data[0x4:self.size]
        self.name = None

    @property
    def objects(self):
        return [self.parsed_object]
        #return self.subsections

    def process(self):
        self.parsed_object = None

        if self.type == 0x01: # compression
            compressed_section = CompressedSection(self.data, self.guid)
            self.parsed_object = compressed_section

        elif self.type == 0x02: # GUID-defined
            guid_defined = GuidDefinedSection(self.data)
            self.parsed_object = guid_defined
        
        elif self.type == 0x14: # version string
            self.name = uefi_name(self.data)

        elif self.type == 0x15: # user interface name
            self.name = uefi_name(self.data)
        
        elif self.type == 0x17: # firmware-volume
            fv = FirmwareVolume(self.data, fguid(self.guid))
            self.parsed_object = fv
        
        elif self.type == 0x18: # freeform GUID
            freeform_guid = FreeformGuidSection(self.data)
            self.parsed_object = freeform_guid

        self.attrs = {"type": self.type, "size": self.size}
        self.attrs["type_name"] = _get_section_type(self.type)[0]

        if self.parsed_object is None: return
        self.parsed_object.process()

        pass

    def showinfo(self, ts='', index=-1):
        print "%s type 0x%02x, size 0x%x (%s section)" % (blue("%sSection %d:" % (ts, index)), self.type, self.size, _get_section_type(self.type)[0])
        if self.type == 0x15 and self.name is not None: print "%sName: %s" % (ts, purple(self.name))
        
        if self.parsed_object is not None:
            '''If this is a specific object, show that object's info.'''
            self.parsed_object.showinfo(ts + '  ')
                
    def dump(self, parent= "", index= 0):
        self.path = os.path.join(parent, "section%d.%s" % (index, _get_section_type(self.type)[1]))
        dump_data(self.path, self._data)

        if self.parsed_object is not None:
            self.parsed_object.dump(os.path.join(parent, "section%d" % index))


class FirmwareFile(FirmwareObject):
    """
    A firmware file is contained within a firmware file system and is comprised of firmware file sections.
    
    struct {
        UCHAR: FileNameGUID[16]
        UINT16: Checksum (header/file)
        UINT8: Filetype
        UINT8: Attributes
        UINT8: Size[3]
        UINT8: State
    };
      
    """
    _HEADER_SIZE = 0x18 # 24 byte header, always
    
    def __init__(self, data):
        header = data[:self._HEADER_SIZE]

        try:
            self.guid, self.checksum, self.type, self.attributes, self.size, self.state = struct.unpack("<16sHBB3sB", header)
            self.size = struct.unpack("<I", self.size + "\x00")[0]
        except Exception, e:
            print "Error: invalid FirmwareFile header."
            raise e

        #print "Debug: Found file with size (%d)." % self.size
        self.attrs = {"size": self.size, "type": self.type, "attributes": self.attributes, "state": self.state ^ 0xFF}
        self.attrs["type_name"] = _get_file_type(self.type)[0]
        
        '''The size includes the header bytes.'''
        self._data = data[:self._HEADER_SIZE + self.size]
        self.data = data[self._HEADER_SIZE:self.size]
        self.raw_blobs = []
        self.sections = []

    @property
    def objects(self):
        return self.sections

    def process(self):
        """
        Parse the file and file sections if appropriate.
        """
        if self.type == 0xf0: # ffs padding
            return
        
        if self.type == 0x01: # raw file
            '''File is raw, no sections.'''
            self.raw_blobs.append(self.data)
            return

        if self.type == 0x00: # unknown
            self.raw_blobs.append(self.data)
            return
        
        section_data = self.data
        self.sections = []
        while len(section_data) > 0:
            file_section = FirmwareFileSystemSection(section_data, self.guid)
            if file_section.size <= 0:
                '''This is not expected, something bad happened while parsing.'''
                print "Error: file section size <= 0 (%d)." % file_section.size
                break
            
            file_section.process()
            self.sections.append(file_section)
            section_data = section_data[(file_section.size + 3)&(~3):]
        pass
    
    def showinfo(self, ts='', index= "N/A"):
        print "%s %s type 0x%02x, attr 0x%02x, state 0x%02x, size 0x%x (%d bytes), (%s)" % (
            blue("%sFile %s:" % (ts, index)),
            green(fguid(self.guid)), self.type, self.attributes, self.state ^ 0xFF, 
            self.size, self.size, _get_file_type(self.type)[0]
        )
        
        for i, blob in enumerate(self.raw_blobs):
            self._guessinfo(ts+"  ", blob, index=i)
        
        if self.sections is None:
            # padding file, skip for now
            return
        
        for i, section in enumerate(self.sections):
            section.showinfo(ts+"  ", index=i)
    
    def _guessinfo(self, ts, data, index= "N/A"):
        if data[:4] == "\x01\x00\x00\x00" and data[20:24] == "\x01\x00\x00\x00":
            print "%s Might contain CPU microcodes" % (blue("%sBlob %d:" % (ts, index)))
    
    def dump(self, parent= ""):
        parent = os.path.join(parent, "file-%s" % fguid(self.guid))

        if self.raw_blobs is not None:
            for i, blob in enumerate(self.raw_blobs):
                self.path = os.path.join(parent, "blob-%s.raw" % i)
                dump_data(self.path, blob)

        if self.sections is not None:
            for i, section in enumerate(self.sections):
                section.dump(parent, index= i)

class FirmwareFileSystem(FirmwareObject):
    """
    A potential UEFI firmware filesystem data stream, comprised of fimrware file system (FSS) sections.
    The FFS is a specific GUID within the FirmwareVolume  
    
    FFS GUID: D9 54 93 7A 68 04 4A 44 81 CE 0B F6 17 D8 90 DF
    """
    FFS_GUID = "7a9354d9-0468-444a-ce81-0bf617d890df"
    
    def __init__(self, data):
        self.files = []
        self._data = data
        self.data = data
    
    @property
    def objects(self):
        return self.files or []
    
    def process(self):
        '''Search for a 24-byte header that does not contain all 0xFF.'''
        
        while len(self.data) >= 24 and self.data[:24] != ("\xff"*24):
            firmware_file = FirmwareFile(self.data)

            if firmware_file.size < 24:
                '''This is a problem, the file was corrupted.'''
                break
            
            firmware_file.process()
            self.files.append(firmware_file)
            
            self.data = self.data[(firmware_file.size + 7) & (~7):]
        pass
    
    def showinfo(self, ts= ''):
        for i, firmware_file in enumerate(self.files):
            #print ts + "File %d:" % i
            firmware_file.showinfo(ts + ' ', index=i)
    
    def dump(self, parent= ""):
        dump_data(os.path.join(parent, "%s.ffs" % self.FFS_GUID), self._data)

        for _file in self.files:
            _file.dump(parent)

class FirmwareVolume(FirmwareObject):
    """
    
    struct EFI_FIRMWARE_VOLUME_HEADER {
        UINT8: Zeros[16]
        UCHAR: FileSystemGUID[16]
        UINT64: Length
        UINT32: Signature (_FVH)
        UINT8: Attribute mask
        UINT16: Header Length
        UINT16: Checksum
        UINT8: Reserved[3]
        UINT8: Revision
        [<BlockMap>]+, <BlockMap(0,0)>
    };
    
    struct BLOCK_MAP {
        UINT32: Block count
        UINT32: Block size
    };
    
    The block map is a set of block followed by a zeroed block indicating the end of the map set.
    
    """
    _HEADER_SIZE = 0x38
    _VALID_GUIDS = ['7a9354d9-0468-444a-ce81-0bf617d890df', '8c8ce578-8a3d-4f1c-3599-896185c32dd3', 'fff12b8d-7696-4c8b-85a9-2747075b4f50']
    
    name = None
    '''An optional name or offset of the firmware volume.'''
    
    block_map = None
    '''An empty block set.'''
    
    firmware_filesystems = None
    
    def __init__(self, data, name= "volume"):
        self.name = name
        self.valid_header = False

        try:
            header = data[:self._HEADER_SIZE]
            self.rsvd, self.guid, self.size, self.magic, self.attributes, self.hdrlen, self.checksum, self.rsvd2, self.revision = struct.unpack("<16s16sQ4sIHH3sB", header)
        except Exception, e:
            print "Error: cannot parse FV header (%s)." % str(e)
            return

        if fguid(self.guid) not in self._VALID_GUIDS:
            print "Error: invalid FV guid (%s)." % fguid(self.guid)
            return

        self.blocks = []
        self.block_map = ""

        try:
            data = data[:self.size]

            self._data = data
            self.data = data[self.hdrlen:]
            self.block_map = data[self._HEADER_SIZE:self.hdrlen]
        except Exception, e:
            print "Error invalid FV header data (%s)." % str(e)
            return

        self.valid_header = True
        pass

    @property
    def objects(self):
        return self.firmware_filesystems or []
    
    def process(self):
        if self.block_map is None: return
        
        block_data = self.block_map
        while len(block_data) > 0:
            block = block_data[:8]
            
            block_size, block_length = struct.unpack("<II", block)
            if (block_size, block_length) == (0,0):
                '''The block map ends with a (0, 0) block.'''
                break
            
            self.blocks.append((block_size, block_length))
            block_data = block_data[8:]
            
        if len(self.blocks) == 0:
            '''No block in the volume? This is a problem.'''
            return
        
        self.firmware_filesystems = []
        for block in self.blocks:
            firmware_filesystem = FirmwareFileSystem(self.data[:block[0] * block[1]])
            firmware_filesystem.process()            
            self.firmware_filesystems.append(firmware_filesystem)
            
    def showinfo(self, ts=''):
        if len(self.data) == 0:
            return

        print "%s %s attr 0x%08x, rev %d, size 0x%x (%d bytes)" % (
            blue("%sFirmware Volume:" % (ts)),
            green(fguid(self.guid)), self.attributes, self.revision, 
            self.size, self.size
        )
        print blue("%s  Firmware Volume Blocks: " % (ts)),
        for block_size, block_length in self.blocks:
            print "(%d, 0x%x)" % (block_size, block_length),
        print ""
        
        for _ffs in self.firmware_filesystems:
            _ffs.showinfo(ts + " ")
    
    def dump(self, parent= ""):
        if len(self.data) == 0:
            return 
        
        path = os.path.join(parent, "volume-%s.fv" % self.name)
        dump_data(path, self._data)

        for _ffs in self.firmware_filesystems:
            _ffs.dump(os.path.join(parent, "volume-%s" % self.name))

