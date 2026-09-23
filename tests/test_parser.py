import unittest

from rtf_parser import parse_rtf


class ParserTests(unittest.TestCase):
    def test_requires_rtf_header(self):
        with self.assertRaises(ValueError):
            parse_rtf(b"plain text")

    def test_text_controls_and_groups(self):
        doc = parse_rtf(r"{\rtf1\ansi Hello \b bold\b0\par second\tab column}")
        self.assertEqual(doc.text, "Hello bold\nsecond\tcolumn")
        bold = [span for span in doc.spans if span.style.bold]
        self.assertEqual(doc.text[bold[0].start:bold[0].end], "bold")

    def test_unicode_and_cp1252_hex(self):
        doc = parse_rtf(r"{\rtf1\ansi\ansicpg1252 Caf\'e9 \u9731?}")
        self.assertEqual(doc.text, "Café ☃")

    def test_source_line_endings_are_not_document_breaks(self):
        doc = parse_rtf("{\\rtf1\\ansi\nHello\r\nworld\\par next}")
        self.assertEqual(doc.text, "Helloworld\nnext")

    def test_unicode_surrogate_pair(self):
        doc = parse_rtf(r"{\rtf1\ansi Smile: \u-10179?\u-8704?}")
        self.assertEqual(doc.text, "Smile: 😀")

    def test_ignores_unsafe_destinations(self):
        doc = parse_rtf(r"{\rtf1 visible {\object secret} text {\*\unknown hidden}}")
        self.assertEqual(doc.text, "visible  text ")

    def test_colors_and_metadata(self):
        raw = r"{\rtf1{\fonttbl{\f0 Arial;}}{\colortbl;\red255\green0\blue0;}{\info{\title Notes}{\author Ada}}\f0\cf1 Red}"
        doc = parse_rtf(raw)
        self.assertEqual(doc.text, "Red")
        self.assertEqual(doc.title, "Notes")
        self.assertEqual(doc.author, "Ada")
        self.assertEqual(doc.spans[-1].style.foreground, "#ff0000")


if __name__ == "__main__":
    unittest.main()
