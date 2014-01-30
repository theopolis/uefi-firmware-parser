# -*- coding: utf-8 -*-

import os
import sys, struct
#from backports import lzma
#import pylzma
import tempfile
import subprocess
import uuid

from .utils import *
from .structs import *
from .contrib import efi_decompressor

def _get_file_type(file_type):
    return EFI_FILE_TYPES[file_type] if file_type in EFI_FILE_TYPES else ("unknown", "unknown")

def _get_section_type(section_type):
    return EFI_SECTION_TYPES[section_type] if section_type in EFI_SECTION_TYPES else ("unknown", "unknown.bin")

def _dump_data(name, data):
    try:
        with open(name, 'wb') as fh: fh.write(data)
        print "Wrote: %s" % (red(name))
    except Exception, e:
        print "Error: could not write (%s), (%s)." % (name, str(e))

def fguid(s):
    a, b, c, d, e = struct.unpack("<IHHH6s", s)
    return "%08x-%04x-%04x-%04x-%s" % (a,b,c,d,''.join('%02x'%ord(c) for c in e))

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

def search_firmware_volumes(data):
    potential_volumes = []
    for aligned_start in xrange(32, len(data), 16):
        if data[aligned_start : aligned_start + 4] == '_FVH':
            potential_volumes.append(aligned_start)
    return potential_volumes
    pass

class FirmwareObject(object):
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
            "label": self.label,
            "guid": self.guid_label,
            "type": self.type_label,
            "content": self.content if include_content else "",
            "attrs": self.attrs_label
        }   
    
    def iterate_objects(self, include_content= False):
        objects = []
        for _object in self.objects:
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

            #print "GUID %s offset %d" % (fguid(self.guid), subsection_offset)
            subsection = FirmwareFileSystemSection(self.data[subsection_offset:], self.guid)
            if subsection.size == 0: break
            subsection.process()
            self.subsections.append(subsection)

            #print subsection.type, subsection.size
            subsection_offset += subsection.size

    def process(self): pass
    def showinfo(self, ts= '', index=-1): pass

    def dump(self, parent= "", index=0):
    #    #print "Dumping: " % os.path.join(parent, "subsection%d" % index)
        #name = os.path.join(parent, "subsection.%s" % )

    #    _dump_data("%s.%s" % (name, 99), self.data)
        for i, subsection in enumerate(self.subsections):
            subsection.dump(parent, i)


class CompressedSection(EfiSection):
    #parsed_objects = None
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
    
    def _p7zip(self, data):
        '''Use 7z to decompress an LZMA-compressed section.'''
        uncompressed_data = None
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp.write(data)
            temp.flush()
            subprocess.call(["7zr", "-o/tmp", "e", temp.name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with open("%s~" % temp.name, 'r') as fh: uncompressed_data = fh.read()
        
        if uncompressed_data is not None:
            self.data= uncompressed_data[:]
    
    def _try_again(self, data, offset):
        '''Warning: this is a massive hack.'''
        object = FirmwareFileSystemSection(self.data[offset+2:], self.guid)
        return object
    
    def process(self):
        if self.type == 0x00:
            '''No compression.'''
            self.data = self.uncompressed_data
        
        if self.type == 0x01:
            '''EFI or Tiano compression.'''
            #print "Debug: attempting EFI decompression"
            self.data = efi_decompressor.Decompress(self.uncompressed_data)
            
        if self.type == 0x02:
            self._p7zip(self.uncompressed_data)
        
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
        #print "FFGS %s" % fguid(self.guid), uuid.UUID(fguid(self.guid)) == self._CHAR_GUID
        if uuid.UUID(fguid(self.guid)) == self._CHAR_GUID:
            self.guid_header = self.data[:12]
            self.name = uefi_name(self.data[12:])
        pass

    def showinfo(self, ts='', index=-1): 
        #print fguid(self.guid)
        #hex_dump(self.data)
        if self.name is not None:
            print "%sGUID Description: %s" % (ts, purple(self.name))
        pass

    pass

class GuidDefinedSection(EfiSection):
    """
    A firmware file section type (GUID-defined)

    struct { UCHAR GUID[16]; short offset; short attrs; }
    """
    LZMA_COMPRESSED_GUID = uuid.UUID("{ee4e5898-3914-4259-9d6e-dc7bd79403cf}")
    _STATIC_GUID = "\xb0\xcd\x1b\xfc\x31\x7d\xaa\x49\x93\x6a\xa4\x60\x0d\x9d\xd0\x83"

    def __init__(self, data):
        self.guid, self.offset, self.attrs = struct.unpack("<16sHH", data[:0x18])
        self.data = data[0x18:]

        self.subsections = []

    @property
    def objects(self):
        return self.subsections

    def process(self):
        if uuid.UUID(fguid(self.guid)) == self.LZMA_COMPRESSED_GUID:
            print "Debug: Found LZMA GUID-defined section"

        elif self.guid == self._STATIC_GUID:
            self.process_subsections()
        pass

    pass

class FirmwareFileSystemSection(FirmwareObject):
    """
    A firmware file section
    
    struct { UINT8 Size[3]; EFI_SECTION_TYPE Type; } EFI_COMMON_SECTION_HEADER;
    """
    
    parsed_object = None
    '''For object sections, keep track of each.'''
    
    def __init__(self, data, guid):
        self.guid= guid
        
        header = data[:0x4]
        #print ["0x%x" % ord(c) for c in hdr]

        try:
            self.size, self.type = struct.unpack("<3sB", header)
            self.size = struct.unpack("<I", self.size + "\x00")[0]
        except Exception, e:
            print "Error: invalid FirmwareFileSystemSection header, expected size 4, got (%d)." % len(header)
            raise e
        
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
            #compressed_section.process()
            self.parsed_object = compressed_section

        elif self.type == 0x02: # GUID-defined
            guid_defined = GuidDefinedSection(self.data)
            #guid_defined.process()
            self.parsed_object = guid_defined
            
        elif self.type == 0x15: # user interface name
            self.name = uefi_name(self.data)
        
        elif self.type == 0x17: # firmware-volume
            fv = FirmwareVolume(self.data, self.guid)
            #fv.process()    
            self.parsed_object = fv
        
        elif self.type == 0x18: # freeform GUID
            freeform_guid = FreeformGuidSection(self.data)
            #freeform_guid.process()
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
        
        #for i, section in enumerate(self.subsections):
        #    section.showinfo(ts + '  ', i)
        #if self.type == 0x02 and self.subsections is not None:
        #    print ts+" CRC32 subsection container:"
        #    for i, s in enumerate(self.subsections):
        #        print "%s type 0x%02x, size 0x%x" % (blue("%s Subsection %d:" % (ts, i)), s.type, s.size)
        #        s.showinfo(ts+"   ")
                
    def dump(self, parent= "", index= 0):
        _dump_data(os.path.join(parent, "section%d.%s" % (index, _get_section_type(self.type)[1])), self.data)

        if self.parsed_object is None: return

        self.parsed_object.dump(os.path.join(parent, "section%d" % index))
        #for i, section in enumerate(self.parsed_object.subsections):
        #    section.dump(os.path.join(parent, "section%d.%d" % (index, i)))


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
                _dump_data(os.path.join(parent, "blob-%s.raw" % i), blob)

        if self.sections is not None:
            for i, section in enumerate(self.sections):
                section.dump(parent, index= i)

class FirmwareFileSystem(FirmwareObject):
    """
    A potential UEFI firmware filesystem data stream, comprised of fimrware file system (FSS) sections.
    The FFS is a specific GUID within the FirmwareVolume  
    
    FFS GUID: D9 54 93 7A 68 04 4A 44 81 CE 0B F6 17 D8 90 DF
    """
    guid = "D954937A68044A4481CE0BF617D890DF".decode("hex")
    
    def __init__(self, data):
        self.files = []
        self.data = data
    
    @property
    def objects(self):
        return self.files or []
    
    def process(self):
        '''Search for a 16-byte header that does not contain all 0xFF.'''
        while len(self.data) >= 16 and self.data[:16] != ("\xff"*16):
            firmware_file = FirmwareFile(self.data)
            if firmware_file.size < 16:
                '''This is a problem, the file was corrupted.'''
                break
            
            firmware_file.process()
            self.files.append(firmware_file)
            
            self.data = self.data[(firmware_file.size + 7) & (~7):]
    
    def showinfo(self, ts= ''):
        for i, firmware_file in enumerate(self.files):
            #print ts + "File %d:" % i
            firmware_file.showinfo(ts + ' ', index=i)
    
    def dump(self, parent= ""):
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
    
    name = None
    '''An optional name or offset of the firmware volume.'''
    
    block_map = None
    '''An empty block set.'''
    
    firmware_filesystems = None
    
    def __init__(self, data, name= "volume"):
        self.name = ""
        self.data = ""
        
        header = data[:self._HEADER_SIZE]

        self.rsvd, self.guid, self.size, self.magic, self.attributes, self.hdrlen, self.checksum, self.rsvd2, self.revision = struct.unpack("<16s16sQ4sIHH3sB", header)
        
        self.blocks = []
        self.block_map = ""
        if self.magic != '_FVH':
            print "Error: this is not a firmware volume, bad magic."
            return 

        if len([ord(c) for c in self.rsvd if ord(c) == 0]) < 8:
            print "Error: this may not be a firmware volume, reserved is not 0?"
            return
        
        data = data[:self.size]
        self.data = data[self.hdrlen:]
        self.block_map = data[self._HEADER_SIZE:self.hdrlen]
    
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
        
        path = os.path.join(parent, "volume-%s.fv" % fguid(self.guid))
        _dump_data(path, self.data)

        for _ffs in self.firmware_filesystems:
            _ffs.dump(os.path.join(parent, "volume-%s" % fguid(self.guid)))

