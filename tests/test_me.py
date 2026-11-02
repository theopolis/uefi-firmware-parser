import os
import struct
import tempfile
import unittest

from uefi_firmware import AutoParser
from uefi_firmware.me import (
    COMP_TYPE_HUFFMAN, COMP_TYPE_NOT_COMPRESSED, CPDManifestHeader,
    MeContainer, MeLLUT, MeManifestHeader)
from uefi_firmware.structs.intel_me_structs import (
    HuffmanLUTHeader, MeManifestHeaderType, MePartitionTable)

HUFFMAN_FLAG = 0x02000000


def make_cpd(entries, header_length=0x10):
    '''A $CPD directory, with each entry's data following the entry table.'''
    table_end = header_length + 0x18 * len(entries)
    table = b""
    body = b""
    for name, data, flags in entries:
        offset = table_end + len(body)
        table += struct.pack("<12sIII", name, offset | flags, len(data), 0)
        body += data
    header = b"$CPD" + struct.pack("<IBBBB4s", len(entries), 1, 1,
                                   header_length, 0, b"FTPR")
    return header.ljust(header_length, b"\x00") + table + body


def make_fpt(partitions):
    '''A partition table, with each partition's data following the table.'''
    table = MePartitionTable()
    table.Magic = b"$FPT"
    table.Entries = len(partitions)
    table_end = 0x30 + 0x20 * len(partitions)
    entries = b""
    body = b""
    for name, data in partitions:
        entries += struct.pack(
            "<4s4sII", name, b"\x00" * 4, table_end + len(body), len(data)
        ).ljust(0x20, b"\x00")
        body += data
    return bytes(table) + entries + body


def me_manifest(size_dw=0):
    manifest = MeManifestHeaderType()
    manifest.ModuleType = 4
    manifest.HeaderLen = 0xA1
    manifest.Size = size_dw
    manifest.Tag = b"$MN2"
    manifest.PartitionName = b"FTPR"
    # Modules follow the header and its key, at the partition offset.
    return bytes(manifest).ljust(0xA1 * 4 + 12, b"\x00")


class MeContainerTest(unittest.TestCase):

    def test_size_is_the_length_of_its_data(self):
        # The size added the whole container's length for every partition.
        data = make_fpt([(b"FTPR", b"\x00" * 0x10), (b"NFTP", b"\x00" * 0x10)])
        container = MeContainer(data)
        self.assertTrue(container.process())
        self.assertEqual(container.size, len(data))

    def test_table_without_partitions(self):
        # A size of 8 left the rest of the table to be parsed as new objects.
        data = make_fpt([]) + b"\x00" * 0x100
        firmware = AutoParser(data).parse()
        self.assertIsInstance(firmware, MeContainer)
        self.assertEqual(firmware.size, len(data))

    def test_partitions_with_the_same_name_do_not_overwrite(self):
        container = MeContainer(make_fpt(
            [(b"FTPR", b"first"), (b"FTPR", b"second")]))
        self.assertTrue(container.process())

        with tempfile.TemporaryDirectory() as temp_dir:
            container.dump(temp_dir)

            partitions = os.path.join(temp_dir, "partitions")
            for name, data in (("FTPR.partition", b"first"),
                               ("FTPR-1.partition", b"second")):
                with open(os.path.join(partitions, name), "rb") as fh:
                    self.assertEqual(fh.read(), data)


class CPDManifestHeaderTest(unittest.TestCase):

    def entries(self, data):
        manifest = CPDManifestHeader(data)
        self.assertTrue(manifest.process())
        return manifest.modules

    def test_first_entry_is_parsed(self):
        modules = self.entries(make_cpd([
            (b"FTPR.man", b"manifest", 0), (b"kernel.met", b"metadata", 0)]))
        self.assertEqual(
            [module.name for module in modules], ["FTPR.man", "kernel.met"])
        self.assertEqual(modules[0].compression, COMP_TYPE_NOT_COMPRESSED)

    def test_huffman_entry(self):
        # The offset's huffman flag failed the bounds check, so huffman
        # entries were dropped.
        modules = self.entries(make_cpd([
            (b"FTPR.man", b"manifest", 0), (b"kernel", b"huffman", HUFFMAN_FLAG)]))
        self.assertEqual(len(modules), 2)
        self.assertEqual(modules[1].compression, COMP_TYPE_HUFFMAN)
        self.assertEqual(modules[1].data, b"huffman")

    def test_version_2_header(self):
        modules = self.entries(make_cpd(
            [(b"FTPR.man", b"manifest", 0)], header_length=0x14))
        self.assertEqual([module.name for module in modules], ["FTPR.man"])

    def test_entries_with_the_same_name_do_not_overwrite(self):
        manifest = CPDManifestHeader(make_cpd([
            (b"kernel.met", b"first", 0), (b"kernel.met", b"second", 0)]))
        self.assertTrue(manifest.process())

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest.dump(temp_dir)

            for name, data in (("kernel.met.module", b"first"),
                               ("kernel.met-1.module", b"second")):
                with open(os.path.join(temp_dir, name), "rb") as fh:
                    self.assertEqual(fh.read(), data)


class HuffmanLUTTest(unittest.TestCase):

    def test_no_table_without_a_huffman_module(self):
        # Without a huffman module the table's offset was negative, so the
        # end of the partition was read as a table.
        tail = b"LLUT".ljust(0xA1 * 4 + 12, b"\x00")
        manifest = MeManifestHeader(me_manifest() + b"\x00" * 0x100 + tail)
        self.assertTrue(manifest.process())
        self.assertIsNone(manifest.huffman_llut)

    def test_data_cannot_start_before_the_table(self):
        header = HuffmanLUTHeader()
        header.Tag = b"LLUT"
        header.DataStart = 0x100
        header.Size = 0x10
        data = bytes(header) + b"\x00" * 0x100 + b"tail-of-the-data"
        self.assertFalse(MeLLUT(data, 0x200).valid_header)
        self.assertTrue(MeLLUT(data, 0x100).valid_header)


if __name__ == '__main__':
    unittest.main()
