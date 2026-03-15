"""Base class for all TensorPicks agents."""

import logging
from abc import ABC, abstractmethod


class Agent(ABC):
    """Base agent that all agents inherit from.

    Subclasses must implement:
        name: human-readable agent name
        run(): the main agent logic, called on schedule or manually
    """

    name: str = "unnamed"

    def __init__(self):
        self.log = logging.getLogger(f"agent.{self.name}")

    @abstractmethod
    def run(self) -> None:
        """Execute the agent's main task."""

    def __repr__(self) -> str:
        return f"<Agent:{self.name}>"
