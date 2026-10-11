class InterruptPhrases:
    PHRASES: tuple[str, ...] = (
        "stop",
        "shut up",
        "hold on",
        "wait",
        "pause",
        "cancel",
        "never mind",
    )

    @classmethod
    def is_an_interrupt(cls, text: str) -> bool:
        normalised = text.strip().lower().rstrip(".!?,")
        for phrase in cls.PHRASES:
            if phrase in normalised:
                return True
        return False
