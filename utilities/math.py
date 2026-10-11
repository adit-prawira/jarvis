import numpy as np


class MathUtil:
    @staticmethod
    def calculate_rms(chunk: np.ndarray) -> float:
        samples = chunk.astype(np.float64)
        squares = np.square(samples)
        mean_square = float(squares.mean())
        return float(np.sqrt(mean_square))
