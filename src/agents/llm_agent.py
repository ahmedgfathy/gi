"""
LLM Agent -- uses a HuggingFace language model as its reasoning engine.
"""

from __future__ import annotations

from transformers import pipeline

from .base_agent import BaseAgent, Observation, Action
from ..core.reasoning import Goal


class LLMAgent(BaseAgent):
    """
    A text-based agent that uses a small LLM (e.g. TinyLlama)
    to generate reasoning steps and actions.

    Args:
        model_name: Any HuggingFace text-generation model.
        max_new_tokens: Token limit for each generation step.
    """

    def __init__(self, name: str = "LLMAgent",
                 model_name: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                 max_new_tokens: int = 256) -> None:
        super().__init__(name=name)
        self.model_name     = model_name
        self.max_new_tokens = max_new_tokens
        self._pipe          = None
        self._last_obs: str = ""

    def _load_model(self) -> None:
        self._pipe = pipeline(
            "text-generation",
            model=self.model_name,
            max_new_tokens=self.max_new_tokens,
            do_sample=True,
            temperature=0.7,
        )

    def perceive(self, observation: Observation) -> None:
        assert observation.modality == "text", "LLMAgent only handles text observations."
        self._last_obs = str(observation.data)
        self.working_memory.push(self._last_obs)

    def think(self) -> None:
        goal_desc = self.goals.peek().description if self.goals.peek() else "No active goal."
        self.cot.add(f"Observation: {self._last_obs}")
        self.cot.add(f"Current goal: {goal_desc}")
        self.cot.add(f"Context window ({len(self.working_memory)} items loaded)")

    def act(self) -> Action:
        if self._pipe is None:
            self._load_model()

        prompt = (
            "You are an AGI agent. Given the context below, decide the SINGLE best action.\n"
            f"Context:\n{self.cot.summarize()}\n\n"
            "Respond with: ACTION: <action_name> ARGS: <key=value ...>"
        )
        result = self._pipe(prompt)[0]["generated_text"]

        action_name = "observe"
        args: dict = {}
        if "ACTION:" in result:
            parts = result.split("ACTION:")[-1].strip().split("ARGS:")
            action_name = parts[0].strip().split()[0] if parts[0].strip() else "observe"
            if len(parts) > 1:
                for pair in parts[1].strip().split():
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        args[k] = v
        return Action(name=action_name, args=args)
