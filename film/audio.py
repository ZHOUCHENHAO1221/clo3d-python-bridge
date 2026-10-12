# -*- coding: utf-8 -*-
"""The film's soundtrack, synthesised. No samples, no track, nothing downloaded.

    python film/render.py verify      # writes out/cues.json from the stage itself
    python film/audio.py              # -> out/audio.wav, two-pass normalised to -14 LUFS

120 BPM in D minor, 36 bars, built to the picture's own structure (out/cues.json carries the
section times, so this file holds none of them):

    the count      pad; a run of blips as the 846 dots arrive; a note for each job's share
    the four calls one instrument joins with each call: kick, hats, bass, clap
    the rule       the kick drops out, a riser climbs, and the last half second is silence
    the drop       one bar per fabric, and the note on each bar is that fabric's measured hem
                   width: the narrowest hem is the lowest note, the widest the highest
    the traps      half-time, while the camera flies through the garments
    the end        one chord, fading

Every hit sits on a cue the picture also reads (out/cues.json), so the two cannot drift.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FF = shutil.which("ffmpeg") or sys.exit("ffmpeg is not on PATH")
SR, BEAT = 48000, 0.5
rng = np.random.default_rng(7)          # seeded: the same film gets the same sound

data = json.loads((OUT / "cues.json").read_text(encoding="utf-8"))
DUR, cues, SEC = data["dur"], data["cues"], data["sections"]
N = int(round(DUR * SR))
T = np.arange(N) / SR
drums, music, fx = (np.zeros((N, 2), np.float32) for _ in range(3))


def ax(dur):
    return np.arange(int(dur * SR)) / SR


def put(bus, sound, t, gain, pan=0.0):
    i0 = int(round(t * SR))
    lo, hi = max(0, i0), min(N, i0 + len(sound))
    if hi > lo:
        s = sound[lo - i0:hi - i0] * gain
        bus[lo:hi, 0] += (s * (1 - max(0, pan))).astype(np.float32)
        bus[lo:hi, 1] += (s * (1 + min(0, pan))).astype(np.float32)


def highpass(x, passes=2):
    for _ in range(passes):
        x = np.diff(x, prepend=x[0])
    return x / (np.abs(x).max() + 1e-9)


def lowpass(x, width):
    return np.convolve(x, np.ones(width) / width, "same")


def kick():
    t = ax(0.32)
    f = 46 + 110 * np.exp(-t / 0.035)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.11) + 0.25 * np.exp(-t / 0.002)


def hat(dur=0.05):
    t = ax(dur)
    return highpass(rng.standard_normal(len(t))) * np.exp(-t / (dur / 4))


def clap():
    t = ax(0.22)
    body = lowpass(highpass(rng.standard_normal(len(t)), 1), 6)
    return body / (np.abs(body).max() + 1e-9) * np.exp(-t / 0.06)


def note(freq, dur, harmonics=5, decay=0.35):
    """A plucked tone: a few harmonics, the higher ones dying first."""
    t = ax(dur)
    s = sum(np.sin(2 * np.pi * freq * h * t) / h * np.exp(-t * h / decay) for h in range(1, harmonics + 1))
    return s * np.minimum(1, t / 0.004)


def bass(freq, dur=0.22):
    t = ax(dur)
    s = sum(np.sin(2 * np.pi * freq * h * t) / h for h in (1, 2, 3))
    return s * np.minimum(1, t / 0.005) * np.exp(-t / (dur / 2.2))


def thump():
    t = ax(0.6)
    f = 38 + 70 * np.exp(-t / 0.06)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.2)


def tick(freq=1400, tau=0.012):
    t = ax(0.07)
    return np.sin(2 * np.pi * freq * t) * np.exp(-t / tau)


def riser(dur):
    t = ax(dur)
    k = t / dur
    noise = highpass(rng.standard_normal(len(t)), 1)
    tone = np.sin(2 * np.pi * np.cumsum(180 * 2 ** (3 * k)) / SR)
    return (0.7 * noise + 0.3 * tone) * k ** 2.2


def whoosh(dur=0.5):
    n = int(dur * SR)
    return lowpass(rng.standard_normal(n), 40) / 0.16 * np.hanning(n)


# D minor: two bars each of i, VI, III, VII
D2, F2, G2, A2, Bb1, C2 = 73.42, 87.31, 98.00, 110.00, 58.27, 65.41
PROG = [(D2, (146.83, 174.61, 220.00)), (Bb1, (116.54, 146.83, 174.61)),
        (F2, (174.61, 220.00, 261.63)), (C2, (130.81, 164.81, 196.00))]


def chord_at(t):
    return PROG[int(t // 4) % 4]


# pad, all the way through
for bar in range(int(DUR // 4) + 1):
    t0 = bar * 4.0
    root, tones = chord_at(t0)
    env = np.clip((T - t0 + 0.4) / 0.9, 0, 1) * np.clip((t0 + 4.5 - T) / 0.9, 0, 1)
    for f in (root * 2,) + tones:
        # no detune between the channels: on a phone's one speaker the two would beat against
        # each other and the bed would swell and sag on its own. The reverb gives it width instead.
        for ch in (0, 1):
            w = 2 * np.pi * f * T
            music[:, ch] += (0.062 * env * (np.sin(w) + 0.35 * np.sin(2 * w) + 0.15 * np.sin(3 * w))).astype(np.float32)

# drums and bass, section by section
kicks = []
for b in range(int(DUR / BEAT)):
    t = b * BEAT
    full, half = SEC["drop"] <= t < SEC["traps"], SEC["traps"] <= t < SEC["end"]
    build = SEC["steps"] <= t < SEC["rule"]
    layer = int((t - SEC["steps"]) // 4) if build else -1      # one more instrument with each call
    root, _ = chord_at(t)
    if full or build or (half and b % 2 == 0):
        grow = (t - SEC["steps"]) / (SEC["rule"] - SEC["steps"]) if build else 0.0
        put(drums, kick(), t, 0.80 if full else 0.50 if half else 0.28 + 0.22 * grow)
        kicks.append(t)
    if b % 2 == 1 and (full or layer >= 3):
        put(drums, clap(), t, 0.26 if full else 0.14)
    if full or half or layer >= 1:
        put(drums, hat(), t + BEAT / 2, 0.16 if full else 0.09, pan=0.3)
        if full:
            put(drums, hat(0.03), t + BEAT / 4, 0.07, pan=-0.3)
            put(drums, hat(0.03), t + 3 * BEAT / 4, 0.07, pan=-0.3)
    if full:
        put(music, bass(root), t + BEAT / 2, 0.42)
        if b % 4 == 3:
            put(music, bass(root * 1.5), t + 3 * BEAT / 4, 0.3)
    elif half or layer >= 2:
        if b % 2 == 0:
            put(music, bass(root, 0.4), t + BEAT / 2, 0.3)

# the kick pushes the music down for an instant, so it reads on small speakers
duck = np.ones(N, np.float32)
for t in kicks:
    i0 = int(t * SR)
    seg = ax(0.3)[:N - i0]
    duck[i0:i0 + len(seg)] = np.minimum(duck[i0:i0 + len(seg)], 1 - 0.28 * np.exp(-seg / 0.09))
music *= duck[:, None]

# an arpeggio that never stops: eighth notes round the chord, from the count to the end.
# It is what carries the ear across the joins between sections.
for i in range(int(DUR / 0.25)):
    t = i * 0.25
    if t < SEC["tasks"] or t >= DUR - 3:
        continue
    _, tones = chord_at(t)
    if t < SEC["steps"]:                                                 # swelling all the way up to the first call
        level = 0.03 + 0.05 * (t - SEC["tasks"]) / (SEC["steps"] - SEC["tasks"])
    elif t < SEC["rule"]:
        level = 0.075
    elif t < SEC["drop"]:
        level = 0.15                                                     # the kick is out; the line carries the bar
    else:
        level = 0.10 if t < SEC["traps"] else 0.095
    f = tones[(0, 1, 2, 1)[i % 4]] * (4 if i % 8 == 7 else 2)
    put(music, note(f, 0.7, harmonics=3, decay=0.22), t, level, pan=0.35 if i % 2 else -0.35)

# the build, and the breath before the drop
R = SEC["rule"]
put(fx, riser(3.5), R, 0.42)
for i, t in enumerate(np.concatenate([np.arange(R + 2.0, R + 3.0, 0.25), np.arange(R + 3.0, R + 3.5, 0.125)])):
    put(drums, clap(), t, 0.05 + 0.012 * i)

# the melody of the drop is the data: a fabric's hem width picks its note
SCALE = [146.83, 174.61, 196.00, 220.00, 261.63, 293.66, 349.23]      # D F G A C D F
morphs = [c for c in cues if c["k"] == "morph"]
order = sorted(set(c["hem"] for c in morphs))
for c in morphs:
    f = SCALE[order.index(c["hem"]) * (len(SCALE) - 1) // max(1, len(order) - 1)]
    for echo, g in ((0.0, 0.34), (0.375, 0.15), (0.75, 0.07)):          # dotted-eighth echoes
        put(music, note(f * 2, 1.2), c["t"] + echo, g, pan=0.25 if echo else 0.0)
    put(music, note(f, 1.6, harmonics=3, decay=0.8), c["t"], 0.22)
    held = ax(2.6)
    put(music, (np.sin(2 * np.pi * f * 2 * held) + 0.3 * np.sin(2 * np.pi * f * 4 * held))
        * np.minimum(1, held / 0.25) * np.minimum(1, (2.6 - held) / 0.7), c["t"], 0.07)
    put(fx, whoosh(0.45), c["t"] - 0.2, 0.10)
# the wall keeps the two extremes ringing: narrowest, widest
for t, f in ((SEC["fan"], SCALE[0]), (SEC["fan"] + 2.0, SCALE[-1]), (SEC["fan"] + 4.0, SCALE[3])):
    for echo, g in ((0.0, 0.30), (0.375, 0.14), (0.75, 0.07)):
        put(music, note(f * 2, 1.2), t + echo, g, pan=-0.25 if echo else 0.0)

# everything the picture does
TASKS = [c["n"] for c in cues if c["k"] == "task"]
last = -1.0
for c in cues:
    k, t = c["k"], c["t"]
    if k == "dots":
        for i in range(37):                                              # one blip per column of dots
            put(fx, tick(700 * 2 ** (i / 24), 0.008), t + i * 0.028, 0.07, pan=(i / 18 - 1) * 0.6)
    elif k == "task":                                                    # a note for each job's share of the 846
        put(music, note(SCALE[[6, 4, 2, 0][TASKS.index(c["n"])]] * 2, 0.9), t, 0.26)
    elif k == "flatten":
        put(fx, whoosh(1.4), t, 0.20)
    elif k == "form":
        put(fx, riser(2.9), t, 0.16)
        put(fx, thump(), t + 2.9, 0.5)
    elif k == "loop":                                                    # three edges, then the hem, lower
        put(fx, tick(1300 + 250 * c["n"], 0.03) if c["n"] < 3 else note(SCALE[0] * 2, 1.0), t, 0.16 if c["n"] < 3 else 0.3)
    elif k == "fan":
        put(fx, thump(), t, 0.7)
        put(fx, whoosh(1.2), t, 0.22)
    elif k == "slam" and t - last > 0.2:
        loud = not (SEC["drop"] <= t < SEC["traps"])                     # under the kick a slam needs no thump
        put(fx, thump(), t, 0.20 if loud else 0.0)
        last = t
    elif k == "call":
        put(fx, tick(1200), t, 0.16)
        put(fx, tick(1800), t + 0.09, 0.12)
    elif k == "soft":
        pass                                                             # small lines arrive without a sound

def reverb(x, seconds=2.4, decay=0.5):
    """Convolve with a burst of decaying noise. Dry, synthesised sound has no room in it; this is the room."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    size = 1 << int(np.ceil(np.log2(N + n)))
    wet = np.zeros_like(x)
    for ch in range(2):
        ir = lowpass(rng.standard_normal(n), 6) * np.exp(-t / decay) * np.minimum(1, t / 0.012)
        ir /= np.sqrt((ir ** 2).sum())
        wet[:, ch] = np.fft.irfft(np.fft.rfft(x[:, ch], size) * np.fft.rfft(ir, size), size)[:N]
    return wet


cut = next(c["t"] for c in cues if c["k"] == "cutout")                   # the dry sound stops; the room rings on
i0, i1 = int(cut * SR), int((cut + 0.5) * SR)
gate = np.ones(N, np.float32)
gate[i0:i1] = np.clip(1 - np.arange(i1 - i0) / (0.06 * SR), 0, 1)
dry = drums + music + fx
mix = dry * gate[:, None] + 0.30 * reverb(music) + 0.16 * reverb(fx) + 0.06 * reverb(drums)
fade = int(4.0 * SR)
mix[-fade:] *= (np.linspace(1, 0, fade) ** 1.4)[:, None]
mix = np.tanh(mix * 1.15) / 1.15                                         # gentle glue, no hard clipping

raw = OUT / "audio_raw.wav"
subprocess.run([FF, "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", str(raw)],
               input=mix.astype(np.float32).tobytes(), check=True)
target = "loudnorm=I=-14:TP=-1.5:LRA=11"
log = subprocess.run([FF, "-hide_banner", "-i", str(raw), "-af", target + ":print_format=json",
                      "-f", "null", "-"], capture_output=True, text=True).stderr
m = json.loads(log[log.rindex("{"):log.rindex("}") + 1])
subprocess.run([FF, "-v", "error", "-y", "-i", str(raw), "-af",
                "%s:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true"
                % (target, m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"],
                   m["target_offset"]), "-ar", str(SR), str(OUT / "audio.wav")], check=True)
raw.unlink()
print("%d cue(s), %d kick(s), %.1f s, raw %s LUFS -> out/audio.wav" % (len(cues), len(kicks), DUR, m["input_i"]))
print("hem -> note:", ", ".join("%d mm %.0f Hz" % (h, SCALE[i * (len(SCALE) - 1) // max(1, len(order) - 1)])
                                for i, h in enumerate(order)))
