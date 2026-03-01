"""Live demo of M2 Telephony components.

Demonstrates:
1. Audio Codec: µ-law ↔ PCM conversion and resampling
2. VAD: Utterance detection from simulated speech + silence
3. Silence Detector: Threshold-based events
4. Caller: WebSocket token generation and TwiML building
"""

import asyncio
import math
import struct
import time
import sys

# Add project root
sys.path.insert(0, ".")

from src.telephony.audio_codec import AudioCodec
from src.telephony.vad import VADProcessor, VADConfig
from src.telephony.silence import SilenceDetector, SilenceConfig, SilenceEvent
from src.telephony.caller import generate_ws_token, validate_ws_token, build_twiml


def generate_sine_pcm(freq_hz: int, duration_ms: int, sample_rate: int = 8000, amplitude: int = 8000) -> bytes:
    """Generate a sine wave as PCM audio."""
    n = sample_rate * duration_ms // 1000
    samples = [int(amplitude * math.sin(2 * math.pi * freq_hz * i / sample_rate)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


def demo_audio_codec():
    print("\n" + "=" * 60)
    print("🔊 DEMO 1: Audio Codec (µ-law ↔ PCM, 8kHz ↔ 16kHz)")
    print("=" * 60)

    # Generate 100ms of 440Hz sine wave at 8kHz (simulating phone audio)
    pcm_8k = generate_sine_pcm(440, 100, sample_rate=8000)
    print(f"\n  📥 Original PCM (8kHz):     {len(pcm_8k):>6} bytes ({len(pcm_8k)//2} samples)")

    # Encode to µ-law (what Twilio sends)
    ulaw = AudioCodec.pcm_to_ulaw(pcm_8k)
    print(f"  📦 Encoded µ-law:           {len(ulaw):>6} bytes (50% compression)")

    # Full inbound pipeline: µ-law 8kHz → PCM 16kHz (for Whisper STT)
    pcm_16k = AudioCodec.twilio_to_stt(ulaw)
    print(f"  📤 STT-ready PCM (16kHz):   {len(pcm_16k):>6} bytes ({len(pcm_16k)//2} samples)")

    # Full outbound pipeline: PCM 16kHz → µ-law 8kHz (back to Twilio)
    ulaw_out = AudioCodec.stt_to_twilio(pcm_16k)
    print(f"  📦 Back to µ-law:           {len(ulaw_out):>6} bytes")

    print(f"\n  ✅ Round-trip ratio: {len(ulaw_out)/len(ulaw)*100:.0f}% of original size")


def demo_vad():
    print("\n" + "=" * 60)
    print("🎙️  DEMO 2: Voice Activity Detection (utterance segmentation)")
    print("=" * 60)

    vad = VADProcessor(VADConfig(
        energy_threshold=200,
        min_speech_ms=100,
        silence_ms=100,
        sample_rate=8000,
        chunk_ms=20,
    ))

    # Simulate: 500ms speech → 200ms silence → 300ms speech → 200ms silence
    speech_chunk = generate_sine_pcm(440, 20, sample_rate=8000, amplitude=8000)
    silence_chunk = b"\x00\x00" * 160  # 20ms at 8kHz

    utterances = []
    timeline = []

    print("\n  Simulating audio stream:")
    print("  " + "-" * 50)

    # Phase 1: 500ms speech (25 chunks × 20ms)
    for i in range(25):
        result = vad.process(speech_chunk)
        timeline.append("█")
        if result:
            utterances.append(result)

    # Phase 2: 200ms silence (10 chunks × 20ms)
    for i in range(10):
        result = vad.process(silence_chunk)
        timeline.append("░")
        if result:
            utterances.append(result)
            print(f"  → Utterance 1 detected! ({len(result)} bytes)")

    # Phase 3: 300ms speech
    for i in range(15):
        result = vad.process(speech_chunk)
        timeline.append("█")
        if result:
            utterances.append(result)

    # Phase 4: 200ms silence
    for i in range(10):
        result = vad.process(silence_chunk)
        timeline.append("░")
        if result:
            utterances.append(result)
            print(f"  → Utterance 2 detected! ({len(result)} bytes)")

    print(f"\n  Timeline: {''.join(timeline)}")
    print(f"            {'speech':^25}{'gap':^10}{'speech':^15}{'gap':^10}")
    print(f"\n  ✅ Detected {len(utterances)} utterances from continuous stream")


def demo_silence_detector():
    print("\n" + "=" * 60)
    print("🔇 DEMO 3: Silence Detector (hold detection)")
    print("=" * 60)

    sd = SilenceDetector(SilenceConfig(
        prompt_threshold_seconds=0.3,   # Accelerated for demo
        timeout_threshold_seconds=0.8,
    ))

    print("\n  Simulating silence during a call (accelerated):")
    print("  " + "-" * 50)

    events_seen = []
    start = time.monotonic()

    for i in range(20):
        time.sleep(0.1)
        event = sd.on_silence()
        elapsed = time.monotonic() - start
        if event == SilenceEvent.PROMPT_CHECK:
            print(f"  ⏱️  {elapsed:.1f}s — PROMPT: \"Are you still there?\"")
            events_seen.append("prompt")
        elif event == SilenceEvent.TIMEOUT:
            print(f"  ⏱️  {elapsed:.1f}s — TIMEOUT: Hanging up")
            events_seen.append("timeout")
            break

    # Now simulate speech (reset)
    sd.on_speech()
    print(f"  🗣️  Speech detected — timer reset!")
    event = sd.on_silence()
    print(f"  ⏱️  After reset — event: {event.value}")

    print(f"\n  ✅ Events fired: {', '.join(events_seen)}")


async def demo_ws_auth():
    print("\n" + "=" * 60)
    print("🔑 DEMO 4: WebSocket Auth Token (single-use)")
    print("=" * 60)

    # In-memory session store for demo
    store = {}
    class DemoSession:
        async def get(self, key): return store.get(key)
        async def set(self, key, value, ttl=None): store[key] = value
        async def delete(self, key): store.pop(key, None)

    session = DemoSession()

    # Generate token
    token = await generate_ws_token(session, "reservation-demo-001")
    print(f"\n  🎫 Generated token: {token[:20]}...")
    print(f"  📦 Stored in session: {len(store)} entry")

    # Validate (first use)
    result = await validate_ws_token(session, token)
    print(f"\n  ✅ First validation: reservation_id = {result}")
    print(f"  📦 Session after use: {len(store)} entries (consumed)")

    # Try to reuse (should fail)
    result2 = await validate_ws_token(session, token)
    print(f"  ❌ Second validation: {result2} (single-use enforced)")

    # Invalid token
    result3 = await validate_ws_token(session, "fake-token-xyz")
    print(f"  ❌ Invalid token: {result3}")


def demo_twiml():
    print("\n" + "=" * 60)
    print("📞 DEMO 5: TwiML Generation")
    print("=" * 60)

    twiml = build_twiml("res-demo-001", "demo-token-abc")
    print(f"\n  Generated TwiML ({len(twiml)} chars):")
    print()
    # Pretty print with indentation
    import xml.dom.minidom
    pretty = xml.dom.minidom.parseString(twiml).toprettyxml(indent="    ")
    for line in pretty.split("\n")[1:]:  # Skip XML declaration
        if line.strip():
            print(f"  {line}")


async def main():
    print("\n" + "🚀" * 30)
    print("  RESERVATION AGENT — M2 TELEPHONY LIVE DEMO")
    print("🚀" * 30)

    demo_audio_codec()
    demo_vad()
    demo_silence_detector()
    await demo_ws_auth()
    demo_twiml()

    print("\n" + "=" * 60)
    print("🎉 ALL M2 COMPONENTS DEMONSTRATED SUCCESSFULLY")
    print("=" * 60)
    print()


if __name__ == "__main__":
    asyncio.run(main())
