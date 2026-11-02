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
from uefi_firmware.structs.uefi_structs import FIRMWARE_VOLUME_GUIDS
from uefi_firmware.uefi import FirmwareVolume

SCRIPTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
# A GUID in the name tables: LENOVO_SYSTEM_SCSI_BUS_DXE_GUID.
KNOWN_GUID = "0167ccc4-d0f7-4f21-a3ef-9e64b7cdce8b"
EFI_CAPSULE_GUID = uuid.UUID("3b6686bd-0d76-4030-b70e-b5519e2fc5a0").bytes_le


def make_file(guid, body):
    size = 24 + len(body)
    data = uuid.UUID(guid).bytes_le + struct.pack(
        "<HBB3sB", 0xaa00, 0x07, 0, struct.pack("<I", size)[:3], 0xf8)
    return data + body + b"\xff" * (-len(data + body) % 8)


def make_raw_section(body):
    return struct.pack("<I", 4 + len(body))[:3] + b"\x19" + body


def make_volume(body, size=0x1000):
    block_map = struct.pack("<II", 1, size) + b"\x00" * 8
    hdrlen = FirmwareVolume._HEADER_SIZE + len(block_map)
    header = struct.pack(
        "<16s16sQ4sIHHHsB",
        b"\x00" * 16, uuid.UUID(FIRMWARE_VOLUME_GUIDS["FFS2"]).bytes_le,
        size, b"_FVH", 0x800, hdrlen, 0, 0, b"\x00", 2)
    return header + block_map + body.ljust(size - hdrlen, b"\xff")


def make_capsule(body):
    header = EFI_CAPSULE_GUID + struct.pack("<IIII", 0x50, 0, 0x50 + len(body), 0)
    header += b"\x00" * 16 + struct.pack("<8I", 0, 0x50, 0, 0, 0, 0, 0, 0)
    return header + body


VOLUME = make_volume(make_file(KNOWN_GUID, make_raw_section(b"original")))


class ScriptTest(unittest.TestCase):

    def setUp(self):
        nocolor = utils.nocolor
        self.addCleanup(setattr, utils, "nocolor", nocolor)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.folder = temp_dir.name

    def write(self, name, data):
        path = os.path.join(self.folder, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def run_script(self, script, *argv):
        '''Run a script in this process, returning its exit code and output.'''
        path = os.path.join(SCRIPTS, script)
        output = io.StringIO()
        code = 0
        with mock.patch.object(sys, "argv", [path] + list(argv)), \
                contextlib.redirect_stdout(output):
            try:
                runpy.run_path(path, run_name="__main__")
            except SystemExit as exit:
                code = exit.code
        return code, output.getvalue()


class GuidListTest(ScriptTest):

    def test_volume(self):
        # Looking up a GUID's name passed a list where bytes were needed.
        code, output = self.run_script("uefi_guids.py", self.write("v.fv", VOLUME))
        self.assertEqual(code, 0)
        self.assertIn("LENOVO_SYSTEM_SCSI_BUS_DXE_GUID", output)

    def test_capsule(self):
        # Capsules were parsed but their GUIDs never listed.
        path = self.write("c.cap", make_capsule(VOLUME))
        code, output = self.run_script("uefi_guids.py", "-c", path)
        self.assertEqual(code, 0)
        self.assertIn("LENOVO_SYSTEM_SCSI_BUS_DXE_GUID", output)

    def test_brute_search(self):
        # A successful search exited with 1.
        path = self.write("blob.bin", b"\x00" * 0x30 + VOLUME)
        code, output = self.run_script("uefi_guids.py", "-b", path)
        self.assertEqual(code, 0)
        self.assertIn("LENOVO_SYSTEM_SCSI_BUS_DXE_GUID", output)

    def test_brute_flash_search(self):
        # The search called a function that does not exist.
        path = self.write("blob.bin", b"\x00" * 0x100)
        code, _ = self.run_script("uefi_guids.py", "-b", "-d", path)
        self.assertEqual(code, 1)


class InjectorTest(ScriptTest):

    def inject(self, *argv):
        injection = self.write("inject.ffs", make_file(
            KNOWN_GUID, make_raw_section(b"injected")))
        output = os.path.join(self.folder, "out.bin")
        code, text = self.run_script(
            "fv_injector.py", "--injection", injection, "-o", output, *argv)
        return code, text, output

    def test_volume(self):
        code, _, output = self.inject(
            "--guid", KNOWN_GUID.upper(), self.write("v.fv", VOLUME))
        self.assertEqual(code, 0)
        with open(output, "rb") as fh:
            data = fh.read()
        self.assertEqual(len(data), len(VOLUME))
        self.assertIn(b"injected", data)
        self.assertNotIn(b"original", data)

    def test_capsule(self):
        # The capsule option was accepted but ignored.
        code, _, output = self.inject(
            "-c", "--guid", KNOWN_GUID, self.write("c.cap", make_capsule(VOLUME)))
        self.assertEqual(code, 0)
        with open(output, "rb") as fh:
            self.assertIn(b"injected", fh.read())

    def test_guid_not_found(self):
        # A copy without the injection was written, and reported as a success.
        code, text, output = self.inject(
            "--guid", str(uuid.UUID(int=1)), self.write("v.fv", VOLUME))
        self.assertEqual(code, 1)
        self.assertIn("no FirmwareFile with GUID", text)
        self.assertFalse(os.path.exists(output))


if __name__ == '__main__':
    unittest.main()
