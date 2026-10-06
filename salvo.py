#!/usr/bin/env python3
"""Salvo 海战齐射：10x10 海战棋，每轮按各自存活舰船数同时开火。

规则：
- 10x10 棋盘，双方各 5 艘舰船（5/4/3/3/2 格）。
- 每轮双方同时开火，开火数 = 己方当前未沉舰船数。
- 双方炮弹同时结算：本轮被击沉的一方仍能打出本轮炮弹。
- 先击沉对方全部舰船者胜；同轮互沉为和棋。
"""
from __future__ import annotations

import argparse
import random
import sys

SIZE = 10
SHIP_LENGTHS = [5, 4, 3, 3, 2]
SHIP_NAMES = ["航母", "战列舰", "巡洋舰", "护卫舰", "驱逐舰"]


class IllegalMove(Exception):
    """非法走法。"""


def in_bounds(r: int, c: int) -> bool:
    return 0 <= r < SIZE and 0 <= c < SIZE


def parse_coord(text: str) -> tuple[int, int]:
    """解析 a1..j10 为 (行, 列)，非法抛 IllegalMove。"""
    t = text.strip().lower()
    if len(t) < 2 or not ("a" <= t[0] <= "j"):
        raise IllegalMove(f"坐标格式错误（应为 a1..j10）：{text!r}")
    try:
        row = int(t[1:]) - 1
    except ValueError:
        raise IllegalMove(f"行必须是 1-10：{text!r}")
    col = ord(t[0]) - ord("a")
    if not in_bounds(row, col):
        raise IllegalMove(f"坐标越界：{text!r}")
    return row, col


def fmt_coord(r: int, c: int) -> str:
    return f"{chr(ord('a') + c)}{r + 1}"


class Board:
    """一方海域：舰船布局 + 对方炮弹落点。"""

    def __init__(self, rng: random.Random) -> None:
        self.ships: list[list[tuple[int, int]]] = []
        self.shots: set[tuple[int, int]] = set()  # 对方打过来的炮弹
        occupied: set[tuple[int, int]] = set()
        for length in SHIP_LENGTHS:
            for _ in range(2000):
                horiz = rng.random() < 0.5
                r, c = rng.randrange(SIZE), rng.randrange(SIZE)
                cells = [(r, c + i) if horiz else (r + i, c) for i in range(length)]
                if all(in_bounds(rr, cc) for rr, cc in cells) and not (
                    set(cells) & occupied
                ):
                    self.ships.append(cells)
                    occupied |= set(cells)
                    break
            else:
                raise RuntimeError("舰船布放失败")

    def ship_cells(self) -> set[tuple[int, int]]:
        return {cell for ship in self.ships for cell in ship}

    def sunk_ships(self) -> list[list[tuple[int, int]]]:
        return [s for s in self.ships if all(cell in self.shots for cell in s)]

    def alive_ships(self) -> list[list[tuple[int, int]]]:
        return [s for s in self.ships if not all(cell in self.shots for cell in s)]

    def salvo_size(self) -> int:
        """本轮可开火数 = 存活舰船数。"""
        return len(self.alive_ships())

    def all_sunk(self) -> bool:
        return len(self.alive_ships()) == 0

    def apply_shots(
        self, shots: list[tuple[int, int]]
    ) -> tuple[list[str], list[list[tuple[int, int]]]]:
        """结算一轮炮弹。返回 (每发结果 'hit'/'miss', 本轮新击沉的舰船)。"""
        before = len(self.sunk_ships())
        for s in shots:
            if not in_bounds(*s):
                raise IllegalMove(f"炮弹越界：{fmt_coord(*s)}")
            self.shots.add(s)
        ship_cells = self.ship_cells()
        results = ["hit" if s in ship_cells else "miss" for s in shots]
        new_sunk = self.sunk_ships()[before:]
        return results, new_sunk


class SalvoAI:
    """hunt-target AI：命中后追踪相邻格，未命中时按奇偶格搜索。"""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.tried: set[tuple[int, int]] = set()
        self.open_hits: set[tuple[int, int]] = set()  # 命中但所属舰船未沉

    def feedback(
        self,
        shots: list[tuple[int, int]],
        results: list[str],
        sunk_ships: list[list[tuple[int, int]]],
    ) -> None:
        sunk_cells = {cell for ship in sunk_ships for cell in ship}
        self.tried |= set(shots)
        for s, res in zip(shots, results):
            if res == "hit" and s not in sunk_cells:
                self.open_hits.add(s)
        self.open_hits -= sunk_cells

    def _targets(self) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for r, c in sorted(self.open_hits):
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cell = (r + dr, c + dc)
                if in_bounds(*cell) and cell not in self.tried and cell not in out:
                    out.append(cell)
        return out

    def choose_shots(self, n: int) -> list[tuple[int, int]]:
        if n <= 0:
            return []
        shots: list[tuple[int, int]] = []
        for cell in self._targets():
            if len(shots) >= n:
                break
            shots.append(cell)
        if len(shots) < n:
            untried = [
                (r, c)
                for r in range(SIZE)
                for c in range(SIZE)
                if (r, c) not in self.tried
            ]
            parity = [cell for cell in untried if (cell[0] + cell[1]) % 2 == 0]
            pool = parity or untried
            self.rng.shuffle(pool)
            for cell in pool:
                if len(shots) >= n:
                    break
                if cell not in shots:
                    shots.append(cell)
        # 棋盘打满的极端情况：允许复打已试格（实战中不会发生）
        while len(shots) < n:
            shots.append((self.rng.randrange(SIZE), self.rng.randrange(SIZE)))
        return shots[:n]


def validate_salvo(shots: list[tuple[int, int]], n: int) -> None:
    if len(shots) != n:
        raise IllegalMove(f"本轮应开火 {n} 发，实际 {len(shots)} 发")
    if len(set(shots)) != len(shots):
        raise IllegalMove("同一轮不能对同一格开火两次")
    for s in shots:
        if not in_bounds(*s):
            raise IllegalMove(f"炮弹越界：{fmt_coord(*s)}")


def play_game(
    rng: random.Random, verbose: bool = False
) -> tuple[int, int]:
    """AI 对 AI 一局。返回 (胜者 0/1/2=和棋, 轮数)。"""
    boards = [Board(rng), Board(rng)]
    ais = [SalvoAI(rng), SalvoAI(rng)]
    rounds = 0
    while True:
        rounds += 1
        sizes = [b.salvo_size() for b in boards]
        salvos = [ais[i].choose_shots(sizes[i]) for i in range(2)]
        for i in range(2):
            validate_salvo(salvos[i], sizes[i])
        # 同时结算
        outcomes = [boards[1].apply_shots(salvos[0]), boards[0].apply_shots(salvos[1])]
        for i in range(2):
            results, sunk = outcomes[i]
            ais[i].feedback(salvos[i], results, sunk)
        if verbose:
            print(
                f"第{rounds}轮: 甲开火{sizes[0]}发({sum(r=='hit' for r in outcomes[0][0])}中) "
                f"乙开火{sizes[1]}发({sum(r=='hit' for r in outcomes[1][0])}中)"
            )
        dead = [b.all_sunk() for b in boards]
        if dead[0] and dead[1]:
            return 2, rounds
        if dead[1]:
            return 0, rounds
        if dead[0]:
            return 1, rounds
        if rounds > 500:  # 安全上限
            return 2, rounds


def render(board: Board, tracking: set[tuple[int, int]], hits: set[tuple[int, int]]) -> str:
    """己方棋盘 + 对敌方海域的追踪棋盘。"""
    ship_cells = board.ship_cells()
    lines = ["   " + " ".join(chr(ord("a") + c) for c in range(SIZE))]
    for r in range(SIZE):
        left = []
        right = []
        for c in range(SIZE):
            cell = (r, c)
            if cell in board.shots and cell in ship_cells:
                left.append("X")
            elif cell in ship_cells:
                left.append("S")
            elif cell in board.shots:
                left.append("o")
            else:
                left.append(".")
            if cell in hits:
                right.append("X")
            elif cell in tracking:
                right.append("o")
            else:
                right.append("?")
        lines.append(f"{r+1:2d} " + " ".join(left) + "   |   " + " ".join(right))
    return "\n".join(lines) + "\n   己方海域(S=舰船 X=被命中 o=落空) | 追踪(X=命中 o=落空)"


def play_interactive(seed: int | None) -> int:
    rng = random.Random(seed)
    board = Board(rng)
    enemy = Board(rng)
    ai = SalvoAI(rng)
    tried: set[tuple[int, int]] = set()
    hits: set[tuple[int, int]] = set()
    print("Salvo 海战齐射：你是指挥官甲，AI 是乙。")
    print("每轮按双方存活舰船数同时开火，先击沉对方全部 5 艘舰船者胜。")
    print("输入坐标如 a1 b3（空格分隔），q 退出。\n")
    round_no = 0
    while True:
        round_no += 1
        n_you = board.salvo_size()
        n_ai = enemy.salvo_size()
        print(render(board, tried, hits))
        print(f"第{round_no}轮：你开火 {n_you} 发，敌方开火 {n_ai} 发。")
        try:
            raw = input(f"请输入 {n_you} 个坐标：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n对局结束。")
            return 0
        if raw.lower() == "q":
            print("对局结束。")
            return 0
        tokens = raw.split()
        try:
            shots = [parse_coord(t) for t in tokens]
            validate_salvo(shots, n_you)
        except IllegalMove as e:
            print(f"非法输入：{e}，请重输。")
            round_no -= 1
            continue
        ai_shots = ai.choose_shots(n_ai)
        your_results, your_sunk = enemy.apply_shots(shots)
        ai_results, ai_sunk = board.apply_shots(ai_shots)
        ai.feedback(ai_shots, ai_results, ai_sunk)
        tried |= set(shots)
        hits |= {s for s, r in zip(shots, your_results) if r == "hit"}
        print(
            f"你 {sum(r=='hit' for r in your_results)} 中"
            + (f"，击沉敌方{len(your_sunk)}艘！" if your_sunk else "")
            + f"；敌方 {sum(r=='hit' for r in ai_results)} 中"
            + (f"，你被击沉{len(ai_sunk)}艘！" if ai_sunk else "")
        )
        dead_you, dead_ai = board.all_sunk(), enemy.all_sunk()
        if dead_you and dead_ai:
            print("同轮互沉——和棋！")
            return 0
        if dead_ai:
            print("敌方舰队全灭——你赢了！")
            return 0
        if dead_you:
            print("你的舰队全灭——AI 赢了。")
            return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Salvo 海战齐射")
    ap.add_argument("--auto", action="store_true", help="AI 自动对局演示")
    ap.add_argument("--games", type=int, default=10, help="自动对局局数")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="逐轮输出")
    args = ap.parse_args(argv)
    if args.auto:
        rng = random.Random(args.seed)
        wins = [0, 0, 0]
        total_rounds = 0
        for g in range(args.games):
            w, rounds = play_game(rng, verbose=args.verbose)
            wins[w] += 1
            total_rounds += rounds
            if args.verbose:
                print(f"第{g+1}局：{'甲胜' if w==0 else '乙胜' if w==1 else '和棋'}（{rounds}轮）")
        print(f"共 {args.games} 局：甲胜 {wins[0]}，乙胜 {wins[1]}，和棋 {wins[2]}")
        print(f"平均 {total_rounds / args.games:.1f} 轮/局")
        return 0
    if not sys.stdin.isatty():
        print("交互模式需要终端；请用 --auto 做自动演示。", file=sys.stderr)
        return 2
    return play_interactive(args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
