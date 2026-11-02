# -*- coding: utf-8 -*-

# Instructions:
# 1. Download, and setup your edk2
# 2. make -C <edk2>/BaseTools/Source/C
# 3. The needed binaries are at <edk2>/BaseTools/Source/C/bin/
# 4. GenFds  -f Testing/testing.fdf -o Testing -t GCC46 -b DEBUG -a X64 -p
# OvmfPkg/OvmfPkgX64.dsc


import os
import re

from ..uefi import FirmwareVolume, FirmwareFile, FirmwareFileSystemSection
from ..structs.uefi_structs import EFI_FILE_TYPES, EFI_SECTION_TYPES, EFI_COMPRESSION_TYPES
from ..utils import dump_data, sguid

FV_BUFFER = '''
[FV.FV_{name}]
BlockSize          = 0x10000
FvAlignment        = 16
ERASE_POLARITY     = 1
MEMORY_MAPPED      = TRUE
STICKY_WRITE       = TRUE
LOCK_CAP           = TRUE
LOCK_STATUS        = TRUE
WRITE_DISABLED_CAP = TRUE
WRITE_ENABLED_CAP  = TRUE
WRITE_STATUS       = TRUE
WRITE_LOCK_CAP     = TRUE
WRITE_LOCK_STATUS  = TRUE
READ_DISABLED_CAP  = TRUE
READ_ENABLED_CAP   = TRUE
READ_STATUS        = TRUE
READ_LOCK_CAP      = TRUE
READ_LOCK_STATUS   = TRUE

{files}
'''

FILE_BUFFER = '''
FILE {type} = {guid} {options} {{
{sections}
}}
'''

SECTION_GUIDED_BUFFER = '''\
{ts}SECTION GUIDED {guid} {auth} {{
{subsections}
{ts}}}
'''

SECTION_COMPRESSED_BUFFER = '''\
{ts}SECTION COMPRESS {type} {{
{subsections}
{ts}}}
'''

SECTION_STRING_BUFFER = '''\
{ts}SECTION {type} = "{value}"
'''

SECTION_LEAF_BUFFER = '''\
{ts}SECTION {type} = {value}
'''

SECTION_UNSUPPORTED_BUFFER = '''\
{ts}# Unsupported section: {value}
'''


def oguid(guid):
    return sguid(guid)


def fdf_string(value):
    '''Return value with the characters that would end an FDF string, or
    start a new line, replaced.'''
    return re.sub(r'["\\\x00-\x1f\x7f]', "_", "%s" % value)


class GeneratorException(Exception):

    def __init__(self, _object):
        message = "Cannot generate from unsupported type (%s)." % type(_object)
        Exception.__init__(self, message)


class RawSectionGenerator(object):

    def __init__(self, path, ts=''):
        self.embedded = []
        template = SECTION_LEAF_BUFFER

        self.output = template.format(
            ts=ts,
            type="RAW",
            value=path
        )
        pass


class UnsupportedSectionGenerator(object):

    def __init__(self, description, ts=''):
        self.embedded = []
        self.output = SECTION_UNSUPPORTED_BUFFER.format(
            ts=ts, value=fdf_string(description))


class SectionGenerator(object):

    def __init__(self, firmware_section=None, ts=''):
        self.subsections = []
        self.embedded = []
        self.ts = ts

        if firmware_section is not None:
            if not isinstance(firmware_section, FirmwareFileSystemSection):
                raise GeneratorException(firmware_section)
            self._generate(firmware_section)
        pass

    def generate_leaf(self, firmware_section):
        template = SECTION_LEAF_BUFFER
        value = firmware_section.path
        section_type = EFI_SECTION_TYPES.get(
            firmware_section.type, (None, None, None))[2]
        if section_type is None:
            self.output = UnsupportedSectionGenerator(
                "type 0x%02x" % firmware_section.type, self.ts).output
            return

        if firmware_section.type == 0x17:  # firmware volume
            if not isinstance(firmware_section.parsed_object, FirmwareVolume):
                self.output = UnsupportedSectionGenerator(
                    "volume that could not be parsed", self.ts).output
                return
            name = oguid(firmware_section.guid).replace("-", "_")
            self.embedded.append(
                FirmwareVolumeGenerator(firmware_section.parsed_object, name))
            value = "FV_%s" % name
            pass

        if firmware_section.type in [0x14, 0x15]:
            template = SECTION_STRING_BUFFER
            value = fdf_string(firmware_section.name)

        self.output = template.format(
            ts=self.ts,
            type=section_type,
            value="%s" % value
        )

    def _generate_subsections(self, parsed_object):
        '''Generate each subsection, returning their combined output.'''
        for subsection in parsed_object.subsections:
            ts = "  %s" % self.ts
            if isinstance(subsection, FirmwareFileSystemSection):
                self.subsections.append(SectionGenerator(subsection, ts=ts))
            elif isinstance(subsection, FirmwareVolume):
                # A GUID-defined section may hold a volume, not sections.
                name = oguid(subsection.fvname if hasattr(subsection, "fvname")
                             else self.guid).replace("-", "_")
                generator = SectionGenerator(ts=ts)
                generator.embedded.append(
                    FirmwareVolumeGenerator(subsection, name))
                generator.output = SECTION_LEAF_BUFFER.format(
                    ts=ts, type="FV_IMAGE", value="FV_%s" % name)
                self.subsections.append(generator)
            else:
                self.subsections.append(UnsupportedSectionGenerator(
                    "data that could not be parsed", ts))

        subsection_output = ""
        for subsection in self.subsections:
            for embedded in subsection.embedded:
                self.embedded.append(embedded)
            subsection_output += "%s" % subsection.output
        return subsection_output

    def generate_compressed(self, firmware_section):
        template = SECTION_COMPRESSED_BUFFER
        compressed = firmware_section.parsed_object
        compression = EFI_COMPRESSION_TYPES.get(compressed.type)
        if compression is None:
            self.output = UnsupportedSectionGenerator(
                "compression type 0x%02x" % compressed.type, self.ts).output
            return

        self.output = template.format(
            ts=self.ts,
            type=compression,
            subsections=self._generate_subsections(compressed)
        )

    def generate_guided(self, firmware_section):
        template = SECTION_GUIDED_BUFFER
        guided = firmware_section.parsed_object

        self.output = template.format(
            ts=self.ts,
            guid=oguid(guided.guid),
            auth="",
            subsections=self._generate_subsections(guided)
        )

    def _generate(self, firmware_section):
        self.guid = firmware_section.guid
        if firmware_section.parsed_object is None and \
                firmware_section.type in (0x01, 0x02):
            # The section's data could not be parsed.
            self.output = UnsupportedSectionGenerator(
                "type 0x%02x that could not be parsed" % firmware_section.type,
                self.ts).output
        elif firmware_section.type == 0x01:  # compressed
            self.generate_compressed(firmware_section)
        elif firmware_section.type == 0x02:  # guided
            self.generate_guided(firmware_section)
        else:
            self.generate_leaf(firmware_section)
        pass


class FirmwareFileGenerator(object):

    def __init__(self, firmware_file=None, type_label=None, guid=None):
        self.embedded = []
        self.sections = []

        self.type_label = type_label
        self.guid_label = guid
        if firmware_file is not None:
            if not isinstance(firmware_file, FirmwareFile):
                raise GeneratorException(firmware_file)
            self._generate(firmware_file)
        pass

    def add_section(self, firmware_section):
        self.sections.append(SectionGenerator(firmware_section, ts='  '))

    def _generate(self, firmware_file):
        self.output = ""

        if firmware_file.type == 0xf0:
            # Do not add FFS padding files
            return

        self.type_label = EFI_FILE_TYPES.get(
            firmware_file.type, (None, None, "0x%02X" % firmware_file.type))[2]
        self.guid_label = oguid(firmware_file.guid)

        if firmware_file.type == 0x01:
            # The file's body, written next to the rest of its dump.
            path = os.path.join(firmware_file.dump_path, "file.raw")
            dump_data(path, firmware_file.data)
            self.sections.append(RawSectionGenerator(path, ts='  '))
        else:
            for section in firmware_file.sections:
                self.add_section(section)

        section_output = ""
        for section in self.sections:
            section_output += "%s" % section.output
            for embedded in section.embedded:
                #self.output += embedded.output
                self.embedded.append(embedded)

        template = FILE_BUFFER
        self.output = template.format(
            type=self.type_label,
            guid=self.guid_label,
            options="",
            sections=section_output
        )
        pass


class FirmwareVolumeGenerator(object):

    def __init__(self, volume=None, name="GENERIC"):
        self.files = []

        self.name = name
        if volume is not None:
            if not isinstance(volume, FirmwareVolume):
                raise GeneratorException(volume)
            self._generate(volume)
        pass

    def add_file(self, firmware_file):
        self.files.append(FirmwareFileGenerator(firmware_file))

    def _generate(self, volume):
        '''Generate buffer using volume object.'''
        self.output = ""

        # Do not generate separate block sets
        for filesystem in volume.firmware_filesystems:
            for firmware_file in filesystem.files:
                self.add_file(firmware_file)

        file_output = ""
        for firmware_file in self.files:
            for embedded in firmware_file.embedded:
                self.output += embedded.output
            file_output += "%s" % firmware_file.output
        template = FV_BUFFER
        self.output += template.format(
            name=self.name,
            files=file_output
        )
