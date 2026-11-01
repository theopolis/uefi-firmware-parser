import os
import struct
import tempfile
import unittest
import uuid

from uefi_firmware import AutoParser, MultiObject
from uefi_firmware.base import RawObject
from uefi_firmware.structs.uefi_structs import FIRMWARE_VOLUME_GUIDS
from uefi_firmware.uefi import FirmwareFileSystem, FirmwareVolume

PAD_FILE_DIR = "file-ffffffff-ffff-ffff-ffff-ffffffffffff"


def make_pad_file(body):
    '''An FFS pad file (type 0xf0), which always has an all-0xff GUID.'''
    size = 24 + len(body)
    header = b"\xff" * 16 + struct.pack(
        "<HBB3sB", 0, 0xf0, 0x00, struct.pack("<I", size)[:3], 0xf8)
    return header + body


def make_volume(size=0x1000):
    '''An empty FFS2 firmware volume made of a single block.'''
    block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size, b"_FVH", 0, hdrlen, 0, 0, b"\x00", 2)
    return header + block_map + b"\xff" * (size - hdrlen)


class FirmwareFileSystemTest(unittest.TestCase):

    def setUp(self):
        # Two non-empty pad files that fill the file system exactly, so
        # there is no free space after the last file.
        self.data = (make_pad_file(b"vendor-A" * 4) +
                     make_pad_file(b"vendor-B" * 4))
        self.ffs = FirmwareFileSystem(self.data)
        self.assertTrue(self.ffs.process())
        self.assertEqual(len(self.ffs.files), 2)

    def test_build_without_free_space(self):
        self.assertEqual(self.ffs.build(), self.data)

    def test_dump_keeps_files_with_the_same_guid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.ffs.dump(temp_dir)

            for name, body in ((PAD_FILE_DIR, b"vendor-A"),
                               (PAD_FILE_DIR + "-1", b"vendor-B")):
                with open(os.path.join(temp_dir, name, "file.obj"), "rb") as fh:
                    self.assertEqual(fh.read()[24:32], body)


class AutoParserPaddingTest(unittest.TestCase):

    def test_leading_padding_is_bytes(self):
        padding = b"\xff" * 1024

        firmware = AutoParser(padding + make_volume()).parse()

        self.assertIsInstance(firmware, MultiObject)
        self.assertIsInstance(firmware.objs[0], RawObject)
        self.assertEqual(firmware.objs[0].data, padding)


if __name__ == '__main__':
    unittest.main()
