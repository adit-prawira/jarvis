import numpy as np
from typing import Protocol

from domain.wake_word import WakeWordScore


class WakeWordDetector(Protocol):
    """Scores a chunk of audio input for wake-work command presence"""
    
    def score(self, audio_chunk: np.ndarray) -> WakeWordScore: ...

class Ear(Protocol):
    """The hearing sense of JARVIS, this will allow the personal assistant to process word"""

    def listen_for_wake_command(self) -> None: ... 


    
