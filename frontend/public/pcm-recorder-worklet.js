// AudioWorklet processor: downsamples mic input to mono PCM16 at a target
// sample rate (default 16kHz, matching Sarvam's realtime STT expectations)
// and posts fixed-size chunks back to the main thread.
class PCMRecorderProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = options.processorOptions || {};
    this.targetSampleRate = opts.targetSampleRate || 16000;
    this.resampleRatio = sampleRate / this.targetSampleRate;
    this.chunkSamples = Math.round(this.targetSampleRate * 0.03); // ~30ms chunks
    this.buffer = [];
    this.carry = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (input && input.length > 0) {
      this._resampleAndBuffer(input[0]);
    }
    return true;
  }

  _resampleAndBuffer(channelData) {
    let pos = this.carry;
    const resampled = [];
    while (pos < channelData.length) {
      const idx = Math.floor(pos);
      const frac = pos - idx;
      const s0 = channelData[idx] || 0;
      const s1 = channelData[idx + 1] !== undefined ? channelData[idx + 1] : s0;
      resampled.push(s0 + (s1 - s0) * frac);
      pos += this.resampleRatio;
    }
    this.carry = pos - channelData.length;

    for (const sample of resampled) this.buffer.push(sample);

    while (this.buffer.length >= this.chunkSamples) {
      const chunk = this.buffer.splice(0, this.chunkSamples);
      const pcm16 = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
  }
}

registerProcessor('pcm-recorder-processor', PCMRecorderProcessor);
