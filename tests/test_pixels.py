import unittest

from stand_up_reminder import pixels


class PaletteTests(unittest.TestCase):
    def test_the_palette_is_the_eleven_named_colours(self):
        self.assertEqual(
            set(pixels.PALETTE),
            {
                "void",
                "ink",
                "slate",
                "edge",
                "bone",
                "mist",
                "amber",
                "coral",
                "mint",
                "sky",
                "plum",
            },
        )

    def test_colours_are_six_digit_hex(self):
        for name, value in pixels.PALETTE.items():
            with self.subTest(name):
                self.assertRegex(value, r"^#[0-9a-f]{6}$")

    def test_one_art_pixel_is_four_real_pixels(self):
        self.assertEqual(pixels.ART, 4)
        self.assertEqual(pixels.ap(3), 12)


class ProgressCellTests(unittest.TestCase):
    def test_a_full_break_lights_every_cell(self):
        self.assertEqual(pixels.filled_cells(120, 120), 27)

    def test_cells_die_from_the_right_as_time_runs_out(self):
        self.assertEqual(pixels.filled_cells(60, 120), 13)
        self.assertEqual(pixels.filled_cells(0, 120), 0)

    def test_a_missing_total_leaves_the_bar_empty(self):
        self.assertEqual(pixels.filled_cells(30, 0), 0)

    def test_the_last_five_cells_are_urgent(self):
        self.assertFalse(pixels.cells_urgent(5))
        self.assertTrue(pixels.cells_urgent(4))
        self.assertTrue(pixels.cells_urgent(0))


class BandTests(unittest.TestCase):
    def test_score_colour_bands(self):
        self.assertEqual(pixels.band_color(70), pixels.PALETTE["mint"])
        self.assertEqual(pixels.band_color(40), pixels.PALETTE["amber"])
        self.assertEqual(pixels.band_color(39), pixels.PALETTE["coral"])

    def test_mood_glyph_bands(self):
        self.assertEqual(pixels.mood_glyph(85), "spark")
        self.assertEqual(pixels.mood_glyph(70), "up")
        self.assertEqual(pixels.mood_glyph(50), "flat")
        self.assertEqual(pixels.mood_glyph(49), "down")

    def test_face_expression_bands(self):
        self.assertEqual(pixels.face_expression(85), "grin1")
        self.assertEqual(pixels.face_expression(50), "rest")
        self.assertEqual(pixels.face_expression(49), "flat")

    def test_an_unscored_day_reads_as_flat(self):
        self.assertEqual(pixels.mood_glyph(None), "flat")
        self.assertEqual(pixels.face_expression(None), "rest")
        self.assertEqual(pixels.band_color(None), pixels.PALETTE["mist"])


class PillRowTests(unittest.TestCase):
    def test_under_an_hour_stacks_minutes_over_seconds(self):
        self.assertEqual(pixels.pill_rows(0), ("00", "00"))
        self.assertEqual(pixels.pill_rows(75), ("01", "15"))
        self.assertEqual(pixels.pill_rows(59 * 60 + 59), ("59", "59"))

    def test_past_an_hour_an_hours_row_opens_on_top(self):
        self.assertEqual(pixels.pill_rows(3600), ("01", "00", "00"))
        self.assertEqual(pixels.pill_rows(3671), ("01", "01", "11"))

    def test_the_pill_clamps_at_ten_hours(self):
        self.assertEqual(pixels.pill_rows(10 * 3600), ("09", "59", "59"))

    def test_negative_time_reads_as_zero(self):
        self.assertEqual(pixels.pill_rows(-5), ("00", "00"))

    def test_the_pill_grows_downward_for_the_hours_row(self):
        self.assertEqual(pixels.pill_height(("00", "00")), 39 * pixels.ART)
        self.assertEqual(pixels.pill_height(("01", "00", "00")), 49 * pixels.ART)


class TimelineMarkTests(unittest.TestCase):
    def test_marks_are_snapped_to_the_art_grid(self):
        marks = pixels.timeline_marks([(0.0, "taken"), (1.0, "missed")], 108)
        self.assertEqual(marks[0][0], 0)
        self.assertEqual(marks[-1][0], 106)

    def test_marks_closer_than_three_art_pixels_merge(self):
        marks = pixels.timeline_marks(
            [(0.10, "taken"), (0.11, "missed")], 108
        )
        self.assertEqual(len(marks), 1)

    def test_a_merged_mark_takes_the_later_outcome(self):
        marks = pixels.timeline_marks(
            [(0.10, "taken"), (0.11, "missed")], 108
        )
        self.assertEqual(marks[0][1], "missed")

    def test_marks_further_apart_are_kept_separate(self):
        marks = pixels.timeline_marks([(0.0, "taken"), (0.5, "away")], 108)
        self.assertEqual([outcome for _x, outcome in marks], ["taken", "away"])

    def test_outcomes_have_their_own_colours(self):
        self.assertEqual(pixels.MARK_COLORS["taken"], pixels.PALETTE["mint"])
        self.assertEqual(pixels.MARK_COLORS["away"], pixels.PALETTE["sky"])
        self.assertEqual(pixels.MARK_COLORS["missed"], pixels.PALETTE["coral"])
        self.assertEqual(pixels.MARK_COLORS["skipped"], pixels.PALETTE["edge"])
        self.assertEqual(pixels.MARK_COLORS["snoozed"], pixels.PALETTE["plum"])


class HeatTests(unittest.TestCase):
    def test_five_flat_shades_from_slate_to_mint(self):
        self.assertEqual(pixels.heat_hex(None), pixels.PALETTE["slate"])
        self.assertEqual(pixels.heat_hex(0), "#255c45")
        self.assertEqual(pixels.heat_hex(3), pixels.PALETTE["mint"])


class HeatGridTests(unittest.TestCase):
    def test_the_grid_is_twelve_columns_of_square_tiles(self):
        width, height = pixels.heat_grid_size(12)
        # 16 ap of labels, a 2 ap gap, then 12 tiles of 8 ap with 2 ap gutters.
        self.assertEqual(width, pixels.ap(16 + 2 + 12 * 8 + 11 * 2))
        self.assertEqual(height, pixels.ap(7 * 8 + 6 * 2))

    def test_a_point_inside_a_tile_names_its_column_and_row(self):
        left = pixels.ap(18)
        self.assertEqual(pixels.heat_tile_at(left, 0, 12), (0, 0))
        self.assertEqual(
            pixels.heat_tile_at(left + pixels.ap(10), pixels.ap(10), 12), (1, 1)
        )

    def test_gutters_and_margins_belong_to_no_tile(self):
        left = pixels.ap(18)
        self.assertIsNone(pixels.heat_tile_at(left + pixels.ap(9), 0, 12))
        self.assertIsNone(pixels.heat_tile_at(0, 0, 12))
        self.assertIsNone(pixels.heat_tile_at(left, pixels.ap(200), 12))


class WipeTests(unittest.TestCase):
    def test_the_card_wipes_from_the_centre_out(self):
        self.assertEqual(pixels.WIPE_ORDER, (2, 3, 1, 4, 0, 5))

    def test_every_band_is_revealed_once(self):
        self.assertEqual(sorted(pixels.WIPE_ORDER), list(range(6)))


if __name__ == "__main__":
    unittest.main()
