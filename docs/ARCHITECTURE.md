# Architecture — JARVIS Voice Assistant

**Status:** Draft v1 (synced to code 2026-08-22)
**Date:** 2026-08-08
**Companion docs:** [PRD.md](./PRD.md) · [CONTEXT.md](./CONTEXT.md) (TBD) · [docs/adr/](./adr/) (TBD)

---

## 1. Overview

JARVIS is a Python voice client that wraps `opencode serve` (an HTTP server the opencode CLI already exposes). The voice client listens for a wake word, transcribes speech, sends text to opencode, streams the LLM response, and speaks it through Microsoft Edge TTS (`en-GB-RyanNeural`, a free neural British male voice), falling back to macOS `say` when the API is unreachable. JARVIS gains the full power of opencode — file reading, web search, MCP tool calls — without re-implementing any of it.

The architecture is a thin voice skin over a thick existing tool. Every component outside the voice pipeline is either an opencode primitive, a third-party library, or a small MCP wrapper.

---

## 2. System diagram

```
                            ┌────────────────────────────┐
                            │  opencode serve (port 4096) │
                            │  ─────────────────────────  │
                            │  /session                  │
   ┌──────────┐             │  /session/:id/message      │
   │   MIC    │──── audio ──▶│  /session/:id/abort        │     ┌──────────┐
   └──────────┘             │  /event (SSE)              │────▶│   LLM    │
        │                   └────────────────────────────┘     └──────────┘
        │ ear.py                      ▲                              ▲
        │  ├ openWakeWord             │                              │ tool calls
        │  └ mlx-whisper              │ text + tool calls            │
        ▼                             │                              │
   ┌──────────┐  text   ┌──────────────────────────┐                  │
   │  turn    │────────▶│  brain.py                │──────────────────┘
   │  end     │         │  ──────────────────      │
   │ detection│         │  httpx async client      │
   └──────────┘         │  session lifecycle       │
                        │  abort on barge-in       │
                        └──────────────────────────┘
                                  │ text deltas (SSE)
                                  ▼
                        ┌──────────────────────────┐
                        │  sentence_splitter.py    │
                        │  ──────────────────      │
                        │  accumulate buffer       │
                        │  split on [.!?] + space  │
                        │  flush at 200 chars max  │
                        └──────────────────────────┘
                                  │ sentences
                                  ▼
                        ┌──────────────────────────┐
                        │  mouth.py                │
                        │  ──────────────────      │
                         │  Edge TTS / macOS say   │
                        │  sounddevice output      │
                        │  interruptible           │
                        └──────────────────────────┘
                                  │ MP3 chunks
                                  ▼
                             ┌──────────┐
                             │  SPEAKER │
                             └──────────┘

  ┌────────────────────┐         ┌────────────────────┐
  │  MCP: system       │         │  MCP: dev          │
  │  ──────────────    │         │  ──────────────    │
  │  open_app          │         │  open_file         │
  │  close_app         │         │  open_project      │
  │  list_apps         │         │  show_file         │
  │  get/set_volume    │         │  find_grep         │
  │  get_battery       │         │  git_*             │
  │  get_time          │         │  run_tests         │
  └────────────────────┘         └────────────────────┘
            ▲                              ▲
            └──────────┬───────────────────┘
                       │ tool calls (via opencode)
                       │
                ┌──────┴──────┐
                │   notes/    │  ← long-term memory
                │  ────────   │     (user.md, preferences.md,
                │  user.md    │      projects.md)
                │  prefs.md   │
                │  projects.md│
                └─────────────┘
```

---

## 3. Components

> **Current status:** Phases 0–1 and the first two Phase 2 slices (Slice 8 — sentence-level
> TTS streaming; Slice 9 — Edge TTS voice) are built and merged. The `Mouth` port is wired
> to `EdgeTtsMouth` (edge-tts → miniaudio → sounddevice); `ui`, the MCP wrappers, `notes/`,
> and the macOS `say` fallback are still planned. Module paths below reflect the DDD layout
> (`domain/` = ports + pure logic, `application/` = use cases, `infrastructure/` =
> adapters), not the original flat `jarvis/` layout.

### 3.1 Voice input — `domain/senses/ear.py` + `infrastructure/sense/`

**Responsibility:** Wake word detection + speech-to-text.

The `Ear` protocol (`domain/senses/ear.py`) exposes `listen_for_wake_command()` and
`transcribe_utterance(timeout: float) -> str | None`. `OpenWakeWordEar`
(`infrastructure/sense/openwakeword_ear.py`) implements both over a `sounddevice`
input stream; `transcribe_utterance` returns `None` when the no-command timeout
elapses before any speech.

| Sub-component | Library | Where |
|---|---|---|
| Wake word | `openwakeword` | `OpenWakeWordDetector` in `openwakeword_ear.py` |
| STT | `mlx-whisper` | `MlxWhisperTranscriber` in `mlx_whisper_transcriber.py` |
| Audio capture | `sounddevice` | `OpenWakeWordEar` input stream (16 kHz, int16, 80 ms chunks) |
| End-of-turn | RMS silence detector (custom) | `SilenceDetector` in `domain/senses/silence_detector.py`, 1.5 s default |
| No-command timeout | leading-silence tracking (`speech_started`) | `OpenWakeWordEar.transcribe_utterance(timeout)`, 30 s / 5 s set by `Assistant` |

**Wake-no-command timeout:** after wake, `Assistant` calls
`transcribe_utterance(timeout=30.0)`; if the user never speaks, the ear returns
`None`, the assistant prints an "are you there, sir?" prompt, then listens 5 s more
(`timeout=5.0`) before returning to wake. `SilenceDetector.feed()` flips
`speech_started` `True` on the first non-silent chunk, and the ear discards leading
silent chunks so the 10 s utterance cap starts at speech onset, not wake.

**STT accuracy:** `MlxWhisperTranscriber.transcribe()` pins `language="en"` and
`temperature=0.0` (greedy decoding) so short English commands decode deterministically.
Whisper's default language auto-detect and temperature fallback hallucinate on
quiet/noisy input; both are disabled here.

**Test seam:** `SilenceDetector` (pure numpy) and `MlxWhisperTranscriber` (stubbed
`mlx_whisper`) are unit-tested without real audio. `OpenWakeWordEar.transcribe_utterance`
is unit-tested with a stubbed `sounddevice` stream (its `sleep` drives the callback
with scripted chunks), and the `Assistant` orchestration is tested with a fake `Ear`.

### 3.2 Conversation engine — `domain/brain.py` + `infrastructure/opencode/brain_client.py`

**Responsibility:** All communication with `opencode serve`.

The `Brain` protocol (`domain/brain.py`) is implemented by `OpenCodeBrain`
(`infrastructure/opencode/brain_client.py`).

| Concern | Mechanism |
|---|---|
| Session lifecycle | `POST /session` on first turn, reuse across turns |
| Send message (blocking) | `POST /session/:id/message` (synchronous — blocks until full response) |
| Send message (streaming) | `POST /session/:id/prompt_async` (no wait), then `GET /event` SSE for `message.part.delta` text chunks |
| Reasoning filter | track reasoning part IDs from `message.part.updated`, skip their `message.part.delta` events |
| Abort turn | `POST /session/:id/abort` on barge-in |
| Persona | the `jarvis` agent in `opencode.json` → `persona/AGENTS.md` |

**Test seam:** httpx client mockable with `respx`. Tests exercise session creation, message send, abort, and `stream_turn` (delta yield, reasoning/cross-session filtering, `session.idle` termination).

### 3.3 SSE parser — `infrastructure/opencode/event_stream.py`

**Responsibility:** Convert raw SSE bytes into typed events.

**Output shape:**
```python
class Event:
    type: Literal[
        "message.updated",
        "message.part.updated",
        "message.part.delta",
        "session.idle",
        "session.error",
        "server.connected",
    ]
    data: dict
```

**Test seam:** pure function over byte stream, fast unit tests.

### 3.4 Text chunker — `domain/text/sentence_splitter.py`

**Responsibility:** Accumulate text deltas, flush complete sentences to TTS.

**Algorithm:**
1. Append each delta to buffer
2. Look for sentence boundary: `re.compile(r"(?<=[.!?])\s+")` via `.search()`
3. Flush complete sentences immediately
4. If buffer exceeds 200 chars without a boundary, flush on word boundary (avoid starvation)
5. Flush remainder on `session.idle` event

**Test seam:** pure function over list of deltas. Many small unit tests.

### 3.5 Voice output — `domain/senses/mouth.py` + `infrastructure/sense/edge_tts_mouth.py`

**Responsibility:** Text → speech via Microsoft Edge TTS + audio playback. The macOS `say` fallback is planned (Slice `#86`), not yet built.

The `Mouth` protocol (`speak`, `stop`, both async) lives in
`domain/senses/mouth.py`. `EdgeTtsMouth` (`infrastructure/sense/edge_tts_mouth.py`)
implements it: `speak` synthesizes text to PCM via the `synthesize` seam, then plays
it; `stop` halts playback. `synthesize` streams MP3 from edge-tts
(`en-GB-RyanNeural`), decodes it to int16 mono 24 kHz PCM via `miniaudio`, and returns
the raw bytes. Playback runs on a worker thread (`asyncio.to_thread`).

| Sub-component | Library | Notes |
|---|---|---|
| TTS (primary) | `edge-tts` | free neural TTS, `en-GB-RyanNeural` British male voice, streaming MP3 |
| Decode | `miniaudio` | MP3 → int16 mono PCM (24 kHz) |
| Playback | `sounddevice` | PCM bytes → output stream |
| TTS (fallback, planned) | macOS `say` | instant, local, zero cost, British voices (`daniel`) |

**Test seam:** `EdgeTtsMouth.synthesize` (text → PCM bytes) is the seam.
`tests/test_edge_tts_mouth.py` stubs edge_tts, miniaudio, and sounddevice in
`sys.modules` and asserts audio-message filtering, voice forwarding, decode params,
and `speak`/`stop` playback — no real audio.

### 3.6 Rich terminal UI — `ui.py` (planned)

**Responsibility:** Display what JARVIS is doing (for dev/debug; in production, mostly silent).

| Panel | Content |
|---|---|
| Status | wake / listening / thinking / speaking / idle |
| Transcript | last user utterance |
| Tool calls | current tool, last N tools |
| Errors | recent errors with stack traces |

### 3.7 Orchestration — `main.py` + `application/assistant.py` (partial)

**Responsibility:** Wire all components together. The "main loop."

Currently implemented: `Assistant.run()` is async (one event loop for the whole app)
and loops `_listen_for_a_command()`, which waits for the wake word and transcribes via
`asyncio.to_thread` (the blocking sounddevice calls run on worker threads), greets once
per session, then transcribes with a 30 s no-command timeout; on `None` it prompts "are
you there, sir?" and listens 5 s more before returning to wake. A transcript is sent to
`_respond()`, which streams `brain.stream_turn(utterance)` through a `SentenceSplitter`
and speaks each complete sentence (plus the flush remainder). The full loop below is
the target:

```
while True:
    wait for wake
    prompt = ear.transcribe_utterance()
    if prompt in dismissals: continue
    if prompt in farewells: sign_off(); break
    if not prompt: timeout_or_prompt(); continue
    brain.send_turn(prompt)
    for delta in brain.stream():
        if barge_in_detected():
            brain.abort()
            break
        sentence = splitter.feed(delta)
        if sentence: mouth.speak(sentence)
    if idle_timeout(): break
```

### 3.8 MCP wrappers — Action layer (planned)

**Two MCP servers**, each running as a small Python process that opencode spawns:

#### `system_actions` (general use)
- `open_app(name)` — `open -a` (whitelisted names only)
- `close_app(name)` — `osascript -e 'quit app ...'`
- `list_running_apps()` — `osascript`
- `get_volume()` / `set_volume(level)` — `osascript`
- `get_battery()` — `pmset`
- `get_time()` — `datetime`

**Whitelisted apps** (PRD §4): Safari, Chrome, Firefox, Spotify, Music, Notes, Calendar, Reminders, Mail, Messages, Terminal, iTerm, Ghostty, VS Code, Cursor, Finder, System Settings, Slack, Discord, Zoom.

#### `dev_actions` (developer use)
- `open_file_in_editor(file)` — opens in nvim in a new Ghostty window
- `open_project(name)` — resolves alias via `notes/projects.md`, opens new Ghostty window with `cd` and `nvim`
- `show_file(file)` — reads file, returns content
- `find_grep(pattern)` — `rg` within the project
- `git_status / git_diff / git_log` — `git` in the project
- `run_tests` — auto-detect runner (pytest, jest, cargo, go test) and execute

**Path scope:** every dev action resolves paths against `~/Documents/projects/` and rejects anything outside. No exceptions.

### 3.9 Long-term memory — `notes/` (planned)

A directory where the LLM can read and write long-term memory. The persona lives
in `persona/AGENTS.md` (wired via the `jarvis` agent in `opencode.json`); the
separate `jarvis_home/` project dir described in early planning no longer exists.

```
notes/
├── user.md        ← user's name, role, preferences
├── preferences.md ← "I prefer dark mode", etc.
└── projects.md    ← alias map: "JARVIS" → jarvis/, "monoflow" → monoflow/
```

The `write` tool is whitelisted only on this path. The MCP wrapper enforces this.

---

## 4. Data flow

### 4.1 One turn (happy path)

```
[mic] audio bytes
  └─▶ ear.openwakeword (background)
        └─▶ wake detected → start recording
              └─▶ ear.mlx_whisper(audio) → "what time is it"
                    └─▶ brain.stream_turn("what time is it")
                          └─▶ opencode (POST /session/:id/prompt_async)
                                └─▶ LLM (sees AGENTS.md, notes/, tools)
                                      └─▶ response delta: "Certainly,"
                                            └─▶ brain.stream_turn yields message.part.delta (SSE /event)
                                                  └─▶ splitter.feed("Certainly,")
                                                        └─▶ buffer too small, no flush
                                                  └─▶ response delta: " sir. The time is 14:32."
                                                        └─▶ splitter.feed("Certainly, sir. The time is 14:32.")
                                                              └─▶ flush "Certainly, sir." → mouth
                                                              └─▶ flush "The time is 14:32." → mouth
                                                  └─▶ session.idle event
                                                        └─▶ splitter.flush() (no remainder)
  └─▶ mouth.speak("Certainly, sir.")  ─▶ speaker
  └─▶ mouth.speak("The time is 14:32.") ─▶ speaker
```

### 4.2 Barge-in (mid-response interrupt)

```
[mouth playing sentence N]
  └─▶ mic detects speech → ear.mlx_whisper (interrupt priority)
        └─▶ barge-in signal → main loop
              └─▶ brain.abort() (POST /session/:id/abort)
                    └─▶ mouth.stop() (drain output stream)
                          └─▶ ear.start_recording() (new turn)
```

### 4.3 Tool call (e.g. "open Spotify")

```
[user: "open Spotify"]
  └─▶ brain.send_turn("open Spotify")
        └─▶ LLM emits tool call: open_app(name="Spotify")
              └─▶ brain detects tool call before any text delta
                    └─▶ status: "Opening Spotify, sir." (spoken immediately)
                          └─▶ MCP system_actions.open_app("Spotify")
                                └─▶ osascript → Spotify launches
                          └─▶ LLM receives tool result
                                └─▶ response: "Spotify is open, sir."
                                      └─▶ mouth speaks
```

---

## 5. Key interfaces

### 5.1 Python module boundaries

```python
# ear.py
class Ear:
    def listen_for_wake_command() -> None: ...  # blocking; run via asyncio.to_thread
    def transcribe_utterance(timeout: float) -> str | None: ...


# brain.py
class Brain:
    async def send_turn(message: str) -> TurnResult: ...  # blocking, full response
    def stream_turn(message: str) -> AsyncIterator[str]: ...  # yields text deltas
    async def abort() -> None: ...
    async def close() -> None: ...


# sentence_splitter.py
class SentenceSplitter:
    def feed(self, delta: str) -> Iterator[str]: ...  # yields complete sentences
    def flush(self) -> str | None: ...  # returns remainder on end-of-stream


# mouth.py
class Mouth:
    async def speak(self, text: str) -> None: ...
    async def stop(self) -> None: ...  # immediate, drain not required


# ui.py
class UI:
    def show_status(self, state: str) -> None: ...
    def show_transcript(self, text: str) -> None: ...
    def show_tool(self, name: str, args: dict) -> None: ...
    def show_error(self, err: Exception) -> None: ...
```

### 5.2 opencode HTTP API (consumed)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/global/health` | liveness check |
| `POST` | `/session` | create session, returns `{id}` |
| `POST` | `/session/:id/message` | send a turn, blocks until full response |
| `POST` | `/session/:id/prompt_async` | send a turn without waiting (returns 204) |
| `GET` | `/event` | SSE stream of session events |
| `POST` | `/session/:id/abort` | abort current turn |

All calls use `Authorization: Basic opencode:<password>` (`httpx.BasicAuth`), where
`<password>` is `OPENCODE_SERVER_PASSWORD` from `.env`.

### 5.3 Tool policy (enforced in MCP + opencode config)

```jsonc
{
  "read": "allow",
  "webfetch": "allow",
  "websearch": "allow",
  "bash": "allow",  // MCP wrapper filters to whitelist
  "write": "deny",  // except notes/ — MCP wrapper allows path-scoped writes
  "edit": "deny"
}
```

The MCP wrappers are the policy enforcement boundary. opencode sees only the wrappers' exposed tool names; the wrappers internally reject anything outside their scope.

---

## 6. Trust boundaries

```
┌────────────────────────────────────────────────────────────┐
│ TRUSTED (Python client + opencode server)                  │
│  - ear.py, brain.py, splitter, mouth.py, ui.py, main.py   │
│  - opencode server, SSE, tool policy                       │
│  - MCP wrappers (system_actions, dev_actions)              │
│  - notes/ directory (writable by LLM)                      │
└────────────────────────────────────────────────────────────┘
                          ▲
                          │ tool calls cross here
                          │
┌────────────────────────────────────────────────────────────┐
│ UNTRUSTED (LLM-mediated actions)                           │
│  - shell commands (whitelisted via MCP)                    │
│  - file reads (scoped to ~/Documents/projects/ for dev)    │
│  - file writes (scoped to notes/ only)                     │
│  - network calls (webfetch/websearch)                      │
└────────────────────────────────────────────────────────────┘
                          ▲
                          │ the LLM decides what to call
                          │
                     ┌────────┐
                     │  LLM   │
                     └────────┘
```

**Invariants the LLM cannot violate** (enforced in MCP wrappers, not in the prompt):
1. Shell commands can only be from the system_actions / dev_actions whitelist
2. Dev action file paths must resolve under `~/Documents/projects/`
3. Writes are only allowed to `notes/`
4. Bash can only be invoked through the MCP wrapper, which filters before exec

---

## 7. Failure modes & fallbacks

| Failure | Detection | Fallback |
|---|---|---|
| `opencode serve` down | `GET /global/health` fails on boot | exit with clear error, LaunchAgent restart loop |
| Edge TTS unreachable | HTTP error or timeout from Microsoft's TTS API | fall back to system `say` (TTS via macOS, no neural voice) |
| macOS mic permission denied | `sounddevice` raises on stream open | text-only mode (loop still works with typed input) |
| LLM refuses | response is "I cannot..." | speak refusal verbatim, no paraphrase |
| LLM tool call rejected by MCP | MCP raises | speak "I couldn't do that, sir", surface error in UI |
| mlx-whisper fails | exception in `transcribe()` | retry once, then "Sorry sir, I didn't catch that" |
| Edge TTS slow | response delayed | continue buffering, flush all at session.idle or force `say` fallback |
| User speaks during TTS | barge-in detected | abort turn, full stop, restart with new input |
| Process crashes | any unhandled exception | LaunchAgent restart loop with backoff |

---

## 8. Latency budget

| Stage | Time | Notes |
|---|---|---|
| Wake detection | <100ms | openWakeWord runs continuously, low CPU |
| STT (short utterance) | 1-2s | mlx-whisper on M-series |
| LLM first token | 2-4s | depends on model, prompt size |
| First sentence spoken | +500ms | after first sentence boundary in delta |
| Subsequent sentences | streaming | overlapped with TTS playback |

**End-to-end (wake to first speech):** ~3-5s, accepted as the latency budget for a butler persona.

**Streaming benefit:** with sentence-level TTS, JARVIS starts speaking well before the LLM finishes generating. The user perceives maybe 4-5s total.

---

## 9. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Brain | `opencode serve` | already in user's stack, full tool ecosystem |
| HTTP client | `httpx` + `httpx-sse` | async-native, SSE support, OpenAPI ecosystem |
| STT | `mlx-whisper` | Apple Silicon native, fast, accurate |
| Wake | `openwakeword` | open-source, no cloud |
| TTS | `edge-tts` + macOS `say` fallback | free neural TTS, `en-GB-RyanNeural` British male voice, no API key |
| Audio | `sounddevice` + `miniaudio` + `numpy` | low-level playback + MP3→PCM decode, enough for interruption |
| UI | `rich` | terminal panels, low ceremony |
| Config | `python-dotenv` | `.env` for API keys, server password |
| Validation | `pydantic` | typed event shapes |
| Tests | `pytest` + `pytest-asyncio` + `respx` | standard, httpx mockable |

**Pinned versions:** see `requirements.txt` (Day 1).

---

## 10. Architectural decisions (pointers)

| ADR | Decision | Why it matters |
|---|---|---|
| [ADR-0001](./adr/0001-hybrid-session-model.md) | Hybrid session model | Fresh per launch + `notes/` for long-term |
| [ADR-0002](./adr/0002-sentence-level-tts.md) | Sentence-level TTS streaming | Perceived latency vs simple whole-response TTS |
| [ADR-0003](./adr/0003-mcp-bash-wrapper.md) | MCP wrapper for whitelisted bash | Policy enforcement, not prompt enforcement |
| [ADR-0004](./adr/0004-tool-call-status.md) | Tool-call-aware status updates | User visibility into LLM activity |

ADRs are written during Phase 0. Until then, the decisions live in the PRD and this doc.

---

## 11. Glossary

See [CONTEXT.md](./CONTEXT.md) for the canonical glossary (20 terms: turn, barge-in, wake, filler, tool-call, quota, session, delta, flush, sentence, MCP, ADR, persona, alias, fall-back, abort, idle, dismiss, farewell, scope). Written in Phase 0.

---

## 12. Open architecture questions

These are not blockers but worth flagging:

1. **Multiple JARVIS instances** — could two JARVIS processes run at once (e.g. for different users or different wake words)? Today, the design assumes one. If multi-instance is wanted, the LaunchAgent needs a per-user config and the opencode session would be per-instance.
2. **Wake word false positives** — openWakeWord's pre-trained "hey jarvis" model may trigger on similar phrases. Mitigations: threshold tuning (0.5 → 0.7), custom-trained model, or push-to-talk fallback. Deferred to production polish.
3. **Streaming abort granularity** — when the user barges in, can we abort mid-token at the LLM level, or only mid-response? `POST /session/:id/abort` semantics need verification on Day 1.
4. **Notes file contention** — if the LLM writes to `notes/user.md` while the user is editing it externally, last-write-wins. Probably fine for MVP, but a real conflict-resolution strategy could be added later.
5. **MCP server lifecycle** — the MCP servers are spawned by opencode, but JARVIS itself needs to know they're healthy. A startup ping per MCP would catch misconfig early.

These are not architectural defects; they are future-work notes.
