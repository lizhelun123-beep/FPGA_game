"""Reject corrupt ABI evidence before producing a prepared build package."""
import io
import struct
import unittest

from pynq_vision.prepare_kernel_sdk import check_symbol_versions, elf_sections, root_partition


def arm_module(crc=0x12345678):
    names = b"\0.shstrtab\0__versions\0"
    records = struct.pack("<I60s", crc, b"module_layout")
    header = b"\x7fELF\x01\x01\x01" + bytes(9)
    header += struct.pack("<HHIIIIIHHHHHH", 1, 40, 1, 0, 0, 52, 0, 52, 0, 0, 40, 3, 1)
    sections = bytes(40)
    sections += struct.pack("<10I", 1, 3, 0, 0, 172, len(names), 0, 0, 1, 0)
    sections += struct.pack("<10I", 11, 1, 0, 0, 172 + len(names), len(records), 0, 0, 4, 0)
    return header + sections + names + records


class KernelSdkEvidenceTests(unittest.TestCase):
    def test_matching_import_crc(self):
        result = check_symbol_versions(arm_module(), b"0x12345678\tmodule_layout\tvmlinux\tEXPORT_SYMBOL\n")
        self.assertEqual(result["imports"], 1)

    def test_changed_or_missing_import_crc_is_rejected(self):
        for table in (b"0x87654321 module_layout vmlinux\n", b"0x12345678 other_symbol vmlinux\n"):
            with self.subTest(table=table), self.assertRaises(ValueError):
                check_symbol_versions(arm_module(), table)

    def test_truncated_elf_is_rejected(self):
        for size in (0, 16, 51, 100, 180):
            with self.subTest(size=size), self.assertRaises(ValueError):
                elf_sections(arm_module()[:size])

    def test_wrong_target_is_rejected(self):
        module = bytearray(arm_module())
        struct.pack_into("<H", module, 18, 62)  # x86-64 cannot qualify ARM32.
        with self.assertRaises(ValueError):
            elf_sections(module)

    def test_partition_cannot_escape_image(self):
        mbr = bytearray(512)
        mbr[510:512] = b"\x55\xaa"
        mbr[450] = 0x83
        struct.pack_into("<II", mbr, 454, 2048, 4096)
        with self.assertRaises(ValueError):
            root_partition(io.BytesIO(mbr), 512)


if __name__ == "__main__":
    unittest.main()
