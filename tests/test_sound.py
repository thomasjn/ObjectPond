import unittest
from objectpond.boot import create_default_environment
from objectpond.kernel.image import ImageSerializer
from objectpond.morphic import DisplayCanvas, RecordingBackend, SampledSound, SoundSynth, ADSR, note_to_hz
from objectpond.tools.demos import SoundStudioWindow


class TestSoundAndBinaryAssets(unittest.TestCase):
    def test_synthesis_effects_and_wav_export(self):
        self.assertAlmostEqual(note_to_hz("A4"), 440.0, places=2)
        self.assertAlmostEqual(note_to_hz(69), 440.0, places=2)

        env = ADSR(0.01, 0.05, 0.6, 0.05)
        s1 = SoundSynth.oscillator("sine", "A4", 0.25, env=env)
        s2 = SoundSynth.fm(440.0, 220.0, 3.0, 0.25, env=env)
        s3 = SoundSynth.additive(((1.0, 1.0), (2.0, 0.5)), "C5", 0.2, env=env)
        seq = SoundSynth.sequence([(0.0, s1), (0.15, s2), (0.3, s3)])
        fx = seq.lowpass(1800.0).echo(0.1, 0.35).gain(0.8)

        self.assertGreater(fx.duration(), 0.4)
        wav = fx.to_wav_bytes()
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav[:16])

    def test_sampled_sound_image_roundtrip_and_host_playback(self):
        smalltalk, world = create_default_environment(1000, 700)
        snd = SoundSynth.fm("E4", "B3", 2.5, 0.2)
        world.workspace_globals["chime"] = snd

        played = []
        world.set_host_action_callback(lambda act, pay=None: played.append((act, pay)))
        self.assertTrue(snd.play(world))
        self.assertEqual(played[0][0], "play_sound")
        self.assertEqual(played[0][1]["sample_rate"], 44100)
        self.assertTrue(played[0][1]["pcm_b64"])

        # Round-trip through compressed .image snapshot
        serializer = ImageSerializer(smalltalk)
        raw_img = serializer.save_image_bytes(world)
        new_world = serializer.load_image_bytes(raw_img)
        restored = new_world.workspace_globals.get("chime")
        self.assertIsInstance(restored, SampledSound)
        self.assertEqual(restored.sample_rate, snd.sample_rate)
        self.assertEqual(restored.samples, snd.samples)
        self.assertIn("SoundStudioWindow", smalltalk.classes)

    def test_sound_studio_window(self):
        _st, world = create_default_environment(1000, 700)
        studio = world.open_sound_studio()
        self.assertIsInstance(studio, SoundStudioWindow)
        studio.wave_dd.select_index(4, notify=True)  # fm_bell
        studio.freq_slider.set_value(523, notify=True)
        studio.save_to_global()
        self.assertIsInstance(world.workspace_globals.get("my_sound"), SampledSound)

        canvas = DisplayCanvas(RecordingBackend(1000, 700))
        world.full_draw_on(canvas)


if __name__ == "__main__":
    unittest.main()
