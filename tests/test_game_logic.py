import unittest

from test_support import ServerModuleLoader


class GameLogicTests(unittest.TestCase):
    def setUp(self):
        self.loader = ServerModuleLoader(SNAKE_TICK_RATE=6)
        self.config, self.game_module, _ = self.loader.load()

    def tearDown(self):
        self.loader.restore()

    def test_respawn_preserves_public_id_and_resets_score(self):
        game = self.game_module.Game()
        snake = game.spawn_snake("k1", "Alpha")
        snake.score = 7
        public_id = snake.public_id
        next_public_id_before = game._next_public_id

        respawned = game.respawn_snake("k1")

        self.assertIsNotNone(respawned)
        self.assertEqual(respawned.public_id, public_id)
        self.assertEqual(respawned.score, 0)
        self.assertEqual(game.get_public_id("k1"), public_id)
        self.assertEqual(game._next_public_id, next_public_id_before)

    def test_remove_snake_finalizes_live_statistics(self):
        game = self.game_module.Game()
        snake = game.spawn_snake("k2", "Beta")
        snake.life_ticks = 5
        snake.length_accumulator = 23

        game.remove_snake("k2")

        stats = game.career_stats["k2"]
        self.assertEqual(stats.completed_lives, 1)
        self.assertEqual(stats.total_life_ticks, 5)
        self.assertEqual(stats.total_length_accumulator, 23)

    def test_set_direction_blocks_opposite_turn(self):
        game = self.game_module.Game()
        snake = game.spawn_snake("k3", "Gamma")
        snake.direction = "right"

        game.set_direction("k3", "left")

        self.assertIsNone(snake.pending_direction)

    def test_stale_observed_tick_is_only_rejected_in_strict_mode(self):
        game = self.game_module.Game()
        snake = game.spawn_snake("k5", "Epsilon")
        snake.direction = "up"
        game.tick_count = 10

        game.set_direction("k5", "right", observed_tick=9)

        self.assertEqual(snake.pending_direction, "right")
        self.assertEqual(snake.pending_state_tick, 9)

        snake.pending_direction = None
        snake.pending_state_tick = None
        game.strict_observed_tick = True

        game.set_direction("k5", "right", observed_tick=9)

        self.assertIsNone(snake.pending_direction)
        self.assertIsNone(snake.pending_state_tick)

        game.set_direction("k5", "right", observed_tick=10)

        self.assertEqual(snake.pending_direction, "right")
        self.assertEqual(snake.pending_state_tick, 10)

    def test_performance_stats_include_current_life(self):
        game = self.game_module.Game()
        snake = game.spawn_snake("k4", "Delta")
        snake.life_ticks = 4
        snake.length_accumulator = 18

        stats = game.get_performance_stats()

        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["rounds"], 1)
        self.assertEqual(stats[0]["avg_length"], 4.5)
        self.assertAlmostEqual(stats[0]["avg_survival_seconds"], 4 / self.config.TICK_RATE, places=2)