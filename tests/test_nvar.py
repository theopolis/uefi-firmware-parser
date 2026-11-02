import struct
import unittest

from uefi_firmware.uefi import NVARVariable, NVARVariableStore

VARIABLE_GUID = bytes(range(16))
ATTR_VALID = 0x80
ATTR_ASCII_NAME = 0x02
ATTR_GUID = 0x04


def make_variable(attributes, body):
    size = 10 + len(body)
    return b"NVAR" + struct.pack("<H", size) + b"\xff" * 3 + \
        bytes([attributes]) + body


class NVARVariableTest(unittest.TestCase):

    def parse(self, attributes, name):
        variable = NVARVariable(make_variable(
            ATTR_VALID | ATTR_GUID | attributes,
            VARIABLE_GUID + name + b"VALUE"))
        self.assertTrue(variable.process())
        return variable

    def test_utf16_name(self):
        # The last character's high byte and the terminator's first byte
        # form a zero pair at an odd offset, which matched before.
        variable = self.parse(0, "Setup\0".encode("utf-16le"))
        self.assertEqual(variable.name, "Setup")
        self.assertEqual(variable.data[variable.data_offset:], b"VALUE")

    def test_ascii_name(self):
        variable = self.parse(ATTR_ASCII_NAME, b"Setup\0")
        self.assertEqual(variable.name, "Setup")
        self.assertEqual(variable.data[variable.data_offset:], b"VALUE")

    def test_name_that_does_not_decode_is_still_skipped(self):
        variable = self.parse(0, "Sétup\0".encode("utf-16le"))
        self.assertIsNone(variable.name)
        self.assertEqual(variable.data[variable.data_offset:], b"VALUE")


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
