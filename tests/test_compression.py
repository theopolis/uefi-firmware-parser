import importlib.machinery
import lzma
import os
import struct
import sys
import sysconfig
import unittest

try:
    import resource
except ImportError:
    # Windows has no resource module.
    resource = None

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


def lzma_alone(data, header_size):
    '''An LZMA-alone stream (with an end marker) claiming header_size bytes.'''
    stream = lzma.compress(data, format=lzma.FORMAT_ALONE)
    return stream[:5] + struct.pack("<Q", header_size) + stream[13:]


class MalformedInputTest(unittest.TestCase):

    DECOMPRESSORS = (
        efi_compressor.EfiDecompress,
        efi_compressor.TianoDecompress,
        efi_compressor.LzmaDecompress,
    )

    def test_lzma_rejects_input_shorter_than_header(self):
        for size in range(13):
            data = b"\x5d" + b"\x00" * 12
            with self.subTest(size=size):
                with self.assertRaises(Exception):
                    efi_compressor.LzmaDecompress(data[:size], size)

    def test_lzma_accepts_stream_with_end_marker(self):
        payload = b"firmware" * 64
        data = lzma_alone(payload, len(payload))

        self.assertEqual(
            efi_compressor.LzmaDecompress(data, len(data)), payload)

    def test_lzma_rejects_stream_shorter_than_header_size(self):
        # The stream ends with its marker before producing the claimed size,
        # so the rest of the output buffer would be uninitialized memory.
        for payload in (b"", b"firmware"):
            data = lzma_alone(payload, 4096)
            with self.subTest(payload=payload):
                with self.assertRaises(Exception):
                    efi_compressor.LzmaDecompress(data, len(data))

    def test_size_larger_than_data_is_rejected(self):
        data = efi_compressor.LzmaCompress(b"A" * 64, 64)
        for decompress in self.DECOMPRESSORS:
            for size in (len(data) + 1, 1 << 40, -1):
                with self.subTest(decompress=decompress.__name__, size=size):
                    with self.assertRaises(ValueError):
                        decompress(data, size)

    def test_size_larger_than_data_is_rejected_on_compress(self):
        for compress in (efi_compressor.EfiCompress,
                         efi_compressor.TianoCompress,
                         efi_compressor.LzmaCompress):
            with self.subTest(compress=compress.__name__):
                with self.assertRaises(ValueError):
                    compress(b"A" * 64, 65)

    def test_empty_output(self):
        # A header claiming zero bytes once wrote one byte into malloc(0).
        for decompress in self.DECOMPRESSORS[:2]:
            with self.subTest(decompress=decompress.__name__):
                self.assertEqual(decompress(b"\x00" * 8, 8), b"")

    @unittest.skipIf(resource is None, "resource module is unavailable")
    def test_decompress_does_not_leak_output(self):
        # An empty Tiano/EFI body decodes to OrigSize zero bytes, so this
        # header produces a 10 MB result from 8 bytes of input.
        size = 10 * 1000 * 1000
        data = struct.pack("<II", 0, size)
        efi_compressor.EfiDecompress(data, len(data))

        before = peak_rss_bytes()
        for _ in range(20):
            self.assertEqual(
                len(efi_compressor.EfiDecompress(data, len(data))), size)
        # Leaking each output buffer would grow the peak by about 200 MB.
        self.assertLess(peak_rss_bytes() - before, 5 * size)


def peak_rss_bytes():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes and Linux reports kilobytes.
    return peak if sys.platform == "darwin" else peak * 1024


if __name__ == '__main__':
    unittest.main()
