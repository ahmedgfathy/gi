"""
Core reasoning module.
Implements chain-of-thought, symbolic reasoning, and planning primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


# Chain-of-Thought

@dataclass
class Thought:
    step: int
    content: str
    confidence: float = 1.0

    def __str__(self) -> str:
        return f"[Step {self.step}] (conf={self.confidence:.2f}) {self.content}"


class ChainOfThought:
    """Builds an explicit reasoning chain before producing a final answer."""

    def __init__(self) -> None:
        self.chain: list[Thought] = []

    def add(self, content: str, confidence: float = 1.0) -> "ChainOfThought":
        self.chain.append(Thought(len(self.chain) + 1, content, confidence))
        return self

    def summarize(self) -> str:
        return "\n".join(str(t) for t in self.chain)

    def clear(self) -> None:
        self.chain.clear()


# Goal Stack (means-ends planning)

@dataclass
class Goal:
    description: str
    priority: int = 0
    completed: bool = False
    sub_goals: list["Goal"] = field(default_factory=list)

    def add_sub_goal(self, description: str, priority: int = 0) -> "Goal":
        sg = Goal(description, priority)
        self.sub_goals.append(sg)
        return sg

    def mark_done(self) -> None:
        self.completed = True

    def is_fully_resolved(self) -> bool:
        return self.completed and all(sg.is_fully_resolved() for sg in self.sub_goals)


class GoalStack:
    """LIFO goal stack — agents push new goals and pop when resolved."""

    def __init__(self) -> None:
        self._stack: list[Goal] = []

    def push(self, goal: Goal) -> None:
        self._stack.append(goal)
        self._stack.sort(key=lambda g: g.priority, reverse=True)

    def pop(self) -> Goal | None:
        return self._stack.pop() if self._stack else None

    def peek(self) -> Goal | None:
        return self._stack[-1] if self._stack else None

    def __len__(self) -> int:
        return len(self._stack)

    def __repr__(self) -> str:
        return f"GoalStack(size={len(self._stack)})"


# Simple Rule Engine (symbolic)

@dataclass
class Rule:
    name: str
    condition: Callable[[dict], bool]
    action: Callable[[dict], str]


class RuleEngine:
    """
    Forward-chaining rule engine.
    Fires all rules whose conditions are satisfied by the current world state.
    """

    def __init__(self) -> None:
        self.rules: list[Rule] = []

    def add_rule(self, name: str,
                 condition: Callable[[dict], bool],
                 action: Callable[[dict], str]) -> None:
        self.rules.append(Rule(name, condition, action))

    def run(self, state: dict) -> list[str]:
        fired = []
        for rule in self.rules:
            if rule.condition(state):
                fired.append(rule.action(state))
        return fired
