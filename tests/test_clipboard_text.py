import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "tools"))
from clipboard_companion import decode_clipboard_text


class ClipboardTextTests(unittest.TestCase):
    def test_allocation_garbage_after_terminator_is_not_decoded(self):
        data="Киндрих\0".encode("utf-16-le")+b"\xff"
        self.assertEqual(decode_clipboard_text(data),"Киндрих")

    def test_terminator_must_be_aligned_to_utf16_units(self):
        self.assertEqual(decode_clipboard_text("A\0".encode("utf-16-le")),"A")

    def test_invalid_unterminated_allocation_rejected(self):
        with self.assertRaises(ValueError): decode_clipboard_text(b"A\0")


if __name__=="__main__": unittest.main()
