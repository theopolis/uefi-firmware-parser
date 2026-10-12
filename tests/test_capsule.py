import struct
import unittest
import uuid

from uefi_firmware import AutoParser, MultiObject
from uefi_firmware.base import RawObject
from uefi_firmware.structs.uefi_structs import (
    APTIO_SIGNED_CAPSULE_GUID,
    APTIO_UNSIGNED_CAPSULE_GUID,
    FIRMWARE_VOLUME_GUIDS,
)
from uefi_firmware.uefi import (
    FirmwareCapsule,
    FirmwareVolume,
    MultiVolumeContainer,
)

UEFI_CAPSULE_GUID = '539182b9-abb5-4391-b69a-e3a943f72fcc'


def make_volume(size=0x1000):
    '''An empty FFS2 firmware volume made of a single block.'''
    block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size, b"_FVH", 0, hdrlen, 0, 0, b"\x00", 2)
    return header + block_map + b"\xff" * (size - hdrlen)


def make_rom():
    '''A flash image with padding and a gap around two volumes.'''
    return (b"\xff" * 0x1000 + make_volume() + b"\x00" * 0x200 +
            make_volume() + b"\xff" * 0x100)


def make_aptio_capsule(guid, rom, header_size=0x40):
    '''EFI_CAPSULE_HEADER + RomImageOffset + RomLayoutOffset, then the ROM.'''
    header = uuid.UUID(guid).bytes_le + struct.pack(
        "<IIIHH", header_size, 0, header_size + len(rom), header_size, 0)
    return header.ljust(header_size, b"\x00") + rom


class AptioCapsuleTest(unittest.TestCase):

    def test_capsule_spans_the_whole_rom_image(self):
        for guid in (APTIO_SIGNED_CAPSULE_GUID, APTIO_UNSIGNED_CAPSULE_GUID):
            with self.subTest(guid=guid):
                data = make_aptio_capsule(guid, make_rom())

                capsule = AutoParser(data).parse()

                self.assertIsInstance(capsule, FirmwareCapsule)
                self.assertEqual(capsule.size, len(data))
                self.assertIsInstance(
                    capsule.capsule_body, MultiVolumeContainer)
                self.assertEqual(len(capsule.capsule_body.volumes), 2)
                self.assertEqual(
                    len(capsule.to_dict()['body']['firmwareVolumes']), 2)

    def test_volumes_are_not_listed_twice(self):
        capsule = make_aptio_capsule(APTIO_SIGNED_CAPSULE_GUID, make_rom())
        trailer = b"\x5a" * 0x100

        firmware = AutoParser(capsule + trailer).parse()

        self.assertIsInstance(firmware, MultiObject)
        self.assertEqual(len(firmware.objs), 2)
        self.assertIsInstance(firmware.objs[0], FirmwareCapsule)
        self.assertEqual(firmware.objs[0].size, len(capsule))
        self.assertIsInstance(firmware.objs[1], RawObject)
        self.assertEqual(firmware.objs[1].data, trailer)

    def test_build_returns_the_capsule_bytes(self):
        data = make_aptio_capsule(APTIO_UNSIGNED_CAPSULE_GUID, make_rom())
        capsule = FirmwareCapsule(data)
        self.assertTrue(capsule.process())

        self.assertEqual(capsule.build(), data)

    def test_rom_without_volumes_is_rejected(self):
        data = make_aptio_capsule(APTIO_SIGNED_CAPSULE_GUID, b"\xff" * 0x1000)

        self.assertFalse(FirmwareCapsule(data).process())

    def test_other_capsules_do_not_search_for_volumes(self):
        header_size = 0x1c
        rom = make_rom()
        header = uuid.UUID(UEFI_CAPSULE_GUID).bytes_le + struct.pack(
            "<III", header_size, 0, header_size + len(rom))

        self.assertFalse(FirmwareCapsule(header + rom).process())


if __name__ == '__main__':
    unittest.main()
