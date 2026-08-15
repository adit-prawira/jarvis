from application.assistant import Assistant
from infrastructure.sense.openwakeword_ear import OpenWakeWordDetector, OpenWakeWordEar


def main() -> None:
    ear = OpenWakeWordEar(detector=OpenWakeWordDetector())
    Assistant(ear=ear).run()

if __name__ == "__main__":
    main()
