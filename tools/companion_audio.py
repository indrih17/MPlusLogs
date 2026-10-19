"""Play the original Companion readiness chime without a system-sound fallback."""
from pathlib import Path

READY_SOUND=Path(__file__).with_name('assets')/'companion-ready.wav'


def play_ready():
    if not READY_SOUND.is_file():return False
    try:
        import winsound
        winsound.PlaySound(str(READY_SOUND),winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        return True
    except (ImportError,OSError,RuntimeError):
        # Readiness and clipboard delivery remain usable without an audio device.
        return False
