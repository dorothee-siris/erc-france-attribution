from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BudgetGuard:
    warning_tokens: int = 25_000
    hard_tokens: int = 40_000
    input_chars: int = 0
    output_chars: int = 0

    def record(self, input_chars: int, output_chars: int) -> None:
        self.input_chars += max(int(input_chars), 0)
        self.output_chars += max(int(output_chars), 0)

    @property
    def estimated_tokens(self) -> int:
        return (self.input_chars + self.output_chars + 3) // 4

    @property
    def warning_reached(self) -> bool:
        return self.estimated_tokens >= self.warning_tokens

    @property
    def hard_stop(self) -> bool:
        return self.estimated_tokens >= self.hard_tokens

    def can_start_case(self) -> bool:
        return not self.hard_stop
