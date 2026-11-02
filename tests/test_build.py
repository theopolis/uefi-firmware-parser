'''build() of an unchanged object gives back the bytes it was parsed from,
and a changed object gives consistent sizes and checksums.'''

import contextlib
import io
import struct
import unittest
import uuid
import zlib

from uefi_firmware import efi_compressor
from uefi_firmware.pfs import PFSFile
from uefi_firmware.structs.uefi_structs import (
    FIRMWARE_GUIDED_GUIDS, FIRMWARE_VOLUME_GUIDS)
from uefi_firmware.uefi import (
    CompressedSection, FirmwareFile, FirmwareFileSystem,
    FirmwareFileSystemSection, FirmwareVolume,
    GuidDefinedSection, calculate_checksum8, calculate_checksum16)

FILE_GUID = uuid.UUID("9e21fd93-9c72-4c15-8c4b-e77f1db2d792").bytes_le
OTHER_GUID = uuid.UUID("01234567-89ab-4def-8123-456789abcdef").bytes_le
ERASE_POLARITY = 0x800


def guid_bytes(name, table=FIRMWARE_GUIDED_GUIDS):
    return uuid.UUID(table[name]).bytes_le


def make_section(section_type, body):
    size = 4 + len(body)
    return struct.pack("<I", size)[:3] + bytes([section_type]) + body


def make_guided(guid, data, preamble=b""):
    '''A GUID-defined section's body, after the common header.'''
    offset = 4 + 20 + len(preamble)
    return guid + struct.pack("<HH", offset, 0) + preamble + data


def make_file(body, guid=FILE_GUID, file_type=0x07, attributes=0x00,
              file_checksum=0xAA):
    size = 24 + len(body)
    header = guid + struct.pack(
        "<BBBB3sB", 0, file_checksum, file_type, attributes,
        struct.pack("<I", size)[:3], 0xf8)
    return header + body


def make_volume(body=b"", size=0x1000, guid="FFS2", attributes=ERASE_POLARITY,
                blocks=None):
    if blocks is None:
        blocks = [(1, size)]
    block_map = b"".join(struct.pack("<II", *block) for block in blocks)
    block_map += b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS[guid]).bytes_le,
        size, b"_FVH", attributes, hdrlen, 0, 0, b"\x00", 2)
    return header + block_map + body.ljust(size - hdrlen, b"\xff")


def quietly(function, *args):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return function(*args)


def parse_section(data):
    section = FirmwareFileSystemSection(data, FILE_GUID)
    quietly(section.process)
    return section


def build_section(section, generate_checksum=False):
    return quietly(section.build, generate_checksum)[1]


class SectionBuildTest(unittest.TestCase):

    def test_compressed_section(self):
        # struct.pack of chr() raised struct.error for every compressed section.
        data = make_section(0x01, struct.pack("<IB", 8, 0x00) +
                            make_section(0x19, b"data"))
        section = parse_section(data)
        self.assertEqual(build_section(section), data)

    def test_guided_section_holding_a_volume(self):
        # A volume's build() returns bytes, not the (size, data) of a section.
        data = make_section(0x02, make_guided(
            guid_bytes("FIRMWARE_VOLUME"), make_volume(size=0x100)))
        section = parse_section(data)
        self.assertIsInstance(section.parsed_object.subsections[0], FirmwareVolume)
        self.assertEqual(build_section(section), data)

    def test_guided_section_with_unknown_data(self):
        # With nothing parsed from it, the data was rebuilt as zeros.
        data = make_section(0x02, make_guided(OTHER_GUID, b"signed payload"))
        section = parse_section(data)
        self.assertEqual(build_section(section), data)

    def test_compressed_data_is_kept_when_unchanged(self):
        inner = make_section(0x19, b"\x00" * 0x400)
        compressed = bytearray(efi_compressor.LzmaCompress(inner, len(inner)))
        # Another encoder's settings: a 64 KiB dictionary in place of 8 MiB.
        struct.pack_into("<I", compressed, 1, 1 << 16)
        data = make_section(0x02, make_guided(
            guid_bytes("LZMA_COMPRESSED"), bytes(compressed)))
        section = parse_section(data)
        self.assertEqual(len(section.parsed_object.subsections), 1)
        # Recompressing would give different bytes than the original encoder.
        self.assertEqual(build_section(section, True), data)


class ChangedSectionTest(unittest.TestCase):

    def change(self, data):
        '''Parse a section, replace the RAW section inside it and rebuild.'''
        section = parse_section(data)
        raw = section.parsed_object.subsections[0]
        raw.regen(make_section(0x19, b"changed data!"))
        quietly(raw.process)
        rebuilt = parse_section(build_section(section))
        return rebuilt.parsed_object

    def test_crc32_section(self):
        inner = make_section(0x19, b"original")
        data = make_section(0x02, make_guided(
            guid_bytes("STATIC_GUID"), inner,
            preamble=struct.pack("<I", zlib.crc32(inner))))
        guided = self.change(data)
        self.assertEqual(
            guided.preamble, struct.pack("<I", zlib.crc32(guided.data)))
        self.assertEqual(guided.subsections[0].data, b"changed data!")

    def test_tiano_section(self):
        # Only LZMA was recompressed; other GUIDs were written uncompressed.
        inner = make_section(0x19, b"original")
        compressed = efi_compressor.TianoCompress(inner, len(inner))
        guided = self.change(make_section(0x02, make_guided(
            guid_bytes("TIANO_COMPRESSED"), compressed)))
        self.assertEqual(guided.subsections[0].data, b"changed data!")

    def test_intel_compressed_section(self):
        # A type 2 section may have 4 bytes before its stream, and was always
        # recompressed as LZMA without them.
        inner = make_section(0x19, b"original")
        compressed = efi_compressor.TianoCompress(inner, len(inner))
        compressed_section = self.change(make_section(
            0x01, struct.pack("<IB", len(inner), 0x02) + b"INTL" + compressed))
        self.assertIsInstance(compressed_section, CompressedSection)
        self.assertEqual(compressed_section.prefix, b"INTL")
        self.assertEqual(compressed_section.decompressed_size, 4 + 13)
        self.assertEqual(
            compressed_section.subsections[0].data, b"changed data!")


class FileBuildTest(unittest.TestCase):

    def test_section_padding_is_kept(self):
        # Vendors pad sections with 0xff; the padding was rebuilt as zeros.
        body = make_section(0x19, b"a") + b"\xff" * 3 + make_section(0x19, b"b")
        firmware_file = FirmwareFile(make_file(body))
        self.assertTrue(quietly(firmware_file.process))
        self.assertEqual(firmware_file.build()[1], firmware_file._data)

    def test_bytes_after_the_last_section_are_kept(self):
        # Fewer than 4 bytes cannot hold a section, and were dropped.
        firmware_file = FirmwareFile(make_file(make_section(0x19, b"a") + b"xyz"))
        quietly(firmware_file.process)
        self.assertEqual(len(firmware_file.sections), 1)
        self.assertEqual(firmware_file.build()[1], firmware_file._data)

    def test_file_padding_is_kept(self):
        # Files were always padded with 0xff, and the last one was padded
        # past the end of an image cut short.
        first = make_file(make_section(0x19, b"a"))
        data = first + b"\x00" * (-len(first) % 8) + make_file(
            make_section(0x19, b"\x00" * 0x40))[:0x23]
        ffs = FirmwareFileSystem(data)
        quietly(ffs.process)
        self.assertEqual(len(ffs.files), 2)
        self.assertEqual(quietly(ffs.build), data)

    def test_framework_fixed_checksum(self):
        # Without a file checksum, FFS1 files use 0x5A where FFS2 uses 0xAA.
        for fixed in (0x5A, 0xAA):
            firmware_file = FirmwareFile(make_file(
                make_section(0x19, b"data"), file_checksum=fixed))
            quietly(firmware_file.process)
            header = firmware_file.build(generate_checksum=True)[1][:24]
            self.assertEqual(header[17], fixed)
            self.assertEqual(header[16], calculate_checksum8(
                header[:16] + b"\x00\x00" + header[18:23] + b"\x00"))

    def test_nvar_store_free_space(self):
        # The store kept only its variables, so the file shrank.
        variable = b"NVAR" + struct.pack("<H", 16) + b"\xff" * 3 + b"\x83" + \
            b"\x00" + b"V" * 5
        data = make_file(variable + b"\xff" * 64, file_type=0x01,
                         guid=guid_bytes("NVRAM_NVAR", FIRMWARE_VOLUME_GUIDS))
        firmware_file = FirmwareFile(data)
        self.assertTrue(quietly(firmware_file.process))
        self.assertEqual(firmware_file.build()[1], data)


class VolumeBuildTest(unittest.TestCase):

    def test_volume_that_is_not_a_file_system(self):
        # An NVRAM volume's body was rebuilt as zeros.
        data = make_volume(b"$VSS" + b"\x5a" * 60, guid="NVRAM_EVSA")
        volume = FirmwareVolume(data)
        quietly(volume.process)
        self.assertEqual(quietly(volume.build), data)

    def test_block_map_with_several_entries(self):
        # Each entry was parsed as its own file system, at the wrong offset.
        body = make_file(make_section(0x19, b"data"))
        data = make_volume(body, size=0x3000, blocks=[(1, 0x1000), (2, 0x1000)])
        volume = FirmwareVolume(data)
        self.assertTrue(quietly(volume.process))
        self.assertEqual(len(volume.firmware_filesystems), 1)
        self.assertEqual(len(volume.firmware_filesystems[0].files), 1)
        self.assertEqual(quietly(volume.build), data)

    def test_length_larger_than_the_data(self):
        # The volume was padded to its claimed length, here 2^62 bytes.
        data = bytearray(make_volume(size=0x1000))
        struct.pack_into("<Q", data, 32, 1 << 62)
        volume = FirmwareVolume(bytes(data))
        quietly(volume.process)
        self.assertEqual(quietly(volume.build), bytes(data))

    def test_file_larger_than_the_volume(self):
        # A truncated section's header was rewritten with its real size, and
        # the file was aligned by the size its header claims.
        body = make_file(make_section(0x19, b"\x00" * 0x400))[:0x100]
        data = make_volume(body, size=0x100 + 0x48)
        volume = FirmwareVolume(data)
        quietly(volume.process)
        self.assertEqual(quietly(volume.build), data)

    def test_new_checksums_with_an_odd_header_length(self):
        # The 16-bit checksum of an odd length raised ValueError.
        data = bytearray(make_volume())
        struct.pack_into("<H", data, 0x30, 0x49)
        volume = FirmwareVolume(bytes(data))
        quietly(volume.process)
        self.assertEqual(len(quietly(volume.build, True)), 0x1000)

    def test_new_checksums_with_a_block_map_larger_than_the_volume(self):
        # The volume was sized from the block map, so these entries asked for
        # 2^64 bytes. Smaller crafted sizes allocated and filled gigabytes.
        for blocks in ([(0xFFFFFFFF, 0xFFFFFFFF), (1, 0x1000)],
                       [(1, 0x1000), (0, 0xFFFFFFFF)]):
            volume = FirmwareVolume(make_volume(size=0x1000, blocks=blocks))
            quietly(volume.process)
            self.assertEqual(len(quietly(volume.build, True)), 0x1000)

    def test_new_checksums_after_the_volume_grows(self):
        data = make_volume(make_file(make_section(0x19, b"data")), size=0x1000)
        volume = FirmwareVolume(data)
        quietly(volume.process)
        firmware_file = volume.firmware_filesystems[0].files[0]
        firmware_file.regen(make_file(make_section(0x19, b"\x00" * 0x1800)))
        quietly(firmware_file.process)

        rebuilt = quietly(volume.build, True)
        self.assertEqual(len(rebuilt), 0x2000)
        rebuilt_volume = FirmwareVolume(rebuilt)
        self.assertTrue(quietly(rebuilt_volume.process))
        self.assertEqual(rebuilt_volume.blocks, [(2, 0x1000)])
        self.assertEqual(calculate_checksum16(rebuilt[:rebuilt_volume.hdrlen]), 0)


class PFSBuildTest(unittest.TestCase):

    def make_pfs(self, section_data):
        section = uuid.UUID("7ec6c2b0-3fe3-42a0-a316-22dd0517c1e8").bytes_le + \
            struct.pack("<I4s8s8sIIII", 1, b"\x00" * 4, b"\x00" * 8,
                        b"\x00" * 8, len(section_data), 0, 0, 0)
        body = section.ljust(0x48, b"\x00") + section_data
        return b"PFS.HDR." + struct.pack("<II", 1, len(body)) + body + \
            struct.pack("<II", len(body), 0) + b"PFS.FTR."

    def test_data_after_the_volumes_is_kept(self):
        data = self.make_pfs(make_volume(size=0x100) + b"trailing data")
        pfs_file = PFSFile(data)
        self.assertTrue(quietly(pfs_file.process))
        self.assertEqual(quietly(pfs_file.build), data)

    def test_sizes_and_checksums_after_a_change(self):
        volume = make_volume(make_file(make_section(0x19, b"data")), size=0x100)
        pfs_file = PFSFile(self.make_pfs(volume))
        self.assertTrue(quietly(pfs_file.process))
        firmware_file = pfs_file.sections[0].section_objects[0] \
            .firmware_filesystems[0].files[0]
        firmware_file.regen(make_file(make_section(0x19, b"\x00" * 0x200)))
        quietly(firmware_file.process)

        rebuilt = quietly(pfs_file.build, True)
        body_size, = struct.unpack("<I", rebuilt[12:16])
        body = rebuilt[16:16 + body_size]
        footer_size, footer_checksum = struct.unpack(
            "<II", rebuilt[16 + body_size:24 + body_size])
        self.assertEqual(footer_size, body_size)
        self.assertEqual(footer_checksum, zlib.crc32(body) ^ 0xFFFFFFFF)

        section_size, = struct.unpack("<I", body[0x28:0x2C])
        section_checksum, = struct.unpack("<I", body[0x40:0x44])
        section_data = body[0x48:0x48 + section_size]
        self.assertEqual(section_checksum, zlib.crc32(section_data) ^ 0xFFFFFFFF)
        reparsed = PFSFile(rebuilt)
        self.assertTrue(quietly(reparsed.process))


class ChecksumTest(unittest.TestCase):

    def test_empty_data(self):
        # The checksums of empty data were 0x100 and 0x10000.
        self.assertEqual(calculate_checksum8(b""), 0)
        self.assertEqual(calculate_checksum16(b""), 0)


if __name__ == '__main__':
    unittest.main()
