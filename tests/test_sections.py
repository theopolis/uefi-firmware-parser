import contextlib
import io
import os
import struct
import tempfile
import unittest
import uuid

from uefi_firmware import MultiObject
from uefi_firmware.me import MeContainer
from uefi_firmware.structs.intel_me_structs import MePartitionTable
from uefi_firmware.structs.uefi_structs import FIRMWARE_VOLUME_GUIDS
from uefi_firmware.uefi import (
    CompressedSection, EfiSection, FirmwareFileSystemSection, FirmwareVolume,
    FreeformGuidSection, VersionSection)

FILE_GUID = uuid.UUID("9e21fd93-9c72-4c15-8c4b-e77f1db2d792").bytes_le
SECRET = b"bytes-from-image-A" * 4


def make_section(section_type, body):
    size = 4 + len(body)
    return struct.pack("<I", size)[:3] + bytes([section_type]) + body


def make_file(body, file_type=0x07):
    '''An FFS file with an 8-byte aligned size.'''
    size = 24 + len(body)
    header = FILE_GUID + struct.pack(
        "<HBB3sB", 0, file_type, 0x00, struct.pack("<I", size)[:3], 0xf8)
    data = header + body
    return data + b"\xff" * (-len(data) % 8)


def make_volume(body, size=0x1000):
    '''An FFS2 volume made of a single block.'''
    block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size, b"_FVH", 0, hdrlen, 0, 0, b"\x00", 2)
    return header + block_map + body.ljust(size - hdrlen, b"\xff")


def parse_volume(body):
    volume = FirmwareVolume(make_volume(make_file(body)))
    volume.process()
    return volume


def first_section(volume):
    return volume.firmware_filesystems[0].files[0].sections[0].parsed_object


class SharedSubsectionsTest(unittest.TestCase):

    def test_failed_decompression_does_not_leak_into_other_images(self):
        # Image A: an EFI-compressed section whose payload cannot be
        # decompressed, so it keeps the compressed bytes as a raw child.
        image_a = parse_volume(make_section(
            0x01, struct.pack("<IB", 0x100, 0x01) + SECRET))
        compressed = first_section(image_a)
        self.assertIsInstance(compressed, CompressedSection)
        self.assertEqual(len(compressed.subsections), 1)

        # Image B, parsed separately: a free-form GUID section has no
        # children of its own.
        image_b = parse_volume(make_section(0x18, b"\x11" * 16 + b"payload"))
        freeform = first_section(image_b)
        self.assertIsInstance(freeform, FreeformGuidSection)
        self.assertEqual(list(freeform.objects), [])

        with tempfile.TemporaryDirectory() as temp_dir:
            image_b.dump(temp_dir)
            for root, _, files in os.walk(temp_dir):
                for name in files:
                    with open(os.path.join(root, name), "rb") as fh:
                        self.assertNotIn(SECRET, fh.read(), name)

    def test_sections_do_not_share_subsections(self):
        sections = [
            CompressedSection(struct.pack("<IB", 0, 0x00), FILE_GUID),
            CompressedSection(struct.pack("<IB", 0, 0x00), FILE_GUID),
            VersionSection(b"\x00" * 16),
            FreeformGuidSection(b"\x00" * 16),
        ]
        for section in sections:
            section.subsections.append(object())

        for section in sections:
            self.assertEqual(len(section.subsections), 1)
        self.assertEqual(len(EfiSection.subsections), 0)


class DepexTest(unittest.TestCase):

    def showinfo(self, body):
        section = FirmwareFileSystemSection(make_section(0x13, body), FILE_GUID)
        self.assertTrue(section.process())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            section.showinfo()
        return [line.strip() for line in output.getvalue().splitlines()[1:]]

    def test_opcodes(self):
        guid = uuid.UUID("01234567-89ab-4def-8123-456789abcdef")
        lines = self.showinfo(
            b"\x01" + guid.bytes_le + b"\x06\x07\x03\x09\x08\xee")
        # The GUID's bytes were shown as opcodes, and FALSE as "07?".
        self.assertEqual(lines, [
            "AFTER %s" % guid, "TRUE", "FALSE", "AND", "SOR", "END", "ee?"])


class RawSectionTest(unittest.TestCase):

    def test_object_followed_by_other_data(self):
        # AutoParser returns a MultiObject, which has no process().
        section = FirmwareFileSystemSection(
            make_section(0x19, make_volume(b"") + b"trailer"), FILE_GUID)
        self.assertTrue(section.process())
        self.assertIsInstance(section.parsed_object, MultiObject)

    def test_object_is_processed_once(self):
        # Processing an ME container twice listed each partition twice.
        table = MePartitionTable()
        table.Magic = b"$FPT"
        table.Entries = 1
        entry = b"FTPR" + b"\x00" * 4 + struct.pack("<II", 0x50, 0x10)
        body = bytes(table) + entry.ljust(0x20, b"\x00") + b"\x00" * 0x10
        section = FirmwareFileSystemSection(make_section(0x19, body), FILE_GUID)
        self.assertTrue(section.process())
        self.assertIsInstance(section.parsed_object, MeContainer)
        self.assertEqual(len(section.parsed_object.partitions), 1)


if __name__ == '__main__':
    unittest.main()
