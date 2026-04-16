import random
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

FIELD_WIDTH = 100
FIELD_HEIGHT = 100
INITIAL_LENGTH = 3
TICK_RATE = 10  # ticks per second
MIN_FOOD = 5
FOOD_PER_SNAKE = 1
FOOD_DECAY_RATE = 0.002  # fraction of drop-food removed per tick

DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

OPPOSITE = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
}


@dataclass
class Snake:
    id: str
    name: str
    public_id: int = 0
    body: deque = field(default_factory=deque)  # body[0] = head
    direction: str = "right"
    alive: bool = True
    score: int = 0
    pending_direction: Optional[str] = None

    @property
    def head(self):
        return self.body[0] if self.body else None


class Game:
    def __init__(self):
        self.snakes: dict[str, Snake] = {}
        self.foods: set[tuple[int, int]] = set()
        self._natural_foods: set[tuple[int, int]] = set()  # subset of foods spawned by _ensure_food
        self.tick_count = 0
        self._next_public_id = 1
        self.record_name: str = "-"
        self.record_length: int = 0

    def _random_empty_pos(self) -> tuple[int, int]:
        occupied = set()
        for snake in self.snakes.values():
            if snake.alive:
                occupied.update(snake.body)
        occupied.update(self.foods)

        for _ in range(1000):
            x = random.randint(0, FIELD_WIDTH - 1)
            y = random.randint(0, FIELD_HEIGHT - 1)
            if (x, y) not in occupied:
                return (x, y)
        # fallback: just return random pos
        return (random.randint(0, FIELD_WIDTH - 1), random.randint(0, FIELD_HEIGHT - 1))

    def spawn_snake(self, snake_id: str, name: str) -> Snake:
        public_id = self._next_public_id
        self._next_public_id += 1
        # Find a safe spawn area: need INITIAL_LENGTH consecutive cells
        for _ in range(100):
            direction = random.choice(["up", "down", "left", "right"])
            dx, dy = DIRECTIONS[direction]
            # Head position
            hx = random.randint(INITIAL_LENGTH, FIELD_WIDTH - 1 - INITIAL_LENGTH)
            hy = random.randint(INITIAL_LENGTH, FIELD_HEIGHT - 1 - INITIAL_LENGTH)

            body = deque()
            valid = True
            for i in range(INITIAL_LENGTH):
                bx = hx - dx * i
                by = hy - dy * i
                if not (0 <= bx < FIELD_WIDTH and 0 <= by < FIELD_HEIGHT):
                    valid = False
                    break
                body.append((bx, by))

            if valid:
                # Check no collision with existing snakes
                occupied = set()
                for s in self.snakes.values():
                    if s.alive:
                        occupied.update(s.body)
                if not any(pos in occupied for pos in body):
                    snake = Snake(id=snake_id, name=name, public_id=public_id, body=body, direction=direction)
                    self.snakes[snake_id] = snake
                    return snake

        # Fallback spawn
        snake = Snake(
            id=snake_id,
            name=name,
            public_id=public_id,
            body=deque([(FIELD_WIDTH // 2 - i, FIELD_HEIGHT // 2) for i in range(INITIAL_LENGTH)]),
            direction="right",
        )
        self.snakes[snake_id] = snake
        return snake

    def respawn_snake(self, snake_id: str):
        snake = self.snakes.get(snake_id)
        if not snake:
            return
        name = snake.name
        del self.snakes[snake_id]
        new_snake = self.spawn_snake(snake_id, name)
        new_snake.score = 0
        return new_snake

    def remove_snake(self, snake_id: str):
        self.snakes.pop(snake_id, None)

    def set_direction(self, snake_id: str, direction: str):
        snake = self.snakes.get(snake_id)
        if not snake or not snake.alive:
            return
        if direction not in DIRECTIONS:
            return
        # Prevent 180-degree turn (check both current and pending direction)
        current = snake.pending_direction or snake.direction
        if OPPOSITE.get(direction) == current:
            return
        snake.pending_direction = direction

    def _ensure_food(self):
        alive_count = sum(1 for s in self.snakes.values() if s.alive)
        target = max(MIN_FOOD, alive_count * FOOD_PER_SNAKE)
        # Clean up stale references
        self._natural_foods &= self.foods
        while len(self._natural_foods) < target:
            pos = self._random_empty_pos()
            self.foods.add(pos)
            self._natural_foods.add(pos)

    def tick(self) -> dict[str, Optional[str]]:
        """Advance game by one tick. Returns dict of {snake_id: death_reason or None}."""
        self.tick_count += 1
        deaths: dict[str, Optional[str]] = {}

        # Apply pending directions
        for snake in self.snakes.values():
            if snake.alive and snake.pending_direction:
                snake.direction = snake.pending_direction
                snake.pending_direction = None

        # Calculate new head positions
        new_heads: dict[str, tuple[int, int]] = {}
        for sid, snake in self.snakes.items():
            if not snake.alive:
                continue
            dx, dy = DIRECTIONS[snake.direction]
            hx, hy = snake.head
            new_heads[sid] = (hx + dx, hy + dy)

        # Check wall collisions
        for sid, (nx, ny) in new_heads.items():
            if not (0 <= nx < FIELD_WIDTH and 0 <= ny < FIELD_HEIGHT):
                deaths[sid] = "hit wall"

        # Build set of all snake bodies (excluding heads that will move)
        body_cells: dict[tuple[int, int], str] = {}
        tail_cells: set[tuple[int, int]] = set()  # track tails separately
        for sid, snake in self.snakes.items():
            if not snake.alive:
                continue
            for i, pos in enumerate(snake.body):
                if i == 0:  # skip head (it's moving)
                    continue
                if i == len(snake.body) - 1:
                    tail_cells.add(pos)
                body_cells[pos] = sid

        # Check body collisions (allow chasing own tail)
        for sid, new_head in new_heads.items():
            if sid in deaths:
                continue
            if new_head in body_cells:
                victim_owner = body_cells[new_head]
                if victim_owner == sid:
                    # Allow moving into own tail (it will move away)
                    if new_head in tail_cells:
                        continue
                    deaths[sid] = "hit self"
                else:
                    deaths[sid] = f"hit snake {self.snakes[victim_owner].name}"

        # Check head-to-head collisions
        head_positions: dict[tuple[int, int], list[str]] = {}
        for sid, new_head in new_heads.items():
            if sid in deaths:
                continue
            head_positions.setdefault(new_head, []).append(sid)
        for pos, sids in head_positions.items():
            if len(sids) > 1:
                for sid in sids:
                    deaths[sid] = "head-to-head collision"

        # Move surviving snakes
        for sid, new_head in new_heads.items():
            if sid in deaths:
                continue
            snake = self.snakes[sid]
            snake.body.appendleft(new_head)
            if new_head in self.foods:
                # Eat food - don't remove tail
                self.foods.discard(new_head)
                self._natural_foods.discard(new_head)
                snake.score += 1
            else:
                # Remove tail
                snake.body.pop()
            # Track historical record
            if len(snake.body) > self.record_length:
                self.record_length = len(snake.body)
                self.record_name = snake.name

        # Mark dead snakes and drop food from their bodies
        for sid, reason in deaths.items():
            snake = self.snakes[sid]
            for pos in snake.body:
                self.foods.add(pos)
            snake.alive = False

        # Ensure enough food
        self._ensure_food()

        # Decay dropped food (non-natural) to prevent accumulation
        drop_foods = self.foods - self._natural_foods
        if drop_foods:
            expected = len(drop_foods) * FOOD_DECAY_RATE
            remove_count = int(expected)
            # Fractional part becomes probability of one extra removal
            if random.random() < (expected - remove_count):
                remove_count += 1
            if remove_count > 0:
                to_remove = random.sample(list(drop_foods), min(remove_count, len(drop_foods)))
                self.foods -= set(to_remove)

        return deaths

    def get_state(self) -> dict:
        return {
            "type": "state",
            "tick": self.tick_count,
            "field": {"width": FIELD_WIDTH, "height": FIELD_HEIGHT},
            "snakes": [
                {
                    "id": s.public_id,
                    "name": s.name,
                    "body": list(s.body),
                    "direction": s.direction,
                    "alive": s.alive,
                    "score": s.score,
                    "length": len(s.body),
                }
                for s in self.snakes.values()
                if s.alive
            ],
            "foods": list(self.foods),
            "record": {"name": self.record_name, "length": self.record_length},
        }

    def get_public_id(self, snake_id: str) -> Optional[int]:
        """Get the public display ID for a snake."""
        snake = self.snakes.get(snake_id)
        return snake.public_id if snake else None
