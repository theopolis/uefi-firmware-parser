import os
import struct
import tempfile
import unittest
import uuid

from uefi_firmware.flash import FlashRegion
from uefi_firmware.structs.uefi_structs import FIRMWARE_VOLUME_GUIDS
from uefi_firmware.uefi import FirmwareFileSystem, FirmwareVolume
from uefi_firmware.utils import dump_data, safe_path, safe_path_component

FV_NAME = "8c8ce578-8a3d-4f1c-9935-896185c32dd3"
FILE_GUID = "9e21fd93-9c72-4c15-8c4b-e77f1db2d792"


def make_file(file_type, guid, body):
    '''An FFS file with an 8-byte aligned size.'''
    size = 24 + len(body)
    header = guid + struct.pack(
        "<HBB3sB", 0, file_type, 0x00, struct.pack("<I", size)[:3], 0xf8)
    data = header + body
    return data + b"\xff" * (-len(data) % 8)


def make_volume(fvname=None, body=b"", size=0x1000):
    '''An FFS2 volume, with an extended header naming it when fvname is set.

    Like EDK2's GenFv, the extended header is stored in a leading pad file.
    '''
    block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    exthdroff = 0
    if fvname is not None:
        exthdroff = hdrlen + 24
        body = make_file(0xf0, b"\xff" * 16, struct.pack(
            "<16sI", fvname, FirmwareVolume._EXT_HEADER_SIZE)) + body
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size, b"_FVH", 0, hdrlen, 0, exthdroff, b"\x00", 2)
    return header + block_map + body.ljust(size - hdrlen, b"\xff")


class DumpPathTest(unittest.TestCase):

    def test_safe_path_component_removes_path_separators(self):
        self.assertEqual(safe_path_component("../testing.partition"), ".._testing.partition")
        self.assertEqual(safe_path_component("/tmp/testing.fv"), "_tmp_testing.fv")
        self.assertEqual(safe_path_component("C:\\tmp\\testing.fv"), "C__tmp_testing.fv")
        self.assertEqual(safe_path_component(".."), "_")

    def test_safe_path_confines_untrusted_component_to_parent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "out")
            target = safe_path(output_dir, "../testing.partition")

            dump_data(target, b"test")

            self.assertTrue(os.path.exists(os.path.join(output_dir, ".._testing.partition")))
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "testing.partition")))


class VolumeDumpNameTest(unittest.TestCase):

    def test_region_volumes_sharing_an_fvname_do_not_collide(self):
        # A recovery copy has the same FvName as the volume it backs up.
        fvname = uuid.UUID(FV_NAME).bytes_le
        region = FlashRegion(
            make_volume(fvname) + make_volume(fvname), "bios", {})
        self.assertTrue(region.process())

        with tempfile.TemporaryDirectory() as temp_dir:
            region.dump(temp_dir)

            self.assertEqual(
                sorted(os.listdir(os.path.join(temp_dir, "region-bios"))), [
                    "volume-0x0-%s" % FV_NAME,
                    "volume-0x0-%s.fv" % FV_NAME,
                    "volume-0x1000-%s" % FV_NAME,
                    "volume-0x1000-%s.fv" % FV_NAME,
                ])

    def test_nested_volume_is_named_by_fvname(self):
        inner = make_volume(uuid.UUID(FV_NAME).bytes_le, size=0x200)
        section = struct.pack("<I", len(inner) + 4)[:3] + b"\x17" + inner
        image_file = make_file(0x0b, uuid.UUID(FILE_GUID).bytes_le, section)
        ffs = FirmwareFileSystem(image_file)
        self.assertTrue(ffs.process())

        with tempfile.TemporaryDirectory() as temp_dir:
            ffs.dump(temp_dir)

            section_dir = os.path.join(
                temp_dir, "file-%s" % FILE_GUID, "section0")
            self.assertEqual(sorted(os.listdir(section_dir)), [
                "volume-%s" % FV_NAME, "volume-%s.fv" % FV_NAME])

    def test_nested_volume_without_fvname(self):
        fv = FirmwareVolume(make_volume(), None)
        self.assertTrue(fv.process())

        with tempfile.TemporaryDirectory() as temp_dir:
            fv.dump(temp_dir)

            self.assertEqual(sorted(os.listdir(temp_dir)), [
                "volume-0", "volume-0.fv"])

    def test_volume_names_stay_inside_parent(self):
        # FvName is read from the image, so it must not be able to steer the
        # output path even when its bytes spell out a traversal.
        fvname = b"/../../../../tmp"
        self.assertEqual(len(fvname), 16)
        fv = FirmwareVolume(make_volume(fvname), "../../escape")
        self.assertTrue(fv.process())

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "out")
            fv.dump(output_dir)

            self.assertEqual(os.listdir(temp_dir), ["out"])
            for name in os.listdir(output_dir):
                self.assertNotIn("/", name)
                self.assertTrue(name.startswith("volume-.._.._escape-"))


if __name__ == '__main__':
    unittest.main()