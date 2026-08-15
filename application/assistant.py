from domain.senses.ear import Ear


class Assistant:
    """Application servie: orchestrate JARVIS senses and the brain"""

    def __init__(self, ear: Ear) -> None:
        self._ear = ear 

    def run(self) -> None:
        print("Listening for 'hey jarvis'...")
        while True: 
            self._ear.listen_for_wake_command()
            print("Wake Detected")
