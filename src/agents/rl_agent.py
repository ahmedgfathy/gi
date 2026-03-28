"""
RL Agent -- uses Stable-Baselines3 PPO to learn from an environment.
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np

from .base_agent import BaseAgent, Observation, Action


class RLAgent(BaseAgent):
    """
    Reinforcement Learning agent using Proximal Policy Optimization (PPO).
    Wraps stable-baselines3 so it fits the BaseAgent cognitive loop.

    Args:
        env_id: Any Gymnasium environment ID (e.g. "CartPole-v1").
        total_timesteps: Training budget.
    """

    def __init__(self, name: str = "RLAgent",
                 env_id: str = "CartPole-v1",
                 total_timesteps: int = 50_000) -> None:
        super().__init__(name=name)
        self.env_id          = env_id
        self.total_timesteps = total_timesteps
        self._model          = None
        self._last_obs       = None

    def train(self) -> None:
        from stable_baselines3 import PPO
        env = gym.make(self.env_id)
        self._model = PPO("MlpPolicy", env, verbose=1)
        self._model.learn(total_timesteps=self.total_timesteps)
        env.close()

    def save(self, path: str = "rl_agent.zip") -> None:
        if self._model:
            self._model.save(path)

    def load(self, path: str = "rl_agent.zip") -> None:
        from stable_baselines3 import PPO
        self._model = PPO.load(path)

    def perceive(self, observation: Observation) -> None:
        assert observation.modality == "state", "RLAgent expects modality=state."
        self._last_obs = np.array(observation.data, dtype=np.float32)
        self.working_memory.push(self._last_obs)

    def think(self) -> None:
        self.cot.add(f"State vector: {self._last_obs}")
        self.cot.add("Running PPO policy network forward pass.")

    def act(self) -> Action:
        if self._model is None:
            raise RuntimeError("Model not trained. Call train() first.")
        raw_action, _ = self._model.predict(self._last_obs, deterministic=True)
        return Action(name="env_step", args={"action": int(raw_action)})
