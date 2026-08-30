import unittest

from stand_up_reminder import eyes


class PromptTests(unittest.TestCase):
    def test_each_prompt_is_named_once_and_dressed(self):
        keys = [prompt.key for prompt in eyes.PROMPTS]
        self.assertEqual(len(keys), len(set(keys)))
        for prompt in eyes.PROMPTS:
            with self.subTest(prompt.key):
                self.assertTrue(prompt.title)
                self.assertTrue(prompt.setting_label)
                self.assertTrue(prompt.accent)
                self.assertTrue(prompt.body)

    def test_every_turn_of_the_rotation_names_a_real_prompt(self):
        known = {prompt.key for prompt in eyes.PROMPTS}
        self.assertTrue(set(eyes.ROTATION) <= known)

    def test_the_settings_module_bounds_the_rotation_correctly(self):
        # settings keeps its own length so it need not import this module;
        # this is what stops the two drifting apart.
        from stand_up_reminder.settings import EYE_ROTATION_LENGTH

        self.assertEqual(len(eyes.ROTATION), EYE_ROTATION_LENGTH)

    def test_looking_far_takes_four_turns_in_six(self):
        self.assertEqual(eyes.ROTATION.count("far"), 4)
        self.assertEqual(len(eyes.ROTATION), 6)


class RotationTests(unittest.TestCase):
    def test_the_rotation_walks_in_order(self):
        prompt, index = eyes.next_prompt(0, frozenset())
        self.assertEqual(prompt.key, eyes.ROTATION[0])
        self.assertEqual(index, 1)

    def test_the_rotation_wraps_round(self):
        _prompt, index = eyes.next_prompt(len(eyes.ROTATION) - 1, frozenset())
        self.assertEqual(index, 0)

    def test_a_muted_prompt_is_stepped_over(self):
        prompt, _index = eyes.next_prompt(2, frozenset({"shut"}))
        self.assertNotEqual(prompt.key, "shut")

    def test_muting_everything_leaves_nothing_to_show(self):
        self.assertIsNone(eyes.next_prompt(0, frozenset({"far", "shut", "move"})))

    def test_the_index_after_a_skip_carries_on_past_what_was_shown(self):
        prompt, index = eyes.next_prompt(2, frozenset({"shut"}))
        self.assertEqual(prompt.key, eyes.ROTATION[3])
        self.assertEqual(index, 4)


class DueTests(unittest.TestCase):
    def test_nothing_is_due_inside_the_interval(self):
        self.assertFalse(eyes.eye_due(0, 1199, 1200))

    def test_the_card_falls_due_on_the_interval(self):
        self.assertTrue(eyes.eye_due(1199, 1200, 1200))

    def test_a_skipped_tick_still_owes_the_card(self):
        self.assertTrue(eyes.eye_due(1190, 1230, 1200))

    def test_a_clock_that_does_not_advance_owes_nothing(self):
        self.assertFalse(eyes.eye_due(1200, 1200, 1200))
        self.assertFalse(eyes.eye_due(1500, 1200, 1200))


class ShutFrameTests(unittest.TestCase):
    def test_the_lids_come_down_first(self):
        frame = eyes.shut_frame(0)
        self.assertEqual(frame.lid, 0.0)
        self.assertEqual(eyes.shut_frame(700).lid, 1.0)

    def test_three_squeezes_follow_the_close(self):
        self.assertTrue(eyes.shut_frame(1000).tight)
        self.assertFalse(eyes.shut_frame(2200).tight)
        self.assertTrue(eyes.shut_frame(3000).tight)
        self.assertTrue(eyes.shut_frame(4800).tight)

    def test_the_squeezes_are_counted_off(self):
        self.assertEqual(eyes.shut_frame(0).pips, 0)
        self.assertEqual(eyes.shut_frame(1000).pips, 1)
        self.assertEqual(eyes.shut_frame(2200).pips, 1)
        self.assertEqual(eyes.shut_frame(3000).pips, 2)
        self.assertEqual(eyes.shut_frame(4800).pips, 3)

    def test_the_rest_is_the_longest_part(self):
        frame = eyes.shut_frame(12000)
        self.assertFalse(frame.tight)
        self.assertEqual(frame.lid, 1.0)
        self.assertEqual(frame.phase, "REST")

    def test_the_eyes_open_again_at_the_end(self):
        self.assertLess(eyes.shut_frame(19700).lid, 1.0)
        self.assertEqual(eyes.shut_frame(20000).lid, 0.0)

    def test_each_stretch_says_what_it_wants(self):
        self.assertEqual(eyes.shut_frame(300).phase, "CLOSE")
        self.assertEqual(eyes.shut_frame(1000).phase, "SQUEEZE")
        self.assertEqual(eyes.shut_frame(2200).phase, "LET GO")
        self.assertEqual(eyes.shut_frame(19700).phase, "OPEN")

    def test_a_squeeze_begins_on_each_of_three_known_beats(self):
        self.assertEqual(eyes.SQUEEZE_BEATS, (700, 2700, 4700))


class MoveStationTests(unittest.TestCase):
    def test_the_walk_starts_and_returns_to_the_middle(self):
        self.assertEqual(eyes.move_station(0), "C")
        self.assertEqual(eyes.move_station(4000), "C")

    def test_the_cardinals_come_before_the_circle(self):
        self.assertEqual(
            [eyes.move_station(n * 800) for n in range(1, 5)],
            ["W", "E", "N", "S"],
        )

    def test_every_station_has_a_gaze_and_a_corner(self):
        for name in eyes.STATIONS:
            with self.subTest(name):
                self.assertIn(name, eyes.GAZE)
        self.assertEqual(eyes.GAZE["C"], (0, 0))

    def test_the_walk_repeats_once_it_runs_out(self):
        period = len(eyes.SEQUENCE) * 800
        self.assertEqual(eyes.move_station(period), eyes.move_station(0))

    def test_a_gaze_never_leaves_the_eye(self):
        for name, offset in eyes.GAZE.items():
            with self.subTest(name):
                self.assertLessEqual(abs(offset[0]), 3)
                self.assertLessEqual(abs(offset[1]), 2)


class WindowSceneTests(unittest.TestCase):
    def test_the_clouds_drift_one_art_pixel_at_a_time(self):
        self.assertEqual(eyes.cloud_offset(0, 1), eyes.cloud_offset(399, 1))
        self.assertNotEqual(eyes.cloud_offset(0, 1), eyes.cloud_offset(400, 1))

    def test_the_clouds_drift_in_opposite_directions(self):
        rightward = eyes.cloud_offset(2000, 1) - eyes.cloud_offset(1600, 1)
        leftward = eyes.cloud_offset(2000, -1) - eyes.cloud_offset(1600, -1)
        self.assertEqual(rightward, 1)
        self.assertEqual(leftward, -1)

    def test_a_drifting_cloud_wraps_rather_than_leaving(self):
        for ms in range(0, 40_000, 400):
            with self.subTest(ms):
                self.assertGreaterEqual(eyes.cloud_offset(ms, 1), -4)
                self.assertLess(eyes.cloud_offset(ms, 1), 36)

    def test_the_sun_flickers_on_a_half_second(self):
        self.assertTrue(eyes.sun_lit(0))
        self.assertFalse(eyes.sun_lit(500))
        self.assertTrue(eyes.sun_lit(1000))

    def test_a_bird_crosses_and_then_leaves_the_sky_alone(self):
        self.assertIsNotNone(eyes.bird_x(0))
        self.assertIsNone(eyes.bird_x(4000))


class ScheduleTests(unittest.TestCase):
    def test_a_card_lasts_twenty_seconds(self):
        self.assertEqual(eyes.CARD_SECONDS, 20)

    def test_the_offered_intervals_bracket_the_recommendation(self):
        self.assertEqual(eyes.INTERVAL_PRESETS, (15 * 60, 20 * 60, 30 * 60))
        self.assertIn(eyes.DEFAULT_INTERVAL_SECONDS, eyes.INTERVAL_PRESETS)
        self.assertEqual(eyes.DEFAULT_INTERVAL_SECONDS, 20 * 60)


if __name__ == "__main__":
    unittest.main()
