'''Truncated or inconsistent headers that once raised instead of failing to
parse.'''

import contextlib
import inspect
import io
import os
import runpy
import struct
import sys
import tempfile
import unittest
import uuid
from unittest import mock

import uefi_firmware
from uefi_firmware import AutoParser, base, flash, me, pfs, uefi, utils
from uefi_firmware.me import MeContainer, MeManifestHeader
from uefi_firmware.pfs import PFSFile
from uefi_firmware.structs.intel_me_structs import (
    MeManifestHeaderType, MeModuleFileHeader1Type, MeModuleHeader1Type,
    MePartitionTable)
from uefi_firmware.structs.uefi_structs import FIRMWARE_VOLUME_GUIDS
from uefi_firmware.uefi import (
    CompressedSection, FirmwareCapsule, FirmwareFile, FirmwareVolume,
    GuidDefinedSection)

FILE_GUID = uuid.UUID("9e21fd93-9c72-4c15-8c4b-e77f1db2d792").bytes_le
EFI_CAPSULE_GUID = uuid.UUID("3b6686bd-0d76-4030-b70e-b5519e2fc5a0").bytes_le
CLI = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "bin",
    "uefi-firmware-parser")


def make_section(section_type, body):
    size = 4 + len(body)
    data = struct.pack("<I", size)[:3] + bytes([section_type]) + body
    return data + b"\x00" * (-len(data) % 4)


def make_file(body, file_type=0x07):
    size = 24 + len(body)
    header = FILE_GUID + struct.pack(
        "<HBB3sB", 0, file_type, 0x00, struct.pack("<I", size)[:3], 0xf8)
    data = header + body
    return data + b"\xff" * (-len(data) % 8)


def make_volume(body=b"", size=0x1000, block_map=None):
    if block_map is None:
        block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size, b"_FVH", 0, hdrlen, 0, 0, b"\x00", 2)
    return header + block_map + body.ljust(size - hdrlen, b"\xff")


def quietly(function, *args):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return function(*args)


class SectionTest(unittest.TestCase):

    def test_section_bodies_shorter_than_their_headers(self):
        # Compression, GUID-defined, version and free-form GUID sections.
        for section_type in (0x01, 0x02, 0x14, 0x18):
            firmware_file = FirmwareFile(
                make_file(make_section(section_type, b"")))
            self.assertFalse(quietly(firmware_file.process), section_type)

    def test_subsections_ignore_bytes_too_short_for_a_header(self):
        section = CompressedSection(
            struct.pack("<IB", 2, 0x00) + b"AB", FILE_GUID)
        self.assertTrue(section.process())
        self.assertEqual(section.subsections, [])

    def test_subsection_with_truncated_extended_size(self):
        # A size of 0xffffff means a 32-bit size follows, but nothing does.
        # The section was kept without data or a name, and to_dict raised.
        section = CompressedSection(
            struct.pack("<IB", 4, 0x00) + b"\xff\xff\xff\x10", FILE_GUID)
        self.assertFalse(quietly(section.process))
        self.assertEqual(section.subsections, [])

    def test_guid_defined_data_offset_inside_its_header(self):
        body = FILE_GUID + struct.pack("<HH", 8, 0) + b"BODY"
        section = GuidDefinedSection(body, large_header=False)
        self.assertEqual(section.preamble, b"")
        self.assertEqual(section.data, b"BODY")


class VolumeTest(unittest.TestCase):

    def test_block_map_shorter_than_an_entry(self):
        volume = FirmwareVolume(make_volume(block_map=b"\x01\x00\x00\x00"))
        self.assertTrue(volume.valid_header)
        self.assertFalse(quietly(volume.process))

    def test_block_map_with_trailing_partial_entry(self):
        block_map = struct.pack("<II", 1, 0x1000) + b"\x00" * 4
        volume = FirmwareVolume(make_volume(block_map=block_map))
        self.assertTrue(volume.process())
        self.assertEqual(volume.blocks, [(1, 0x1000)])


class CapsuleTest(unittest.TestCase):

    def efi_capsule(self, header_size, body_offset, body):
        header = EFI_CAPSULE_GUID + struct.pack(
            "<IIII", header_size, 0, header_size + len(body), 0) + \
            b"\x00" * 16 + struct.pack("<8I", 0, body_offset, 0, 0, 0, 0, 0, 0)
        return header.ljust(header_size, b"\x00") + body

    def test_truncated_header(self):
        data = EFI_CAPSULE_GUID + b"\x00" * 8
        self.assertIsNone(AutoParser(data).parse())

    def test_body_offset_inside_header(self):
        # Retrying the offset as relative to the header's end gave -0x1000,
        # which found this volume by slicing from the end of the capsule.
        data = self.efi_capsule(
            0x1000, 0, b"\x00" * 0x100 + make_volume(size=0x1000))
        capsule = FirmwareCapsule(data)
        self.assertTrue(capsule.valid_header)
        self.assertFalse(capsule.process())


def me_manifest(tag=b"$MN2", num_modules=0, size_dw=0x400):
    manifest = MeManifestHeaderType()
    manifest.ModuleType = 4
    manifest.HeaderLen = 0xA1
    manifest.Size = size_dw
    manifest.Tag = tag
    manifest.NumModules = num_modules
    manifest.PartitionName = b"FTPR"
    # Modules follow the header and its key, at the partition offset.
    return bytes(manifest).ljust(0xA1 * 4 + 12, b"\x00")


class MeTest(unittest.TestCase):

    def variable_module(self, tag, values):
        body = b"".join(struct.pack("<I", value) for value in values)
        return tag + struct.pack("<I", 2 + len(values)) + body

    def test_mcp_with_one_value(self):
        # A size of 4 bytes was unpacked as two 32-bit values.
        manifest = MeManifestHeader(
            me_manifest() + self.variable_module(b"$MCP", [0x1000]) +
            b"\x00" * 0x1000)
        self.assertTrue(manifest.process())
        self.assertEqual(manifest.partition_end, 0)

    def test_mcp_with_two_values(self):
        manifest = MeManifestHeader(
            me_manifest() + self.variable_module(b"$MCP", [0x1000, 0x2000]) +
            b"\x00" * 0x1000)
        self.assertTrue(manifest.process())
        self.assertEqual(manifest.partition_end, 0x3000)

    def test_variable_module_truncated_mid_value(self):
        data = me_manifest() + b"$ABC" + struct.pack("<I", 4) + b"\x01" * 5
        manifest = MeManifestHeader(data)
        self.assertTrue(manifest.process())
        self.assertEqual(manifest.variable_modules[0].values, [0x01010101])

    def test_truncated_update_module(self):
        manifest = MeManifestHeader(
            me_manifest() + self.variable_module(b"$UDC", [0]) +
            b"\x00" * 0x1000)
        self.assertFalse(manifest.process())

    def test_module_file_after_manifest(self):
        # A $MOD header after a $MAN manifest's modules raised TypeError.
        data = me_manifest(tag=b"$MAN", size_dw=0x100) + b"\x00" * 0x400 + \
            b"$MOD" + b"\x00" * 0x100
        self.assertTrue(MeManifestHeader(data).process())

    def test_type1_lzma_module_takes_size_from_module_file(self):
        module = MeModuleHeader1Type()
        module.Tag = b"$MME"
        module.Name = b"KERN"
        module.Size = 0x200
        module_file = MeModuleFileHeader1Type()
        module_file.Tag = b"$MOD"
        module_file.UncompressedSize = 0x1234
        props = b"\x5D\x00\x00\x80\x00"
        partition = me_manifest(tag=b"$MAN", num_modules=1, size_dw=0)
        # A type 1 module's data is at the partition offset from its header.
        data = partition + bytes(module).ljust(len(partition), b"\x00") + \
            bytes(module_file) + props + b"STREAM"
        manifest = MeManifestHeader(data.ljust(0x2000, b"\x00"))

        self.assertTrue(manifest.process())
        self.assertEqual(
            manifest.modules[0].data[:19],
            props + struct.pack("<Q", 0x1234) + b"STREAM")

    def test_container_dumps_inside_multi_object(self):
        # MultiObject passes an index to dump(), which ME objects rejected.
        table = MePartitionTable()
        table.Magic = b"$FPT"
        firmware = AutoParser(
            b"\xff" * 1024 + bytes(table) + b"\x00" * 0x100).parse()
        self.assertIsInstance(firmware.objs[1], MeContainer)
        with tempfile.TemporaryDirectory() as temp_dir:
            quietly(firmware.dump, temp_dir)
            self.assertTrue(
                os.path.exists(os.path.join(temp_dir, "me-container.me")))

    def test_every_dump_accepts_an_index(self):
        # Containers call dump(parent, index) on children of any type.
        for module in (base, flash, me, pfs, uefi, uefi_firmware):
            for name, cls in inspect.getmembers(module, inspect.isclass):
                if cls.__module__ != module.__name__ or \
                        not hasattr(cls, "dump"):
                    continue
                with self.subTest(cls=name):
                    inspect.signature(cls.dump).bind(None, "parent", 0)


class PfsTest(unittest.TestCase):

    def pfs(self, body, size=None):
        if size is None:
            size = len(body)
        return b"PFS.HDR." + struct.pack("<II", 1, size) + body + \
            struct.pack("<II", size, 0) + b"PFS.FTR."

    def test_empty_body(self):
        pfs_file = PFSFile(self.pfs(b""))
        self.assertTrue(pfs_file.process())
        self.assertEqual(pfs_file.sections, [])

    def test_footer_past_the_data(self):
        data = b"PFS.HDR." + struct.pack("<II", 1, 0x100) + b"\x00" * 0x20
        self.assertFalse(quietly(PFSFile, data).valid_header)


class CliTest(unittest.TestCase):

    def run_cli(self, *argv):
        '''Run the CLI in this process, returning its exit code and output.'''
        nocolor = utils.nocolor
        self.addCleanup(setattr, utils, "nocolor", nocolor)
        output = io.StringIO()
        code = 0
        with mock.patch.object(sys, "argv", [CLI] + list(argv)), \
                contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                runpy.run_path(CLI, run_name="__main__")
            except SystemExit as exit:
                code = exit.code
        return code, output.getvalue()

    def write(self, directory, name, data):
        path = os.path.join(directory, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def test_json_for_a_file_that_fails_to_parse(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write(
                temp_dir, "capsule.bin", EFI_CAPSULE_GUID + b"\x00" * 8)
            code, output = self.run_cli("-j", path)
        self.assertEqual(code, 3)
        self.assertIn("could not be processed", output)

    def test_error_in_one_file_does_not_stop_the_others(self):
        real_parse = AutoParser.parse
        calls = []

        def parse(parser):
            calls.append(parser)
            if len(calls) == 1:
                raise ValueError("boom")
            return real_parse(parser)

        with tempfile.TemporaryDirectory() as temp_dir:
            first = self.write(temp_dir, "first.fv", make_volume())
            second = self.write(temp_dir, "second.fv", make_volume())
            with mock.patch.object(AutoParser, "parse", parse):
                code, output = self.run_cli(first, second)

        self.assertEqual(code, 3)
        self.assertIn("cannot parse %s (ValueError: boom)" % first, output)
        self.assertIn("Firmware Volume", output)

    def test_superbrute_finds_an_object_after_other_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write(
                temp_dir, "blob.bin", b"\x01" * 0x101 + make_volume())
            code, output = self.run_cli("--superbrute", path)
        self.assertEqual(code, 0)
        self.assertIn("Firmware Volume", output)


if __name__ == '__main__':
    unittest.main()
