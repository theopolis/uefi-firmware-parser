import contextlib
import io
import os
import struct
import tempfile
import unittest
import uuid

from uefi_firmware import AutoParser, MultiObject
from uefi_firmware.base import PaddingObject, RawObject
from uefi_firmware.flash import FlashRegion
from uefi_firmware.structs.uefi_structs import FIRMWARE_VOLUME_GUIDS
from uefi_firmware.uefi import FirmwareFileSystem, FirmwareVolume

VENDOR_DATA = b"vendor data"


def make_volume(size=0x1000):
    '''An empty FFS2 firmware volume made of a single block.'''
    block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size, b"_FVH", 0, hdrlen, 0, 0, b"\x00", 2)
    return header + block_map + b"\xff" * (size - hdrlen)


def make_pad_file(body):
    '''An FFS pad file (type 0xf0), which always has an all-0xff GUID.'''
    size = 24 + len(body)
    header = b"\xff" * 16 + struct.pack(
        "<HBB3sB", 0, 0xf0, 0x00, struct.pack("<I", size)[:3], 0xf8)
    return header + body


def show(firmware_object):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        firmware_object.showinfo()
    return output.getvalue()


class FreeSpaceTest(unittest.TestCase):

    def make_ffs(self, free_space):
        ffs = FirmwareFileSystem(make_pad_file(b"\x00" * 8) + free_space)
        self.assertTrue(ffs.process())
        return ffs

    def test_free_space_with_data_is_shown_and_dumped(self):
        free_space = b"\xff" * 0x40 + VENDOR_DATA + b"\xff" * 0x40
        ffs = self.make_ffs(free_space)

        self.assertIn("Free space:", show(ffs))
        with tempfile.TemporaryDirectory() as temp_dir:
            ffs.dump(temp_dir)
            with open(os.path.join(temp_dir, "free-space.raw"), "rb") as fh:
                self.assertEqual(fh.read(), free_space)

    def test_erased_free_space_is_not_shown_or_dumped(self):
        ffs = self.make_ffs(b"\xff" * 0x80)

        self.assertNotIn("Free space:", show(ffs))
        with tempfile.TemporaryDirectory() as temp_dir:
            ffs.dump(temp_dir)
            self.assertFalse(
                os.path.exists(os.path.join(temp_dir, "free-space.raw")))


class FlashRegionPaddingTest(unittest.TestCase):

    def setUp(self):
        # Erased padding, a volume, padding holding data, a second volume
        # and erased padding to the end of the region.
        self.gap = VENDOR_DATA.ljust(0x100, b"\xff")
        self.data = (b"\xff" * 0x100 + make_volume() + self.gap +
                     make_volume() + b"\xff" * 0x80)
        self.region = FlashRegion(self.data, "bios", {})
        self.assertTrue(self.region.process())

    def test_sections_cover_the_region(self):
        sections = self.region.sections

        self.assertEqual(
            [type(s) for s in sections],
            [PaddingObject, FirmwareVolume, PaddingObject, FirmwareVolume,
             PaddingObject])
        self.assertEqual(sum(s.size for s in sections), len(self.data))
        self.assertEqual(sections[2].offset, 0x1100)
        self.assertEqual(sections[2].data, self.gap)

    def test_dump_keeps_each_volume_and_non_empty_padding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.region.dump(temp_dir)

            output = os.path.join(temp_dir, "region-bios")
            self.assertEqual(sorted(os.listdir(output)), [
                "padding-0x1100.raw",
                "volume-0x100", "volume-0x100.fv",
                "volume-0x1200", "volume-0x1200.fv",
            ])


class MultiVolumePaddingTest(unittest.TestCase):

    def test_gap_between_volumes_is_kept(self):
        gap = VENDOR_DATA.ljust(0x200, b"\x00")
        trailer = b"\x5a" * 0x100

        firmware = AutoParser(
            make_volume() + gap + make_volume() + trailer).parse()

        self.assertIsInstance(firmware, MultiObject)
        self.assertEqual(
            [type(obj) for obj in firmware.objs],
            [FirmwareVolume, PaddingObject, FirmwareVolume, RawObject])
        self.assertEqual(firmware.objs[1].data, gap)
        self.assertEqual(firmware.objs[3].data, trailer)
        self.assertEqual(
            len(firmware.to_dict()['regions'][0]['data']['firmwareVolumes']),
            2)


if __name__ == '__main__':
    unittest.main()
