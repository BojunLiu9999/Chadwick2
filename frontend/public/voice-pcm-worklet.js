// AudioWorkletProcessor that downsamples mic audio from the AudioContext's
// native sample rate (typically 48 kHz) to 24 kHz mono Int16 LE PCM and
// posts the resulting frames as binary chunks to the main thread.
//
// Output chunk size = 960 samples (40 ms at 24 kHz). Small enough for low
// latency, large enough to keep postMessage overhead down.

class PcmDownsamplerProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super()
    const opts = (options && options.processorOptions) || {}
    this.targetRate = opts.targetRate || 24000
    this.chunkSamples = opts.chunkSamples || 960
    this.outBuffer = []
    this.srcOffset = 0
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || input.length === 0) return true
    const ch = input[0]
    if (!ch || ch.length === 0) return true

    const ratio = sampleRate / this.targetRate
    let i = this.srcOffset
    while (i < ch.length) {
      const idx = Math.floor(i)
      const frac = i - idx
      const a = ch[idx]
      const b = idx + 1 < ch.length ? ch[idx + 1] : a
      this.outBuffer.push(a + (b - a) * frac)
      i += ratio
    }
    this.srcOffset = i - ch.length

    while (this.outBuffer.length >= this.chunkSamples) {
      const slice = this.outBuffer.splice(0, this.chunkSamples)
      const i16 = new Int16Array(this.chunkSamples)
      for (let k = 0; k < this.chunkSamples; k++) {
        let s = slice[k]
        if (s > 1) s = 1
        else if (s < -1) s = -1
        i16[k] = s < 0 ? (s * 32768) | 0 : (s * 32767) | 0
      }
      this.port.postMessage(i16.buffer, [i16.buffer])
    }

    return true
  }
}

registerProcessor('pcm-downsampler', PcmDownsamplerProcessor)
