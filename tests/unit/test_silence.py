"""Unit tests for silence detection."""

import time
from unittest.mock import patch
import pytest

from src.telephony.silence import SilenceDetector, SilenceConfig, SilenceEvent


class TestSilenceDetector:
    def test_initial_silence_returns_none(self):
        sd = SilenceDetector()
        assert sd.on_silence() == SilenceEvent.NONE

    def test_speech_resets_timer(self):
        sd = SilenceDetector(SilenceConfig(prompt_threshold_seconds=0.01))
        sd.on_silence()
        time.sleep(0.02)
        # Would normally prompt, but speech resets
        sd.on_speech()
        assert sd.on_silence() == SilenceEvent.NONE

    def test_prompt_check_at_threshold(self):
        sd = SilenceDetector(SilenceConfig(
            prompt_threshold_seconds=0.05,
            timeout_threshold_seconds=10.0,
        ))
        sd.on_silence()  # Start timer
        time.sleep(0.07)
        event = sd.on_silence()
        assert event == SilenceEvent.PROMPT_CHECK

    def test_prompt_fires_only_once(self):
        sd = SilenceDetector(SilenceConfig(
            prompt_threshold_seconds=0.02,
            timeout_threshold_seconds=10.0,
        ))
        sd.on_silence()  # Start timer
        time.sleep(0.04)
        event1 = sd.on_silence()
        assert event1 == SilenceEvent.PROMPT_CHECK
        # Second call should NOT re-fire prompt
        event2 = sd.on_silence()
        assert event2 == SilenceEvent.NONE

    def test_timeout_at_threshold(self):
        sd = SilenceDetector(SilenceConfig(
            prompt_threshold_seconds=0.01,
            timeout_threshold_seconds=0.05,
        ))
        sd.on_silence()  # Start timer
        time.sleep(0.02)
        sd.on_silence()  # Prompt fires
        time.sleep(0.05)
        event = sd.on_silence()
        assert event == SilenceEvent.TIMEOUT

    def test_speech_after_prompt_resets(self):
        sd = SilenceDetector(SilenceConfig(
            prompt_threshold_seconds=0.02,
            timeout_threshold_seconds=10.0,
        ))
        sd.on_silence()
        time.sleep(0.03)
        sd.on_silence()  # Prompt fires
        sd.on_speech()   # Speech resets
        event = sd.on_silence()
        assert event == SilenceEvent.NONE  # Timer reset

    def test_reset_clears_state(self):
        sd = SilenceDetector(SilenceConfig(prompt_threshold_seconds=0.01))
        sd.on_silence()
        time.sleep(0.02)
        sd.reset()
        assert sd.on_silence() == SilenceEvent.NONE
