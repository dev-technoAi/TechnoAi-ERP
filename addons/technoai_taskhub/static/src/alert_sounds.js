// Due-alert sounds, synthesised with the Web Audio API (same sounds as the original Task Hub)

let audioCtx = null;

function getContext() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
        return null;
    }
    if (!audioCtx || audioCtx.state === "closed") {
        audioCtx = new AudioContextClass();
    }
    if (audioCtx.state === "suspended") {
        audioCtx.resume();
    }
    return audioCtx;
}

function tone(ctx, out, { type, start, dur, freq, freqEnd, peak, attack = 0.02 }) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, start);
    if (freqEnd) {
        osc.frequency.exponentialRampToValueAtTime(freqEnd, start + dur);
    }
    gain.gain.setValueAtTime(0.001, start);
    gain.gain.linearRampToValueAtTime(peak, start + attack);
    gain.gain.exponentialRampToValueAtTime(0.001, start + dur);
    osc.connect(gain);
    gain.connect(out);
    osc.start(start);
    osc.stop(start + dur);
}

/**
 * @param {string} sound industrial-siren | digital-matrix | airport-chime | gentle-bell | none
 * @param {number} volume 0-100
 */
export function playAlertSound(sound = "industrial-siren", volume = 80) {
    if (sound === "none") {
        return;
    }
    try {
        const ctx = getContext();
        if (!ctx) {
            return;
        }
        // browsers only allow vibration after the user has interacted with the page
        if (navigator.vibrate && navigator.userActivation?.hasBeenActive) {
            navigator.vibrate([220, 80, 220, 80, 420]);
        }
        const now = ctx.currentTime;
        // the compressor keeps the louder sounds from clipping the speakers
        const compressor = ctx.createDynamicsCompressor();
        compressor.threshold.setValueAtTime(-14, now);
        compressor.knee.setValueAtTime(8, now);
        compressor.ratio.setValueAtTime(14, now);
        compressor.attack.setValueAtTime(0.003, now);
        compressor.release.setValueAtTime(0.12, now);
        const master = ctx.createGain();
        master.gain.setValueAtTime(Math.max(0, Math.min(100, volume)) / 100, now);
        compressor.connect(master);
        master.connect(ctx.destination);

        if (sound === "digital-matrix") {
            [587.33, 739.99, 880.0, 1046.5, 1318.51, 1567.98].forEach((freq, i) =>
                tone(ctx, compressor, { type: "sine", start: now + i * 0.07, dur: 0.14, freq, peak: 0.7, attack: 0.015 })
            );
        } else if (sound === "airport-chime") {
            [349.23, 440.0, 523.25].forEach((freq, i) =>
                tone(ctx, compressor, { type: "triangle", start: now + i * 0.28, dur: 0.65, freq, peak: 0.8, attack: 0.03 })
            );
        } else if (sound === "gentle-bell") {
            [880, 1760, 2640].forEach((freq, i) =>
                tone(ctx, compressor, { type: "sine", start: now, dur: 1.2, freq, peak: 0.7 / (i + 1) })
            );
        } else {
            // heavy industrial siren: four rising bursts with a bass punch
            const bursts = [
                { start: 0.0, dur: 0.16, fStart: 880, fEnd: 1100, bass: 150 },
                { start: 0.22, dur: 0.16, fStart: 932, fEnd: 1175, bass: 150 },
                { start: 0.44, dur: 0.16, fStart: 1046, fEnd: 1318, bass: 160 },
                { start: 0.66, dur: 0.45, fStart: 1174, fEnd: 1480, bass: 170 },
            ];
            for (const { start, dur, fStart, fEnd, bass } of bursts) {
                const t = now + start;
                tone(ctx, compressor, { type: "triangle", start: t, dur, freq: bass, freqEnd: 50, peak: 0.6 });
                tone(ctx, compressor, { type: "sawtooth", start: t, dur, freq: fStart, freqEnd: fEnd, peak: 0.55, attack: 0.015 });
                tone(ctx, compressor, { type: "square", start: t, dur, freq: fStart / 2, freqEnd: fEnd / 2, peak: 0.38 });
            }
        }
    } catch (error) {
        console.warn("Task Hub alert sound could not play", error);
    }
}
