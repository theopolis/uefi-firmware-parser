import os
import tempfile
import unittest

from uefi_firmware.utils import dump_data, safe_path, safe_path_component


class DumpPathTest(unittest.TestCase):

    def test_safe_path_component_removes_path_separators(self):
        self.assertEqual(safe_path_component("../testing.partition"), ".._testing.partition")
        self.assertEqual(safe_path_component("/tmp/testing.fv"), "_tmp_testing.fv")
        self.assertEqual(safe_path_component("C:\\tmp\\testing.fv"), "C__tmp_testing.fv")
        self.assertEqual(safe_path_component(".."), "_")

    def test_safe_path_confines_untrusted_component_to_parent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "out")
            target = safe_path(output_dir, "../testing.partition")

            dump_data(target, b"test")

            self.assertTrue(os.path.exists(os.path.join(output_dir, ".._testing.partition")))
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "testing.partition")))


if __name__ == '__main__':
    unittest.main()