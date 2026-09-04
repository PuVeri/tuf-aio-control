from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

import gif_animation


class GifAnimationSchedulerTests(unittest.TestCase):
    def test_source_durations_scale_at_each_supported_speed_with_one_ms_floor(self) -> None:
        scheduler = gif_animation.GifAnimationScheduler()
        state = scheduler.start(
            (0, 300, 600), 0, now=10.0, playback_speed=1.0
        )

        self.assertEqual(state.frame_index, 0)
        self.assertEqual(scheduler.effective_durations_ms, (1, 300, 600))
        self.assertEqual(scheduler.next_deadline, 10.001)
        self.assertEqual(gif_animation.MINIMUM_EFFECTIVE_FRAME_DURATION_MS, 1)
        for speed, expected in (
            (1.0, (1, 300, 600)),
            (1.5, (1, 200, 400)),
            (2.0, (1, 150, 300)),
            (3.0, (1, 100, 200)),
        ):
            scheduler.start((0, 300, 600), 0, now=10.0, playback_speed=speed)
            self.assertEqual(scheduler.effective_durations_ms, expected)

    def test_late_advance_preserves_order_without_skip_or_catch_up_loop(self) -> None:
        scheduler = gif_animation.GifAnimationScheduler()
        scheduler.start((100, 100, 100, 100), 0, now=0.0)

        state = scheduler.advance(now=0.35)
        assert state is not None
        self.assertEqual(state.frame_index, 1)
        self.assertEqual(state.completed_loops, 0)
        self.assertAlmostEqual(scheduler.next_deadline or 0.0, 0.45)
        self.assertIsNone(scheduler.advance(now=0.36))
        next_state = scheduler.advance(now=0.45)
        assert next_state is not None
        self.assertEqual(next_state.frame_index, 2)

    def test_infinite_loop_keeps_running(self) -> None:
        scheduler = gif_animation.GifAnimationScheduler()
        scheduler.start((250, 250), 0, now=1.0)

        first = scheduler.advance(now=2.01)
        second = scheduler.advance(now=2.26)
        assert first is not None and second is not None
        self.assertEqual((first.frame_index, second.frame_index), (1, 0))
        self.assertEqual(second.completed_loops, 1)
        self.assertFalse(second.finished)
        self.assertTrue(scheduler.is_running)

    def test_finite_repetitions_hold_last_frame_without_session_stop(self) -> None:
        scheduler = gif_animation.GifAnimationScheduler()
        scheduler.start((250, 250), 1, now=0.0)

        scheduler.advance(now=0.25)
        scheduler.advance(now=0.5)
        penultimate = scheduler.advance(now=0.75)
        assert penultimate is not None
        self.assertEqual(penultimate.frame_index, 1)
        self.assertEqual(penultimate.completed_loops, 1)
        final = scheduler.advance(now=1.0)
        assert final is not None
        self.assertEqual(final.frame_index, 1)
        self.assertTrue(final.finished)
        self.assertFalse(scheduler.is_running)
        self.assertIsNone(scheduler.next_deadline)

    def test_missing_loop_metadata_plays_once_and_stop_clears_timeline(self) -> None:
        scheduler = gif_animation.GifAnimationScheduler()
        scheduler.start((250, 500), None, now=0.0)
        state = scheduler.advance(now=0.25)
        assert state is not None
        self.assertEqual(state.frame_index, 1)

        scheduler.stop()
        self.assertIsNone(scheduler.state)
        self.assertFalse(scheduler.is_running)
        self.assertIsNone(scheduler.advance(now=10.0))

    def test_speed_change_is_immediate_without_restart_or_frame_jump(self) -> None:
        scheduler = gif_animation.GifAnimationScheduler()
        scheduler.start((200, 100), 0, now=5.0, playback_speed=1.0)

        scheduler.set_playback_speed(2.0, now=5.04)

        self.assertEqual(scheduler.playback_speed, 2.0)
        self.assertEqual(scheduler.effective_durations_ms, (100, 50))
        self.assertAlmostEqual(scheduler.next_deadline or 0.0, 5.1)
        self.assertIsNone(scheduler.advance(now=5.099))
        state = scheduler.advance(now=5.1)
        assert state is not None
        self.assertEqual(state.frame_index, 1)

    def test_scheduler_has_no_frame_queue_or_worker_thread(self) -> None:
        scheduler = gif_animation.GifAnimationScheduler()
        self.assertFalse(hasattr(scheduler, "queue"))
        self.assertFalse(hasattr(scheduler, "_queue"))
        self.assertFalse(hasattr(scheduler, "thread"))
        self.assertFalse(hasattr(scheduler, "_thread"))


if __name__ == "__main__":
    unittest.main()
