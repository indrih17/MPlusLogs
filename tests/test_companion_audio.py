"""Original readiness audio, nonblocking playback and lossless packaging."""
import base64
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
import wave

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import companion_audio
import companion_version
import export_release_source


class CompanionAudioTests(unittest.TestCase):
    def test_chime_is_short_valid_pcm_with_headroom(self):
        with wave.open(str(companion_audio.READY_SOUND),'rb') as sound:
            self.assertEqual((sound.getnchannels(),sound.getsampwidth()),(1,2))
            self.assertTrue(.3<=sound.getnframes()/sound.getframerate()<=.8)
            samples=struct.unpack('<'+'h'*sound.getnframes(),sound.readframes(sound.getnframes()))
        self.assertTrue(1000<max(abs(value) for value in samples)<30000)
        self.assertLess(abs(samples[0]),10)
        self.assertLess(abs(samples[-1]),10)

    def test_playback_is_async_and_never_uses_default_system_sound(self):
        import winsound
        with patch.object(winsound,'PlaySound') as play:
            self.assertTrue(companion_audio.play_ready())
        play.assert_called_once_with(str(companion_audio.READY_SOUND),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)

    def test_missing_sound_does_not_fall_back_to_a_windows_beep(self):
        import winsound
        with patch.object(companion_audio,'READY_SOUND',ROOT/'missing-audio.wav'),patch.object(winsound,'PlaySound') as play:
            self.assertFalse(companion_audio.play_ready())
        play.assert_not_called()

    def test_audio_device_error_does_not_interrupt_ready_delivery(self):
        import winsound
        with patch.object(winsound,'PlaySound',side_effect=RuntimeError('no audio device')):
            self.assertFalse(companion_audio.play_ready())

    def test_public_source_export_preserves_wav_bytes(self):
        entry=next(e for e in export_release_source.entries() if e['path']=='tools/assets/companion-ready.wav')
        self.assertEqual(entry['encoding'],'base64')
        self.assertEqual(base64.b64decode(entry['content']),companion_audio.READY_SOUND.read_bytes())
        self.assertIn('companion_audio.py',companion_version.RUNTIME)


if __name__=='__main__':unittest.main()
