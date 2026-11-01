import struct
import unittest

from uefi_firmware.uefi import NVARVariableStore


class NVARVariableStoreTest(unittest.TestCase):

    def test_zero_size_variable_stops_parsing(self):
        # An NVAR header whose TotalSize is 0 must not make the store loop
        # forever on the same offset.
        data = b"NVAR" + struct.pack("<H", 0) + b"\x00" * 26
        store = NVARVariableStore(data)

        self.assertTrue(store.process())
        self.assertEqual(store.variables, [])

    def test_variable_size_is_used_to_advance(self):
        variable = b"NVAR" + struct.pack("<H", 16) + b"\x00" * 3 + b"\x00" + b"\x00" * 6
        store = NVARVariableStore(variable * 2)

        self.assertTrue(store.process())
        self.assertEqual(len(store.variables), 2)


if __name__ == '__main__':
    unittest.main()
