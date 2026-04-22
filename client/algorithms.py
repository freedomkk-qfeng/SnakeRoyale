import random
from collections import deque

from sdk import BaseSnakeAlgorithm, ClientContext, DIRECTIONS


def _collect_obstacles(state: dict, head: tuple[int, int]) -> set[tuple[int, int]]:
    obstacles: set[tuple[int, int]] = set()
    for snake in state.get("snakes", []):
        for body_part in snake.get("body", []):
            obstacles.add(tuple(body_part))
    obstacles.discard(head)
    return obstacles


def _find_safe_moves(
    head: tuple[int, int],
    obstacles: set[tuple[int, int]],
    context: ClientContext,
) -> dict[str, tuple[int, int]]:
    safe_moves: dict[str, tuple[int, int]] = {}
    for direction, (dx, dy) in DIRECTIONS.items():
        nx, ny = head[0] + dx, head[1] + dy
        if 0 <= nx < context.field_width and 0 <= ny < context.field_height and (nx, ny) not in obstacles:
            safe_moves[direction] = (nx, ny)
    return safe_moves


class BFSAlgorithm(BaseSnakeAlgorithm):
    def decide(self, state: dict, context: ClientContext) -> str:
        my_snake = context.get_my_snake(state)
        if not my_snake or not my_snake.get("body"):
            return "right"

        head = tuple(my_snake["body"][0])
        foods = {tuple(food) for food in state.get("foods", [])}
        obstacles = _collect_obstacles(state, head)
        safe_moves = _find_safe_moves(head, obstacles, context)

        if not safe_moves:
            return my_snake.get("direction", "right")

        if foods:
            best_direction = self._bfs_to_food(head, foods, obstacles, safe_moves, context)
            if best_direction:
                return best_direction

        best_direction = None
        best_space = -1
        for direction, position in safe_moves.items():
            reachable = self._count_reachable(position, obstacles, context)
            if reachable > best_space:
                best_space = reachable
                best_direction = direction

        return best_direction or my_snake.get("direction", "right")

    def _bfs_to_food(
        self,
        head: tuple[int, int],
        foods: set[tuple[int, int]],
        obstacles: set[tuple[int, int]],
        safe_moves: dict[str, tuple[int, int]],
        context: ClientContext,
    ) -> str | None:
        visited = {head}
        queue = deque()
        for direction, position in safe_moves.items():
            if position in foods:
                return direction
            queue.append((position, direction))
            visited.add(position)

        steps = 0
        max_search = 500
        while queue and steps < max_search:
            position, first_direction = queue.popleft()
            steps += 1

            for dx, dy in DIRECTIONS.values():
                nx, ny = position[0] + dx, position[1] + dy
                next_position = (nx, ny)
                if next_position in visited:
                    continue
                if not (0 <= nx < context.field_width and 0 <= ny < context.field_height):
                    continue
                if next_position in obstacles:
                    continue
                if next_position in foods:
                    return first_direction
                visited.add(next_position)
                queue.append((next_position, first_direction))

        return None

    def _count_reachable(
        self,
        start: tuple[int, int],
        obstacles: set[tuple[int, int]],
        context: ClientContext,
        limit: int = 50,
    ) -> int:
        visited = {start}
        queue = deque([start])
        count = 0
        while queue and count < limit:
            position = queue.popleft()
            count += 1
            for dx, dy in DIRECTIONS.values():
                nx, ny = position[0] + dx, position[1] + dy
                next_position = (nx, ny)
                if next_position in visited:
                    continue
                if not (0 <= nx < context.field_width and 0 <= ny < context.field_height):
                    continue
                if next_position in obstacles:
                    continue
                visited.add(next_position)
                queue.append(next_position)
        return count


class RandomAlgorithm(BaseSnakeAlgorithm):
    def decide(self, state: dict, context: ClientContext) -> str:
        my_snake = context.get_my_snake(state)
        if not my_snake or not my_snake.get("body"):
            return "right"

        head = tuple(my_snake["body"][0])
        obstacles = _collect_obstacles(state, head)
        safe_moves = _find_safe_moves(head, obstacles, context)
        if not safe_moves:
            return my_snake.get("direction", "right")
        return random.choice(sorted(safe_moves))


ALGORITHMS = {
    "bfs": BFSAlgorithm,
    "random": RandomAlgorithm,
}


def create_algorithm(name: str) -> BaseSnakeAlgorithm:
    normalized_name = name.strip().lower()
    if normalized_name not in ALGORITHMS:
        raise ValueError(f"Unknown algorithm {name!r}; choose from {', '.join(sorted(ALGORITHMS))}")
    return ALGORITHMS[normalized_name]()