// External WebAudio surface only; OpenAL buffer/source bookkeeping is the SDK's.
class FixtureAudioContext {
  constructor() { this.currentTime = 0; this.sampleRate = 22050; this.state = 'running'; this.destination = {}; }
  createGain() { return {gain: {value: 1}, connect() {}, disconnect() {}}; }
  createBuffer(channels, length, sampleRate) {
    const planes = Array.from({length: channels}, () => new Float32Array(length));
    return {numberOfChannels: channels, length, sampleRate, duration: length / sampleRate,
      getChannelData: channel => planes[channel]};
  }
  close() { return Promise.resolve(); }
}
globalThis.AudioContext = FixtureAudioContext;
globalThis.window = {AudioContext: FixtureAudioContext};
globalThis.document = {addEventListener() {}, getElementById() { return null; }};
