import contextlib
import io
import os
import runpy
import struct
import sys
import tempfile
import unittest
import uuid
from unittest import mock

from uefi_firmware import utils
from uefi_firmware.generator.uefi import FirmwareVolumeGenerator
from uefi_firmware.structs.uefi_structs import (
    FIRMWARE_GUIDED_GUIDS, FIRMWARE_VOLUME_GUIDS)
from uefi_firmware.uefi import FirmwareVolume

CLI = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "bin",
    "uefi-firmware-parser")


def make_guid(number):
    return uuid.UUID(int=number).bytes_le


def make_section(section_type, body):
    data = struct.pack("<I", 4 + len(body))[:3] + bytes([section_type]) + body
    return data + b"\x00" * (-len(data) % 4)


def make_guided(guid, data):
    return make_section(0x02, uuid.UUID(guid).bytes_le +
                        struct.pack("<HH", 24, 0) + data)


def make_file(number, file_type, body):
    size = 24 + len(body)
    data = make_guid(number) + struct.pack(
        "<HBB3sB", 0xaa00, file_type, 0, struct.pack("<I", size)[:3], 0xf8)
    return data + body + b"\xff" * (-len(data + body) % 8)


def make_volume(body, size=0x2000):
    block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size, b"_FVH", 0x800, hdrlen, 0, 0, b"\x00", 2)
    return header + block_map + body.ljust(size - hdrlen, b"\xff")


def quietly(function, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args)


VOLUME = make_volume(
    make_file(1, 0x01, b"raw file body") +
    make_file(2, 0x07, make_section(0x15, 'A"B\n!include x'.encode("utf-16le") + b"\0\0") +
              make_section(0x03, b"disposable")) +
    make_file(3, 0x0e, make_section(0x10, b"MZ")) +
    make_file(4, 0xc0, make_section(0x19, b"oem")) +
    make_file(5, 0x07, make_guided(
        FIRMWARE_GUIDED_GUIDS["STATIC_GUID"], make_section(0x19, b"crc"))) +
    make_file(6, 0x0b, make_guided(
        FIRMWARE_GUIDED_GUIDS["FIRMWARE_VOLUME"], make_volume(b"", size=0x100))) +
    make_file(7, 0x07, make_section(0x01, struct.pack("<IB", 8, 0) +
                                    make_section(0x19, b"none"))))


class GeneratorTest(unittest.TestCase):

    def setUp(self):
        self.volume = FirmwareVolume(VOLUME)
        self.assertTrue(quietly(self.volume.process))
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.folder = temp_dir.name
        quietly(self.volume.dump, self.folder)
        self.output = quietly(FirmwareVolumeGenerator, self.volume).output

    def file_block(self, number):
        start = self.output.index(str(uuid.UUID(int=number)))
        return self.output[start:self.output.index("\n}", start)]

    def test_raw_file(self):
        # Raw files had no path, which raised AttributeError.
        raw_block = self.file_block(1)
        path = raw_block.split("SECTION RAW = ")[1].strip()
        self.assertTrue(path.startswith(self.folder))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"raw file body")

    def test_names_cannot_end_their_string(self):
        self.assertIn('SECTION UI = "A_B_!include x"', self.file_block(2))
        self.assertNotIn("\n!include", self.output)

    def test_unsupported_section_type(self):
        # The disposable section was written as "SECTION None = ...".
        self.assertIn("# Unsupported section: type 0x03", self.file_block(2))
        self.assertNotIn("None", self.output)

    def test_file_types_missing_from_the_table(self):
        # Types missing from the table raised KeyError.
        self.assertIn("FILE MM_STANDALONE = %s" % uuid.UUID(int=3), self.output)
        self.assertIn("FILE 0xC0 = %s" % uuid.UUID(int=4), self.output)

    def test_guided_section_uses_its_own_guid(self):
        # The file's GUID was written in place of the section's.
        self.assertIn("SECTION GUIDED %s" % FIRMWARE_GUIDED_GUIDS["STATIC_GUID"],
                      self.file_block(5))

    def test_guided_section_holding_a_volume(self):
        # The volume was passed to SectionGenerator, which raised.
        self.assertIn("SECTION FV_IMAGE = FV_", self.file_block(6))

    def test_uncompressed_section(self):
        self.assertIn("SECTION COMPRESS PI_NONE", self.file_block(7))


class GenerateCommandTest(unittest.TestCase):

    def test_generate_without_brute(self):
        # -g only worked with -b, nested its output path, and wrote a str to
        # a binary file, so no FDF was ever written.
        nocolor = utils.nocolor
        self.addCleanup(setattr, utils, "nocolor", nocolor)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "image.fv")
            with open(path, "wb") as fh:
                fh.write(VOLUME)
            out = os.path.join(temp_dir, "out")
            code = 0
            with mock.patch.object(sys, "argv", [CLI, "-q", "-g", out, path]), \
                    contextlib.redirect_stdout(io.StringIO()):
                try:
                    runpy.run_path(CLI, run_name="__main__")
                except SystemExit as exit:
                    code = exit.code
            self.assertEqual(code, 0)

            with open(os.path.join(out, "volume-0.fdf")) as fh:
                self.assertIn("[FV.FV_GENERIC]", fh.read())
            self.assertTrue(os.path.exists(os.path.join(out, "volume-0.fv")))


if __name__ == '__main__':
    unittest.main()
