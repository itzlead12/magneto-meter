import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from main import parse_reading, save_graph_png


class ParseReadingTests(unittest.TestCase):
    def test_parses_comma_separated_values(self):
        self.assertEqual(parse_reading("12.3,-4.5,38.0"), (12.3, -4.5, 38.0))

    def test_parses_labeled_values(self):
        self.assertEqual(parse_reading("X=12.3, Y=-4.5, Z=38.0"), (12.3, -4.5, 38.0))

    def test_parses_exponents_and_whitespace(self):
        self.assertEqual(parse_reading("1e2  -2.5E-1  .75"), (100.0, -0.25, 0.75))

    def test_ignores_lines_without_three_numbers(self):
        self.assertIsNone(parse_reading("Waiting for sensor"))
        self.assertIsNone(parse_reading("X=1, Y=2"))

    def test_uses_last_three_numbers_from_prefixed_metadata(self):
        self.assertEqual(parse_reading("sample 8: 1, 2, 3"), (1.0, 2.0, 3.0))

    def test_saves_graph_png_with_samples(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plot.png"
            save_graph_png(path, [(1.0, 2.0, 3.0), (3.0, 1.0, -1.0)], 400, 240)
            with Image.open(path) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (400, 240))
                colors = {color for _count, color in image.getcolors(400 * 240) or []}
                self.assertIn((255, 107, 107), colors)
                self.assertIn((84, 214, 160), colors)
                self.assertIn((105, 170, 252), colors)

    def test_saves_empty_graph_png(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "empty.png"
            save_graph_png(path, [], 400, 240)
            with Image.open(path) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (400, 240))


if __name__ == "__main__":
    unittest.main()
