from enum import Enum


class Phase(str, Enum):
    AWAKENING = "awakening"
    LEARNING = "learning"
    UNDERSTANDING = "understanding"
    MASTERING = "mastering"
    POLISHING = "polishing"


class Grade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    B_PLUS = "B+"
    B = "B"
    B_MINUS = "B-"
    C_PLUS = "C+"
    C = "C"
    C_MINUS = "C-"
    D = "D"
    F = "F"
    INCOMPLETE = "I"


class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    DETECTION = "detection"
    REGRESSION = "regression"
    BIOMETRIC = "biometric"
    GAZE = "gaze"
    NLP = "nlp"
    GENERATIVE = "generative"
    CUSTOM = "custom"


PHASE_EMOJI: dict[Phase, str] = {
    Phase.AWAKENING: "🌱",
    Phase.LEARNING: "📚",
    Phase.UNDERSTANDING: "💡",
    Phase.MASTERING: "⚡",
    Phase.POLISHING: "✨",
}
