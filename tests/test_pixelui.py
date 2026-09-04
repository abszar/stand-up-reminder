import unittest
from types import SimpleNamespace

from stand_up_reminder import pixelui as ui


def area(x=0, y=0, width=1920, height=1080):
    return SimpleNamespace(x=x, y=y, width=width, height=height)


class CornerPlaceTests(unittest.TestCase):
    def test_pins_the_card_to_the_bottom_right(self):
        self.assertEqual(
            ui.corner_place(area(), 300, 200, 12), (1920 - 300 - 12, 1080 - 200 - 12)
        )

    def test_honours_the_work_area_origin(self):
        spot = ui.corner_place(area(x=96, y=40, width=3744, height=2075), 300, 200, 12)
        self.assertEqual(spot, (96 + 3744 - 300 - 12, 40 + 2075 - 200 - 12))

    def test_a_wider_card_keeps_the_same_right_edge(self):
        narrow = ui.corner_place(area(), 300, 200, 12)
        wide = ui.corner_place(area(), 460, 200, 12)
        self.assertEqual(narrow[0] + 300, wide[0] + 460)

    def test_a_pill_on_the_same_rows_pushes_the_card_left(self):
        rows = (1080 - 100, 1080, 56)
        self.assertEqual(
            ui.corner_place(area(), 300, 200, 12, pill=rows)[0],
            1920 - 300 - 12 - 56 - 12,
        )

    def test_a_pill_on_other_rows_leaves_the_card_in_the_corner(self):
        rows = (100, 300, 56)
        self.assertEqual(
            ui.corner_place(area(), 300, 200, 12, pill=rows),
            ui.corner_place(area(), 300, 200, 12),
        )

    def test_the_drop_offsets_the_card_downwards(self):
        top = ui.corner_place(area(), 300, 200, 12)[1]
        self.assertEqual(ui.corner_place(area(), 300, 200, 12, drop=36)[1], top + 36)


if __name__ == "__main__":
    unittest.main()
