import os
import struct
import tempfile
import unittest
import uuid

from uefi_firmware import AutoParser, MultiObject
from uefi_firmware.base import RawObject
from uefi_firmware.pfs import PFSFile

SECTION_GUID = uuid.UUID("9e21fd93-9c72-4c15-8c4b-e77f1db2d792")


def make_section(body, guid=SECTION_GUID):
    '''A PFS section header followed by its data, with no signatures.'''
    header = guid.bytes_le + struct.pack("<I4s8s8sIIII", 1, b"\x00" * 4,
                                         b"\x00" * 8, b"\x00" * 8, len(body),
                                         0, 0, 0)
    return header.ljust(0x48, b"\x00") + body


def make_pfs(body):
    return b"PFS.HDR." + struct.pack("<II", 1, len(body)) + body + \
        struct.pack("<II", len(body), 0) + b"PFS.FTR."


class PFSFileTest(unittest.TestCase):

    def test_size_includes_header_and_footer(self):
        # The size left out the 0x20 bytes of header and footer, so data
        # after the PFS was parsed from 0x20 bytes too early.
        pfs = make_pfs(make_section(b"payload"))
        firmware = AutoParser(pfs + b"trailing data").parse()

        self.assertIsInstance(firmware, MultiObject)
        pfs_file, trailer = firmware.objects
        self.assertIsInstance(pfs_file, PFSFile)
        self.assertEqual(pfs_file.size, len(pfs))
        self.assertEqual(pfs_file.data, pfs)
        self.assertIsInstance(trailer, RawObject)
        self.assertEqual(trailer.data, b"trailing data")

    def test_to_dict(self):
        # PFS objects had no to_dict, so -j raised AttributeError.
        pfs_file = PFSFile(make_pfs(make_section(b"payload")))
        self.assertTrue(pfs_file.process())
        self.assertEqual(pfs_file.to_dict(), {
            'spec': 1, 'size': 0x48 + 7, 'sections': [{
                'guid': str(SECTION_GUID), 'version': '', 'size': 0x48 + 7,
                'objects': [{'size': 7}]}]})

    def test_body_ends_at_the_declared_size(self):
        pfs_file = PFSFile(make_pfs(make_section(b"payload")) + b"\x00" * 0x48)
        self.assertTrue(pfs_file.process())
        self.assertEqual(len(pfs_file.sections), 1)

    def test_second_pfs_in_a_file_does_not_overwrite_the_first(self):
        first = make_pfs(make_section(b"first"))
        second = make_pfs(make_section(b"second"))
        firmware = AutoParser(first + second).parse()
        self.assertEqual(
            [type(obj) for obj in firmware.objects], [PFSFile, PFSFile])

        with tempfile.TemporaryDirectory() as temp_dir:
            firmware.dump(temp_dir)

            for name, data in (("pfsobject.pfs", first),
                               ("pfsobject-1.pfs", second)):
                with open(os.path.join(temp_dir, name), "rb") as fh:
                    self.assertEqual(fh.read(), data)

    def test_sections_with_the_same_guid_do_not_overwrite(self):
        pfs_file = PFSFile(make_pfs(
            make_section(b"first") + make_section(b"second")))
        self.assertTrue(pfs_file.process())

        with tempfile.TemporaryDirectory() as temp_dir:
            pfs_file.dump(temp_dir)

            section_dir = os.path.join(temp_dir, "pfsobject")
            for name, data in (("%s.data" % SECTION_GUID, b"first"),
                               ("%s-1.data" % SECTION_GUID, b"second")):
                with open(os.path.join(section_dir, name), "rb") as fh:
                    self.assertEqual(fh.read(), data)


if __name__ == '__main__':
    unittest.main()
