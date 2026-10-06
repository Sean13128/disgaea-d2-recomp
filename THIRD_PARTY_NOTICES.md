# Third-party notices

This project builds on, patches or links the following components. Each keeps
its own license; nothing here relicenses them.

| Component | Used for | License |
|---|---|---|
| [ps3recomp](https://github.com/sp00nznet/ps3recomp) (sp00nznet / Ned Heller) | Recompiler SDK and runtime. `patches/ps3recomp-d2-macos.diff` contains our modifications to it; `tools/bootstrap_sdk.sh` fetches upstream and applies them. | MIT, Copyright (c) 2026 Ned Heller / sp00nznet |
| at3_standalone (in ps3recomp `third_party/`, derived from PPSSPP / FFmpeg) | ATRAC3/ATRAC3plus audio decoding | LGPL-2.1 (see its `COPYING.LGPLv2.1`) |
| [SDL2](https://www.libsdl.org/) | Gamepad and audio output | zlib |
| [nlohmann/json](https://github.com/nlohmann/json) | Cheat/editor schema parsing | MIT |
| Apple frameworks (Metal, AppKit, VideoToolbox, CoreAudio) | Rendering, UI, movie decoding, audio | Apple SDK terms |
| Homebrew build dependencies (CMake, Ninja, FFmpeg, glslang, SPIRV-Cross) | Build tooling, installed by the user | Their respective licenses |

The ps3recomp MIT notice, reproduced as its license requires:

```
MIT License

Copyright (c) 2026 Ned Heller / sp00nznet

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Reference material consulted during development (not included): RPCS3 source
and issue tracker, community Cheat Engine / Apollo cheat documentation, and
public GameFAQs save files used only for local import testing.
