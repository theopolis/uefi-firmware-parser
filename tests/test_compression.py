import importlib.machinery
import os
import struct
import sysconfig
import unittest

from uefi_firmware import efi_compressor


class CompressionTest(unittest.TestCase):

    def test_extension_uses_abi3_suffix(self):
        if sysconfig.get_config_var("Py_GIL_DISABLED") == 1:
            self.skipTest("free-threaded CPython does not use abi3 wheels")

        abi3_suffix = None
        for suffix in importlib.machinery.EXTENSION_SUFFIXES:
            if ".abi3" in suffix or suffix == ".pyd":
                abi3_suffix = suffix
                break

        if abi3_suffix is None:
            self.skipTest("interpreter does not advertise an abi3 extension suffix")

        self.assertEqual(
            os.path.basename(efi_compressor.__file__),
            "efi_compressor" + abi3_suffix,
        )

    def _test_compress(self, compress_algorithm):
        default_buffer = b"AAAAAAAA" * 90
        compressed_buffer = compress_algorithm(
            default_buffer, len(default_buffer))

        self.assertTrue(compressed_buffer is not None)
        self.assertGreater(len(compressed_buffer), 8)

        compressed_size, uncompressed_size = struct.unpack(
            "<II", compressed_buffer[:8])
        self.assertEqual(len(compressed_buffer) - 8, compressed_size)

    def _test_decompress(self, compress_algorithm, decompress_algorithm):
        default_buffer = b"AAAAAAAA" * 90
        compressed_buffer = compress_algorithm(
            default_buffer, len(default_buffer))
        decompressed_buffer = decompress_algorithm(
            compressed_buffer, len(compressed_buffer))

        self.assertTrue(decompressed_buffer is not None)
        self.assertEqual(len(decompressed_buffer), len(default_buffer))
        self.assertEqual(decompressed_buffer, default_buffer)

    def test_efi_compress(self):
        self._test_compress(efi_compressor.EfiCompress)

    def test_efi_decompress(self):
        self._test_decompress(
            efi_compressor.EfiCompress, efi_compressor.EfiDecompress)

    def test_tiano_compress(self):
        self._test_compress(efi_compressor.TianoCompress)

    def test_tiano_decompress(self):
        self._test_decompress(
            efi_compressor.TianoCompress, efi_compressor.TianoDecompress)

    def test_lzma_compress(self):
        default_buffer = b"AAAAAAAA" * 90
        compressed_buffer = efi_compressor.LzmaCompress(
            default_buffer, len(default_buffer))

        self.assertTrue(compressed_buffer is not None)

    def test_lzma_decompress(self):
        default_buffer = b"AAAAAAAA" * 90
        compressed_buffer = efi_compressor.LzmaCompress(
            default_buffer, len(default_buffer))
        decompressed_buffer = efi_compressor.LzmaDecompress(
            compressed_buffer,
            len(compressed_buffer)
        )

        self.assertTrue(decompressed_buffer is not None)
        self.assertEqual(len(decompressed_buffer), len(default_buffer))
        self.assertEqual(decompressed_buffer, default_buffer)

if __name__ == '__main__':
    unittest.main()
