import os
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

"""
main.py -- Minimal end-to-end demo showing all GI subsystems working together.
Runs without any GPU or internet connection.
"""

from rich.console import Console
from rich.panel   import Panel
from loguru       import logger
import numpy as np

from src.core.memory    import WorkingMemory, VectorMemory
from src.core.reasoning import ChainOfThought, GoalStack, Goal, RuleEngine
from src.agents.base_agent import Observation, Action

console = Console()


def demo_memory() -> None:
    console.rule("[bold cyan]1. Memory")

    wm = WorkingMemory(capacity=4)
    for i in range(6):
        wm.push(f"event_{i}")
    console.print(f"Working memory (cap=4): {wm.retrieve_all()}")

    vm = VectorMemory(dim=16)
    for i in range(5):
        vec = np.random.randn(16).astype(np.float32)
        vm.store(vec, metadata=f"fact_{i}")
    query = np.random.randn(16).astype(np.float32)
    results = vm.search(query, top_k=3)
    console.print(f"Vector memory size: {len(vm)}")
    console.print(f"Top-3 search results: {[r[1] for r in results]}")


def demo_reasoning() -> None:
    console.rule("[bold cyan]2. Reasoning")

    cot = ChainOfThought()
    cot.add("Perceived: the room is dark.", confidence=0.95)
    cot.add("Retrieved memory: light switch is near the door.", confidence=0.80)
    cot.add("Plan: move to door and flip switch.", confidence=0.90)
    console.print(cot.summarize())

    goals = GoalStack()
    goals.push(Goal("Explore environment", priority=1))
    goals.push(Goal("Find energy source",  priority=3))
    goals.push(Goal("Build world model",   priority=2))
    console.print(f"\nGoal stack top: {goals.peek()}")

    engine = RuleEngine()
    engine.add_rule(
        "low_battery",
        condition=lambda s: s.get("battery", 100) < 20,
        action=lambda s: "Go charge immediately!",
    )
    engine.add_rule(
        "goal_achieved",
        condition=lambda s: s.get("goal_done", False),
        action=lambda s: "Report success and pick next goal.",
    )
    fired = engine.run({"battery": 15, "goal_done": True})
    console.print(f"Rule engine fired: {fired}")


def demo_observation() -> None:
    console.rule("[bold cyan]3. Agent Observation / Action")

    obs = Observation(modality="text", data="The sky is blue and the sun is shining.")
    console.print(f"Observation: modality={obs.modality!r}, data={obs.data!r}")

    action = Action(name="speak", args={"message": "I see clear sky.", "volume": "normal"})
    console.print(f"Action: {action}")


if __name__ == "__main__":
    console.print(Panel.fit(
        "[bold green]GI -- General Intelligence Framework[/bold green]\n"
        "Demo: memory + reasoning + agents",
        border_style="green"
    ))

    demo_memory()
    demo_reasoning()
    demo_observation()

    console.print(Panel.fit(
        "[bold green]All subsystems OK.[/bold green]\n"
        "Next steps:\n"
        "  * Train an RL agent:  from src.agents import RLAgent\n"
        "  * Run an LLM agent:   from src.agents import LLMAgent\n"
        "  * Check packages:     python verify.py",
        border_style="blue"
    ))
