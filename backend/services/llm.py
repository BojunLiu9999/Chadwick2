"""
PCM downsampling helper shared by the voice path.

G1 AudioClient.PlayStream wants 16 kHz mono 16-bit signed LE PCM, but
OpenAI tts-1 with response_format="pcm" emits 24 kHz mono. Linear
interpolation is good enough for speech at this rate ratio.
"""
import struct


def _downsample_24k_to_16k(pcm_24k: bytes) -> bytes:
    samples = struct.unpack(f"<{len(pcm_24k) // 2}h", pcm_24k)
    n_in = len(samples)
    n_out = (n_in * 2) // 3
    out = [0] * n_out
    for i in range(n_out):
        src = i * 1.5
        idx = int(src)
        frac = src - idx
        a = samples[idx]
        b = samples[idx + 1] if idx + 1 < n_in else a
        v = int(a + (b - a) * frac)
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        out[i] = v
    return struct.pack(f"<{n_out}h", *out)
