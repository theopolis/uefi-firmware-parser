'''Crafted inputs that once looped forever, recursed past the stack, took
quadratic time, or decompressed without bound.'''

import gzip
import struct
import threading
import time
import unittest
import uuid
from unittest import mock

from uefi_firmware import AutoParser, utils
from uefi_firmware import efi_compressor
from uefi_firmware.flash import FlashRegion
from uefi_firmware.me import CPDManifestHeader, MeContainer, MeManifestHeader
from uefi_firmware.misc import checker
from uefi_firmware.structs.intel_me_structs import (
    MeCpdHeaderType, MeManifestHeaderType, MePartitionTable)
from uefi_firmware.structs.uefi_structs import (
    FIRMWARE_GUIDED_GUIDS, FIRMWARE_VOLUME_GUIDS)
from uefi_firmware.uefi import (
    CompressedSection, FirmwareFile, FirmwareFileSystem, FirmwareVolume,
    find_volumes)
from uefi_firmware.utils import flatten_firmware_objects

FILE_GUID = uuid.UUID("9e21fd93-9c72-4c15-8c4b-e77f1db2d792").bytes_le


def make_section(section_type, body):
    '''A file section, padded so the next section is 4-byte aligned.'''
    size = 4 + len(body)
    data = struct.pack("<I", size)[:3] + bytes([section_type]) + body
    return data + b"\x00" * (-len(data) % 4)


def make_file(body, file_type=0x07):
    '''An FFS file with an 8-byte aligned size.'''
    size = 24 + len(body)
    header = FILE_GUID + struct.pack(
        "<HBB3sB", 0, file_type, 0x00, struct.pack("<I", size)[:3], 0xf8)
    data = header + body
    return data + b"\xff" * (-len(data) % 8)


def make_volume(body=b"", size=None, length=None):
    '''An FFS2 volume of one block, sized to fit body unless size is given.

    length overrides the header's volume length without changing the data.
    '''
    block_map_size = 16
    hdrlen = FirmwareVolume._HEADER_SIZE + block_map_size
    if size is None:
        size = hdrlen + len(body) + (-len(body) % 8)
    block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size if length is None else length, b"_FVH", 0, hdrlen, 0, 0,
        b"\x00", 2)
    return header + block_map + body.ljust(size - hdrlen, b"\xff")


def compressed_section(data):
    '''An EFI compression section (type 0x01) holding an LZMA stream.'''
    stream = efi_compressor.LzmaCompress(data, len(data))
    return make_section(0x01, struct.pack("<IB", len(data), 0x02) + stream)


def run_with_deadline(test, function, seconds=10):
    '''Run function, failing the test (rather than hanging) if it does not
    return within seconds. A runaway call is left in a daemon thread.'''
    result = {}

    def target():
        try:
            result["value"] = function()
        except BaseException as error:
            result["error"] = error

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    test.assertFalse(thread.is_alive(), "did not finish in %ds" % seconds)
    if "error" in result:
        raise result["error"]
    return result["value"]


class FindVolumesTest(unittest.TestCase):

    def test_zero_length_volume_terminates(self):
        # A header whose Length is 0 was found again at the same offset.
        data = b"JUNKJUNK" + make_volume(length=0)
        objects = run_with_deadline(self, lambda: find_volumes(data))
        self.assertEqual(sum(obj.size for obj in objects), len(data))

    def test_objects_cover_skipped_bytes(self):
        # An invalid magic used to drop 48 bytes from the output.
        data = b"\x00" * 100 + b"_FVH" + b"\x00" * 100 + make_volume()
        objects = find_volumes(data)
        self.assertEqual(
            b"".join(getattr(obj, "_data", None) or obj.data
                     for obj in objects), data)

    def test_magic_near_start_does_not_wrap(self):
        # A magic within the first 40 bytes gave a negative volume offset,
        # which sliced from the end of the data.
        data = b"_FVH" + make_volume()
        objects = find_volumes(data)
        self.assertIsInstance(objects[-1], FirmwareVolume)
        self.assertEqual(sum(obj.size for obj in objects), len(data))

    def test_scan_is_linear(self):
        # Each candidate copied the rest of the data, so this took minutes.
        data = b"\x00" * (4 * 1024 * 1024) + b"_FVH"
        start = time.monotonic()
        find_volumes(data)
        self.assertLess(time.monotonic() - start, 2)


class ScanTimeTest(unittest.TestCase):
    '''Loops that copied the rest of their data on every step.

    Each input is 16-32 MiB, which took 12 seconds or more when every step
    copied the remaining data, and takes well under a second now.
    '''

    COUNT = 32768
    BODY = b"\x00" * 1000

    def assertParsesQuickly(self, parse, seconds=3):
        start = time.monotonic()
        run_with_deadline(self, parse, seconds * 10)
        self.assertLess(time.monotonic() - start, seconds)

    def test_many_files(self):
        ffs = FirmwareFileSystem(
            make_file(self.BODY, file_type=0xf0) * self.COUNT)
        self.assertParsesQuickly(ffs.process)
        self.assertEqual(len(ffs.files), self.COUNT)

    def test_many_sections_in_file(self):
        # A file's 24-bit size limits it to 16 MiB, which took about 3
        # seconds when each step copied the remaining sections.
        count = self.COUNT // 2
        firmware_file = FirmwareFile(
            make_file(make_section(0xf0, self.BODY) * count))
        self.assertParsesQuickly(firmware_file.process, seconds=1)
        self.assertEqual(len(firmware_file.sections), count)

    def test_many_subsections(self):
        # An uncompressed compression section holding the subsections.
        sections = make_section(0xf0, self.BODY) * self.COUNT
        section = CompressedSection(
            struct.pack("<IB", len(sections), 0x00) + sections, FILE_GUID)
        self.assertParsesQuickly(section.process)
        self.assertEqual(len(section.subsections), self.COUNT)

    def test_many_volume_candidates_in_flash_region(self):
        # An 8-byte aligned '_FVH' every 256 bytes, none a valid volume.
        chunk = b"\x00" * 248 + b"_FVH" + b"\x00" * 4
        region = FlashRegion(chunk * (16 * 4096), "bios", {})
        self.assertParsesQuickly(region.process)


def me_manifest(num_modules=0, size_dw=0x200):
    manifest = MeManifestHeaderType()
    manifest.ModuleType = 4
    manifest.HeaderLen = 0xA1
    manifest.Size = size_dw
    manifest.Tag = b"$MN2"
    manifest.NumModules = num_modules
    manifest.PartitionName = b"FTPR"
    return bytes(manifest)


class MeTerminationTest(unittest.TestCase):

    def test_zero_length_variable_module(self):
        # A length of 0 gave a size of -8, so the offset never advanced.
        header = me_manifest(size_dw=0x400)
        data = header.ljust(0xA1 * 4 + 12, b"\x00") + \
            b"$ABC" + struct.pack("<I", 0) + b"\x00" * 0x1000
        manifest = MeManifestHeader(data)
        self.assertTrue(manifest.valid_header)
        run_with_deadline(self, manifest.process)
        self.assertEqual(manifest.variable_modules, [])

    def test_module_count_is_bounded_by_data(self):
        data = me_manifest(num_modules=0xFFFFFFFF, size_dw=0) + \
            b"\x00" * 0x1000
        manifest = MeManifestHeader(data)
        run_with_deadline(self, manifest.process)
        self.assertLess(len(manifest.modules), len(data))

    def test_partition_count_is_bounded_by_data(self):
        table = MePartitionTable()
        table.Magic = b"$FPT"
        table.Entries = 0xFFFFFFFF
        data = bytes(table) + b"\x00" * 0x10000
        container = MeContainer(data)
        self.assertTrue(container.valid_header)
        run_with_deadline(self, container.process)
        self.assertLessEqual(len(container.partitions), len(data) // 0x20)

    def test_cpd_entry_count_is_bounded_by_data(self):
        header = MeCpdHeaderType()
        header.Tag = b"$CPD"
        header.NumModules = 0xFFFFFFFF
        header.PartitionName = b"FTPR"
        data = bytes(header) + b"\x00" * 0x1000
        cpd = CPDManifestHeader(data)
        run_with_deadline(self, cpd.process)
        self.assertLessEqual(len(cpd.modules), len(data) // 0x18)


class NestingTest(unittest.TestCase):

    def test_deeply_nested_volumes(self):
        # Each volume holds a file whose FV-image section holds the next.
        volume = make_volume()
        for _ in range(300):
            volume = make_volume(
                make_file(make_section(0x17, volume), file_type=0x0b))
        firmware = FirmwareVolume(volume)
        # This raised RecursionError; parsing now stops at the depth limit.
        run_with_deadline(self, firmware.process)

    def test_many_concatenated_volumes(self):
        # AutoParser recursed once for each object after the first.
        count = 1000
        data = make_volume() * count
        firmware = run_with_deadline(self, AutoParser(data).parse)
        volumes = [
            obj for obj in flatten_firmware_objects(firmware.iterate_objects())
            if isinstance(obj["_self"], FirmwareVolume)]
        self.assertEqual(len(volumes), count)

    def test_object_covering_no_bytes(self):
        class EmptyObject(object):
            size = 0

            def __init__(self, data):
                pass

            def process(self):
                return True

        class EmptyTester(checker.TypeTester):
            parser = EmptyObject
            static = b"EMPTY"

        with mock.patch.object(checker, "TESTERS", [EmptyTester]):
            parser = AutoParser(b"EMPTY" + b"\x00" * 64)
            run_with_deadline(self, parser.parse)


class DecompressionBudgetTest(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(
            utils, "MAX_DECOMPRESSED_BYTES", 1024 * 1024)
        patcher.start()
        self.addCleanup(patcher.stop)

    def parse_file(self, sections):
        firmware = FirmwareVolume(make_volume(make_file(sections)))
        firmware.process()
        return firmware.firmware_filesystems[0].files[0]

    def test_budget_limits_total_output(self):
        payload = b"\x00" * (512 * 1024)
        firmware_file = self.parse_file(compressed_section(payload) * 4)

        decompressed = [
            section for section in firmware_file.sections
            if section.parsed_object.data == payload]
        self.assertEqual(len(decompressed), 2)

    def test_budget_resets_for_each_parse(self):
        payload = b"\x00" * (768 * 1024)
        for _ in range(2):
            firmware_file = self.parse_file(compressed_section(payload))
            self.assertEqual(
                firmware_file.sections[0].parsed_object.data, payload)

    def test_claimed_size_is_charged_before_decoding(self):
        # 8 bytes of Tiano/EFI header claiming 100 MB of output.
        header = struct.pack("<II", 0, 100 * 1000 * 1000)
        section = make_section(0x01, struct.pack("<IB", 0, 0x01) + header)
        start = time.monotonic()
        firmware_file = self.parse_file(section)
        self.assertLess(time.monotonic() - start, 1)
        self.assertIsNone(firmware_file.sections[0].parsed_object.data)

    def test_gzip_section_is_bounded(self):
        guid = uuid.UUID(FIRMWARE_GUIDED_GUIDS["GZIP_COMPRESSED_QC"]).bytes_le

        def gzip_section(payload):
            stream = gzip.compress(payload)
            body = guid + struct.pack("<HH", 24, 0) + stream
            return self.parse_file(make_section(0x02, body)).sections[0]

        payload = b"\x00" * (512 * 1024)
        self.assertEqual(gzip_section(payload).parsed_object.data, payload)
        # A failed GUID-defined section is dropped rather than kept raw.
        too_large = b"\x00" * (2 * 1024 * 1024)
        self.assertIsNone(gzip_section(too_large).parsed_object)

    def test_zlib_decompress_rejects_truncated_stream(self):
        stream = gzip.compress(b"firmware" * 64)
        with self.assertRaises(Exception):
            utils.zlib_decompress(stream[:-12], wbits=31)


if __name__ == '__main__':
    unittest.main()
