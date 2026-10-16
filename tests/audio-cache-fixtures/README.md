# OpenAL cache regression fixture

Run the complete ownership and resident-memory checks:

```sh
python3 scripts/test-audio-cache.py --accounting
```

`--engine-ref ceb9dcb` compiles the historical cache and reproduces lease and
buffer-lifetime failures. `--engine-ref 643614e --accounting` preserves the
ownership fix and reproduces the four old resident-accounting failures.
Both historical runs are expected to return nonzero.

The script copies the production cache implementation and its header without
editing their bytes. Only the filesystem, FFmpeg decoder and unrelated manager
types use fixtures. Each synthetic file emits one known PCM frame. The linked
OpenAL implementation is the real Emscripten SDK library; its buffer/source
reference tracking and buffer deletion are not mocked. The AudioContext shim
supplies Float32 channel arrays and connection methods without audio output.

The production lease helper always comes from the working tree. Its regression
uses a corrected-cache negative control: closing the lease while a stopped
source still owns AL_BUFFER blocks eviction, then detaching permits retry.
The test does not compile historical audio-manager transition code.
