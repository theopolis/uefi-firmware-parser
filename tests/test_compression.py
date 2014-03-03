import unittest
import struct

from uefi_firmware import efi_compressor

class CompressionTest(unittest.TestCase):
    def test_efi_compress(self):
        default_buffer = "AAAAAAAA"*90
        compressed_buffer = efi_compressor.EfiCompress(default_buffer, len(default_buffer))

        self.assertTrue(compressed_buffer != None)
        self.assertGreater(len(compressed_buffer), 8)

        compressed_size, uncompressed_size = struct.unpack("<II", compressed_buffer[:8])
        self.assertEqual(len(compressed_buffer)-8, compressed_size)

    def test_efi_decompress(self):
        default_buffer = "AAAAAAAA"*90
        compressed_buffer = efi_compressor.EfiCompress(default_buffer, len(default_buffer))
        decompressed_buffer = efi_compressor.EfiDecompress(compressed_buffer, len(compressed_buffer))

        self.assertTrue(decompressed_buffer != None)
        self.assertEqual(len(decompressed_buffer), len(default_buffer))
        self.assertEqual(str(decompressed_buffer), str(default_buffer))

    def test_tiano_compress(self):
        default_buffer = "AAAAAAAA"*90
        compressed_buffer = efi_compressor.TianoCompress(default_buffer, len(default_buffer))

        self.assertTrue(compressed_buffer != None)
        self.assertGreater(len(compressed_buffer), 8)

        compressed_size, uncompressed_size = struct.unpack("<II", compressed_buffer[:8])
        self.assertEqual(len(compressed_buffer)-8, compressed_size)

    def test_tiano_decompress(self):
        default_buffer = "AAAAAAAA"*90
        compressed_buffer = efi_compressor.TianoCompress(default_buffer, len(default_buffer))
        decompressed_buffer = efi_compressor.TianoDecompress(compressed_buffer, len(compressed_buffer))

        self.assertTrue(decompressed_buffer != None)
        self.assertEqual(len(decompressed_buffer), len(default_buffer))
        self.assertEqual(str(decompressed_buffer), str(default_buffer))

if __name__ == '__main__':
    #default_buffer = "AAAAAAAA"
    #t = efi_compressor.TianoCompress(default_buffer, len(default_buffer))
    #print len(default_buffer), len(str(t))
    #print struct.unpack("<II", t[:8])

    unittest.main()