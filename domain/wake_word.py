from dataclasses import dataclass


@dataclass(frozen=True)
class WakeWordScore:
    """A model's confident that will chunk audio input containing wake up word command."""
    model_name: str
    confidence: float

    def exceeds(self, threshold: float) -> bool:
        return self.confidence >= threshold
