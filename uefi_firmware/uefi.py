# -*- coding: utf-8 -*-

import os
import sys, struct
import uuid

from .utils import *
from .guids import get_guid_name
from .structs.uefi_structs import *
import efi_compressor

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

def compare(data1, data2):
    from hashlib import md5
    md5_1 = md5(data1).hexdigest()
    md5_2 = md5(data2).hexdigest()
    if (md5_1 != md5_2):
        print "%s != %s" % (red(md5_1), red(md5_2))
        return False
    return True

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

            try:
                subsection = FirmwareFileSystemSection(self.data[subsection_offset:], self.guid)
            except struct.error, e:
                break
            if subsection.size == 0: break
            subsection.process()
            self.subsections.append(subsection)

            subsection_offset += subsection.size

    def build(self, generate_checksum= False, debug= False):
        raise Exception("Cannot build from unknown section type!")

    def process(self): pass
    def showinfo(self, ts= '', index=-1): pass

    def dump(self, parent= "", index=0):
        for i, subsection in enumerate(self.subsections):
            subsection.dump(parent, i)


class CompressedSection(EfiSection):
    name = None
    
    ATTR_NOT_COMPRESSED         = 0x00
    ATTR_STANDARD_COMPRESSION   = 0x01
    ATTR_CUSTOMIZED_COMPRESSION = 0x02

    def __init__(self, data, guid):
        self.guid= guid
        self.data= None
        self.parsed_objects = []
        
        # http://dox.ipxe.org/PiFirmwareFile_8h_source.html
        self.decompressed_size, self.type = struct.unpack("<Ic", data[:5])
        self.type = ord(self.type)
        # A special compression type to determine (EFI/Tiano if type= 0x01).
        self.subtype = 0
        
        # Advance the byte pointer through the header
        self.compressed_data = data[5:]
        self.attrs = {"decompressed_size": self.decompressed_size, "type": self.type}
        
        pass
    
    def process(self):        
        if self.type == 0x01:
            ### Tiano or Efi compression, unfortunately these are identified by the same byte
            try:
                self.data = efi_compressor.EfiDecompress(self.compressed_data, len(self.compressed_data))
                self.subtype = 0x01
            except Exception, e:
                try:
                    self.data = efi_compressor.TianoDecompress(self.compressed_data, len(self.compressed_data))
                    self.subtype = 0x02
                except Exception, e:
                    #print "Error: cannot decompress (%s) (%s)." % (fguid(self.guid), str(e))
                    raise Exception("Cannot EFI decompress GUID (%s), %s" % (fguid(self.guid), str(e)))
                    return

        if self.type == 0x00:
            '''No compression.'''
            self.data = self.compressed_data

        if self.type == 0x02:
            try:
                self.data = efi_compressor.LzmaDecompress(self.compressed_data, len(self.compressed_data))
            except Exception, e:
                raise Exception("Cannot LZMA decompress GUID (%s), %s" % (fguid(self.guid), str(e)))
                return
            #self.data = p7z_extract(self.compressed_data)
            
        if self.data is None:
            '''No data was uncompressed.'''
            return
        
        self.process_subsections()
        pass

    def build(self, generate_checksum= False, debug= False):
        #print "Building compression type=(%d, %d)" % (self.type, self.subtype)

        data = ""
        for i, section in enumerate(self.subsections):
            subsection_size, subsection_data = section.build(generate_checksum)
            data += subsection_data
            if (i+1 < len(self.subsections)):
                ### Nibble-align inter-section subsections
                data += "\x00" * (((subsection_size + 3)&(~3)) - subsection_size)

        ### Pad the pre-compression data
        trailling_bytes = len(self.data) - len(data)
        if trailling_bytes > 0:
            data += '\x00' * trailling_bytes

        if self.type == 0x01:
            if self.subtype == 0x01:
                data = str(efi_compressor.EfiCompress(data, len(data)))
            elif self.subtype == 0x02:
                data = str(efi_compressor.TianoCompress(data, len(data)))
        elif self.type == 0x02:
            data = str(efi_compressor.LzmaCompress(data, len(data)))
        elif self.type == 0x00:
            pass

        ### Debug compare-compressed data
        if not compare(self.compressed_data, data):
            print "  old compress size=%d, new=%d, type=(%d, %d)" % (len(self.compressed_data), len(data), self.type, self.subtype)   
            pass

        header = struct.pack("<Ic", self.decompressed_size, chr(self.type))
        return header + data
        pass

    def showinfo(self, ts):
        if self.name is not None:
            print "%s %s" % (blue("%sCompressed Name:" % ts), purple(self.name))
        for i, _object in enumerate(self.subsections):
            _object.showinfo(ts, i)
        
        pass

class VersionSection(EfiSection):

    def __init__(self, data):
        self.build_number = struct.unpack("<16s", self.data[:16])
        pass

class FreeformGuidSection(EfiSection):
    """
    A firmware file section type (free-form GUID)

    struct { UCHAR GUID[16]; }
    """
    
    CHAR_GUID = "059ef06e-c652-4a45-be9f-5975e369461c"
    name = None

    def __init__(self, data):
        self.guid = struct.unpack("<16s", data[:16])[0]
        self.data = data[16:]

    def process(self):
        if fguid(self.guid) == self.CHAR_GUID:
            self.guid_header = self.data[:12]
            self.name = uefi_name(self.data[12:])
        pass

    def build(self, generate_checksum= False, debug= False):
        #print "Building FreeformGUID: %s" % green(fguid(self.guid))

        header = struct.pack("<16s", self.guid)
        return header + self.data

    def showinfo(self, ts='', index=-1): 
        #print "%sGUID: %s" % (ts, green(fguid(self.guid)))
        if self.name is not None:
            print "%sGUID Description: %s" % (ts, purple(self.name))
        pass

    pass

class GuidDefinedSection(EfiSection):
    """
    A firmware file section type (GUID-defined)

    struct { UCHAR GUID[16]; short offset; short attrs; }
    """

    ATTR_PROCESSING_REQUIRED = 0x01
    ATTR_AUTH_STATUS_VALID   = 0x02

    def __init__(self, data):
        self.guid, self.offset, self.attrs = struct.unpack("<16sHH", data[:20])

        ### A guid-defined section includes an offset
        self.preamble = data[20:self.offset]
        self.data = data[self.offset:]

        self.subsections = []

    @property
    def objects(self):
        return self.subsections

    def process(self):
        def parse_volume():
            fv = FirmwareVolume(self.data)
            if fv.valid_header:
                fv.process()
                self.subsections = [fv]
                return True
            return False

        if fguid(self.guid) == FIRMWARE_GUIDED_GUIDS["LZMA_COMPRESSED"]:
            try:
                self.data = efi_compressor.LzmaDecompress(self.data, len(self.data))
            except Exception, e:
                raise "Cannot decompress GuidDefinedSection, %s" % (str(e))
                return
            self.process_subsections()
        elif fguid(self.guid) == FIRMWARE_GUIDED_GUIDS["STATIC_GUID"]:
            self.process_subsections()
            if len(self.subsections) == 0:
                ### There were no subsections parsed, treat as a firmware volume
                parse_volume()
        elif fguid(self.guid) == FIRMWARE_GUIDED_GUIDS["FIRMWARE_VOLUME"]:
            parse_volume()
        else:
            parse_volume()
        pass

    def build(self, generate_checksum= False, debug= False):
        #print "Building GUID-defined: %s" % green(fguid(self.guid))

        data = ""
        for section in self.subsections:
            data += section.build(generate_checksum)

        if fguid(self.guid) == LZMA_COMPRESSED_GUID:
            data = efi_compressor.LzmaCompress(data, len(data))
            pass

        header = struct.pack("<16sHH", self.guid, self.offset, self.attrs)
        return header + data

    def showinfo(self, ts='', index= 0):
        #print "%sGUID: %s" % (ts, green(fguid(self.guid)))
        print "%s%s %s offset= 0x%x attrs= 0x%x" % (
            ts, blue("Guid-Defined:"), green(fguid(self.guid)),
            self.offset, self.attrs
        )
        if len(self.subsections) > 0:
            for i, section in enumerate(self.subsections):
                section.showinfo("%s  " % ts, index= i)

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

        self.valid_header = True
        try:
            self.size, self.type = struct.unpack("<3sB", header)
            self.size = struct.unpack("<I", self.size + "\x00")[0]
        except Exception, e:
            print "%s: invalid FirmwareFileSystemSection header, expected size 4, got (%d)." % (red("Error"), len(header))
            self.valid_header = False 
            return          
            #raise e

        self._data = data[:self.size]
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

    def build(self, generate_checksum= False, debug= False):
        #print "Building section (%s): %s" % (_get_section_type(self.type)[1], green(fguid(self.guid)))

        data = ""
        ### Add section data (either raw, or a partitioned section)
        if self.parsed_object is not None:
            data = self.parsed_object.build(generate_checksum)
        else:
            data = self.data

        ### Pad the data and check for potential overflows.
        size = self.size
        trailling_bytes = (self.size-4) - len(data)
        if trailling_bytes > 0:
            data += '\x00' * trailling_bytes
        if trailling_bytes < 0:
            size = self.size - trailling_bytes
            #raise Exception("FileSystemSection GUID %s has overflown %d bytes." % (fguid(self.guid), trailling_bytes*-1))
            pass

        string_size = struct.pack("<I", size)
        header = struct.pack("<3sB", string_size[:3], self.type)
        return size, header + data
        pass

    def showinfo(self, ts='', index=-1):
        print "%s type 0x%02x, size 0x%x (%d bytes) (%s section)" % (
            blue("%sSection %d:" % (ts, index)), 
            self.type, self.size, self.size,
            _get_section_type(self.type)[0]
        )
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
        self._data = data[:self.size]
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
        while len(section_data) >= 4:
            file_section = FirmwareFileSystemSection(section_data, self.guid)
            if not file_section.valid_header:
                break
            if file_section.size <= 0:
                '''This is not expected, something bad happened while parsing.'''
                print "Error: file section size <= 0 (%d)." % file_section.size
                break
            
            file_section.process()
            self.sections.append(file_section)

            section_data = section_data[(file_section.size + 3)&(~3):]
        pass

    def build(self, generate_checksum= False, debug= False):
        #print "Building file: %s" % green(fguid(self.guid))
        
        data = ""
        for i, section in enumerate(self.sections):
            section_size, section_data = section.build(generate_checksum)
            data += section_data
            if (i+1 < len(self.sections)):
                ### Nibble-align inter-file sections
                data += "\x00" * (((section_size + 3)&(~3)) - section_size)

        for blob in self.raw_blobs:
            data += blob

        ### Maining to support ffs-padding
        if len(self.raw_blobs) == 0 and len(self.sections) == 0:
            data = self.data

        if generate_checksum:
            pass

        size = self.size
        trailling_bytes = size - (len(data) + 24)
        if trailling_bytes < 0:
            print "%s adding %s-bytes to GUID: %s" % (red("Warning"), red(trailling_bytes*-1), red(fguid(self.guid))) 
            size += (trailling_bytes * -1)

        string_size = struct.pack("<I", size)
        header = struct.pack("<16sHBB3sB", self.guid, self.checksum, self.type, self.attributes, string_size[:3], self.state)
        return size, header + data

    def showinfo(self, ts='', index= "N/A"):
        guid_name = get_guid_name(self.guid)

        print "%s %s type 0x%02x, attr 0x%02x, state 0x%02x, size 0x%x (%d bytes), (%s)" % (
            blue("%sFile %s:" % (ts, index)),
            "%s" % ("%s" % green(fguid(self.guid)) if guid_name is None \
                else "%s (%s)" % (green(fguid(self.guid)), purple(guid_name))), 
            self.type, self.attributes, self.state ^ 0xFF, 
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

        ### Overflow data is non-file data within the filesystem
        self.overflow_data = ""
    
    @property
    def objects(self):
        return self.files or []
    
    def process(self):
        '''Search for a 24-byte header that does not contain all 0xFF.'''
        
        data = self._data
        while len(data) >= 24 and data[:24] != ("\xff"*24):
            firmware_file = FirmwareFile(data)

            if firmware_file.size < 24:
                '''This is a problem, the file was corrupted.'''
                break
            
            firmware_file.process()
            self.files.append(firmware_file)
            
            #print "pos=%d, size=%s padd=%d" % (len(self._data)-len(data), firmware_file.size, ((firmware_file.size + 7) & (~7)) - firmware_file.size)
            data = data[(firmware_file.size + 7) & (~7):]

        if len(data) > 0:
            ### There is overflow data
            self.overflow_data = data
        pass
    
    def build(self, generate_checksum= False, debug= False):

        ### Generate the file system data as an unstructed set of file data.
        data = ""
        for firmware_file in self.files:
            file_size, file_data = firmware_file.build(generate_checksum)
            data += file_data
            data += "\xFF" * (((file_size + 7) & (~7)) - file_size)

        data += self.overflow_data

        if len(data) != len(self._data):
            print "ffs size mismatch old=%d new=%d %d" % (len(self._data), len(data), len(self._data)-len(data))

        return data
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

    name = None
    '''An optional name or offset of the firmware volume.'''
    
    block_map = None
    '''An empty block set.'''
    
    firmware_filesystems = None
    raw_objects = None
    
    def __init__(self, data, name= "volume"):
        self.name = name
        self.valid_header = False

        try:
            header = data[:self._HEADER_SIZE]
            self.rsvd, self.guid, self.size, self.magic, self.attributes, self.hdrlen, self.checksum, self.rsvd2, self.revision = struct.unpack("<16s16sQ4sIHH3sB", header)
        except Exception, e:
            print "Error: cannot parse FV header (%s)." % str(e)
            return

        if fguid(self.guid) not in FIRMWARE_VOLUME_GUIDS:
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
        
        data = self.data
        self.firmware_filesystems = []
        self.raw_objects = []
        for block in self.blocks:
            ### If this is an NVRAM volume, there is no FFS/FFs.
            if fguid(self.guid) == FIRMWARE_VOLUME_GUIDS[2]:
                self.raw_objects.append(data[:block[0]* block[1]])
            else:
                firmware_filesystem = FirmwareFileSystem(data[:block[0] * block[1]])
                firmware_filesystem.process()            
                self.firmware_filesystems.append(firmware_filesystem)
            data = data[block[0] * block[1]:]

    def build(self, generate_checksum= False, debug= False):
        
        ### Generate blocks from FirmwareFileSystems
        data = ""
        for filesystem in self.firmware_filesystems:
            #print "Building filesystem"
            data += filesystem.build(generate_checksum)

        ### Generate block map from original block map (assume no size change)
        block_map = ""
        for block in self.blocks:
            #print "Packing block"
            block_map += struct.pack("<II", block[0], block[1])
        ### Add a trailing-NULL to the block map
        block_map += "\x00"*8

        if generate_checksum:
            pass

        ### Assume no size change
        header = struct.pack("<16s16sQ4sIHH3sB", self.rsvd, self.guid, self.size, self.magic, self.attributes, self.hdrlen, self.checksum, self.rsvd2, self.revision)
        return header + block_map + data
        pass
    
    def showinfo(self, ts='', index= None):
        if not self.valid_header or len(self.data) == 0:
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
        for raw in self.raw_objects:
            print "%s%s NVRAM" % ("%s  " % ts, blue("Raw section:"))
    
    def dump(self, parent= "", index= None):
        if len(self.data) == 0:
            return 
        
        path = os.path.join(parent, "volume-%s.fv" % self.name)
        dump_data(path, self._data)

        for _ffs in self.firmware_filesystems:
            _ffs.dump(os.path.join(parent, "volume-%s" % self.name))

class FirmwareCapsule(FirmwareObject):
    """
    struct EFI_CAPSULE_HEADER {
        UCHAR:  CapsuleGUID[16]
        UINT32: HeaderSize
        UINT32: Flags
        UINT32: CapsureImageSize
        UINT32: SequenceNumber
        UCHAR:  InstanceGUID[16]
        UINT32: OffsetToSplitInformation
        UINT32: OffsetToCapsuleBody
        UINT32: OffsetToOemDefinedHeader
        UINT32: OffsetToAuthorInformation
        UINT32: OffsetToRevisionInformation
        UINT32: OffsetToShortDescription
        UINT32: OffsetToLongDescription
        UINT32: OffsetToApplicableDevices
    }
    """
    capsule_body = None


    def __init__(self, data, name= "Capsule"):
        self.name = name
        self.valid_header = True
        self.data = None

        self.capsule_guid = data[:16]
        self.guid = "\x00"*16
        if fguid(self.capsule_guid) not in FIRMWARE_CAPSULE_GUIDS:
            self.valid_header = False
            return

        try:
            self.parse_capsule_header(data[16:])
        except:
            self.valid_header = False
            return

        ### Set data (original, and body content)
        self._data = data
        self.data = data[self.header_size:]

        pass

    def parse_capsule_header(self, data):
        if fguid(self.capsule_guid) == FIRMWARE_CAPSULE_GUIDS[0]: 
            ### EFICapsule    
            self.size, self.flags, self.image_size, self.seq_num = struct.unpack("<IIII", data[:4*4])
            self.guid = data[16:32]
            split_info, capsule_body, oem_header, author_info, revision_info, short_desc, long_desc, compatibility = struct.unpack("<" + "I"*8, data[32:32+4*8])

            ### Store offsets
            self.offsets = {
                "capsule_body":  capsule_body,
                "split_info":    split_info,
                "oem_header":    oem_header,
                "author_info":   author_info,
                "revision_info": revision_info,
                "short_desc":    short_desc,
                "long_desc":     long_desc,
                "compatibility": compatibility
            }
        elif fguid(self.capsule_guid) == FIRMWARE_CAPSULE_GUIDS[1]:
            ### EFI2Capsule
            self.size, self.flags, self.image_size = struct.unpack("<III", data[:4*3])
            fv_image, oem_header = struct.unpack("<HH", data[12:12+4])
            self.offsets = {
                "capsule_body": fv_image,
                "oem_header": oem_header,
                "author_info": 0
            }
        elif fguid(self.capsule_guid) == FIRMWARE_CAPSULE_GUIDS[2]:
            ### UEFI Capsule
            self.size, self.flags, self.image_size = struct.unpack("<III", data[:4*3])
            self.offsets = {
                "capsule_body": self.size,
                "oem_header": 0,
                "author_info": 0
            }
        self.header_size = self.size
        pass

    @property
    def objects(self):
        return [self.capsule_body]

    def process(self):
        fv = FirmwareVolume(self.data[self.offsets["capsule_body"]- self.header_size:])
        if not fv.valid_header:
            return

        fv.process()
        self.capsule_body = fv
        pass

    def showinfo(self, ts= '', index= None):
        if not self.valid_header or len(self.data) == 0:
            return

        print "%s %s flags 0x%08x, size 0x%x (%d bytes)" % (
            blue("%sFirmware Capsule:" % (ts)),
            "%s/%s" % (green(fguid(self.capsule_guid)), green(fguid(self.guid))), 
            self.flags, self.size, self.size
        )
        print "%s  Details: body= 0x0%x, oem= 0x0%x, author= 0x0%x" % (
            ts, self.offsets["capsule_body"], self.offsets["oem_header"], self.offsets["author_info"]
        )

        if self.capsule_body is not None:
            self.capsule_body.showinfo(ts)
        pass