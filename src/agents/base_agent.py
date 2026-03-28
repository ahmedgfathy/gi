"""
Base agent interface.
Every AGI agent inherits from BaseAgent and implements perceive / think / act.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from ..core.memory import WorkingMemory, VectorMemory
from ..core.reasoning import ChainOfThought, GoalStack


@dataclass
class Observation:
    """Raw sensory input received by an agent."""
    modality: str          # "text" | "image" | "audio" | "state"
    data: Any
    timestamp: float = 0.0


@dataclass
class Action:
    """An action the agent intends to take in the environment."""
    name: str
    args: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"Action({self.name}, args={self.args})"


class BaseAgent(ABC):
    """
    Abstract base class for all GI agents.

    Subclass this and implement:
        perceive(obs)  -- update internal state from raw observation
        think()        -- run reasoning to decide what to do next
        act()          -- return the chosen Action

    The run_cycle() method ties these together into one cognitive loop.
    """

    def __init__(self, name: str = "Agent",
                 memory_capacity: int = 256,
                 vector_dim: int = 384) -> None:
        self.name = name
        self.working_memory   = WorkingMemory(capacity=memory_capacity)
        self.long_term_memory = VectorMemory(dim=vector_dim)
        self.cot              = ChainOfThought()
        self.goals            = GoalStack()
        self._step            = 0

    @abstractmethod
    def perceive(self, observation: Observation) -> None:
        """Process an observation and update internal state."""

    @abstractmethod
    def think(self) -> None:
        """Reason over current memory and goals to form a plan."""

    @abstractmethod
    def act(self) -> Action:
        """Return the next action based on the current plan."""

    def run_cycle(self, observation: Observation) -> Action:
        """One full perceive -> think -> act cycle."""
        self._step += 1
        logger.info(f"{self.name} | step {self._step} | PERCEIVE")
        self.perceive(observation)

        logger.info(f"{self.name} | step {self._step} | THINK")
        self.cot.clear()
        self.think()

        logger.info(f"{self.name} | step {self._step} | ACT")
        action = self.act()
        logger.info(f"{self.name} | step {self._step} | -> {action}")
        return action

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}(name={self.name!r}, "
                f"step={self._step}, goals={len(self.goals)})")
