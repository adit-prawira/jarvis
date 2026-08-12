# Background — JARVIS Voice Assistant

**Status:** Draft v1
**Date:** 2026-08-08
**Companion docs:** [PRD.md](./PRD.md) · [ARCHITECTURE.md](./ARCHITECTURE.md) · [PHASES.md](./PHASES.md) (TBD)

This document captures the *why* behind JARVIS. The PRD says what we're building. The architecture says how. This one says where the idea came from, what was considered and rejected, and the tradeoffs we're knowingly accepting.

---

## 1. Origin

The project started as a generic question: "what are some fun AI project ideas in Python?" The user is an intermediate-to-advanced Python developer with an Apple Silicon Mac, paying for the opencode subscription, and looking for a project that combines several interests — voice interfaces, LLM-driven agents, system automation, and developer ergonomics.

The first shortlist was broad: a code-review bot, a research assistant, a personal knowledge graph, a TUI-driven task runner, a voice assistant. The user gravitated toward a voice assistant almost immediately, and the *JARVIS* framing came from a follow-up: "I want it to feel like Iron Man's assistant."

That single aesthetic choice — butler persona, "sir", dry wit — did most of the design work. Everything else followed from trying to make that character feel real: terse responses, immediate action, polite refusals, no chit-chat.

---

## 2. Who is this for

The user is the only intended user. JARVIS is not a product. There is no planned release, no multi-user support, no marketplace. It's a personal tool that:

- runs on a single macOS machine
- responds to one voice (the user's)
- integrates with the user's existing project folder
- uses the user's opencode subscription
- knows the user's projects by name (via `notes/projects.md`)

This single-user framing lets us make decisions that would be wrong in a multi-user product: e.g. hard-coding the project root, skipping authentication on local services, accepting the latency that a real-time product would reject.

---

## 3. The key insight

The most consequential discovery during planning was that **opencode is already an HTTP server, not just a CLI tool.**

The user's mental model going in was: "I pay for opencode go, so I have an LLM API key I can call directly." That's a common misunderstanding. opencode is a coding agent, not an LLM provider. It has a CLI TUI, a tool system, and a session model. It does not expose a "give me a prompt, give me a response" API.

What it *does* expose is a full HTTP server (`opencode serve`) with the same tool ecosystem the TUI uses. Session lifecycle, message sending, event streaming, abort — all there. The TUI is itself a client of that server.

This is the unlock: **JARVIS doesn't need to be a stand-alone LLM app.** It can be another client of the same server the TUI uses. That gives us, for free:

- the LLM model the user is already paying for
- all opencode tools (bash, read, write, edit, webfetch, websearch)
- session persistence
- SSE event streaming
- permission system
- project context (the `AGENTS.md` file)
- the same conversation history the TUI would have

JARVIS becomes a voice skin, not a brain. The brain already exists. This is the difference between a 6-day project and a 6-month project.

---

## 4. Why voice

The user works at a desk and has a keyboard. Voice is not the most efficient way to run shell commands. So why voice?

Three reasons, in order of weight:

1. **The aesthetic.** Iron Man's JARVIS is voice-driven. The persona only works if the interaction is voice. A text-based "butler" feels like a chatbot. A voice butler feels like a butler.

2. **The constraint as feature.** A voice interface forces terse, focused interactions. You can't paste a 200-line stack trace; you have to ask "what's wrong with the build?" That pressure produces better AGENTS.md design and a more disciplined tool set.

3. **Latency tolerance.** A voice interface normalizes a 3-5s response time. The user said upfront that this was fine. For real-time conversation, you'd need a different architecture; for a butler, the slow-but-stately response is part of the character.

Voice is a deliberate design choice, not a technical default.

---

## 5. Why these specific tools

Every dependency was selected to fit the constraints: macOS, Apple Silicon, local-first, no extra cloud lock-in, fast enough for voice.

| Choice | Why this and not the alternative |
|---|---|
| `mlx-whisper` (STT) | Native to Apple Silicon, no GPU quota, runs offline. Faster-Whisper would also work but lacks the M-series optimization. |
| `openwakeword` (wake word) | Open-source, runs locally, no cloud round-trip. Picovoice/Porcupine would work but require accounts and per-device licenses. |
| `edge-tts` (TTS) | Free Microsoft Edge neural TTS, no API key, no quota, cross-platform. `en-GB-RyanNeural` is a crisp British male voice. macOS `say` is an instant local fallback. |
| `httpx` + `httpx-sse` (HTTP) | Async-native, supports SSE without extra plumbing. `aiohttp` is fine but `httpx` has better type hints. |
| `rich` (UI) | Low ceremony for terminal panels, good for the dev/debug overlay. Not used in production where JARVIS is mostly silent. |
| `sounddevice` (audio) | Direct PortAudio binding, low latency, easy to interrupt. PyAudio works but is older. |
| `pytest` + `respx` (tests) | Standard, the `respx` library makes httpx mocking trivial. |
| macOS LaunchAgent (auto-start) | Native to the platform. systemd-equivalent on Linux would be different; we're macOS-only. |

---

## 6. What was considered and rejected

A few directions were considered and explicitly dropped.

**Reuse Siri shortcuts via AppleScript.** Pro: zero development. Con: no LLM, no personality, no opencode integration. The "butler" framing dies immediately. Rejected.

**Direct LLM API call (OpenAI / Anthropic) without opencode.** Pro: simpler. Con: requires a separate API key, doesn't use the user's opencode subscription, loses all the tools (bash, read, etc.), loses session context, and re-implements what opencode already does well. Rejected because the opencode-server architecture is strictly more powerful for the same effort.

**Voice Activity Detection (VAD) for end-of-turn.** Considered using webrtcvad or silero-vad to detect when the user stops speaking. Decided against for MVP — a simple silence-duration threshold in the audio stream is sufficient, and the more sophisticated VADs add complexity without much value at this scale.

**Custom wake word model.** openWakeWord ships with "hey jarvis" out of the box. Training a custom one is overkill for a single-user project. Defer to a future iteration if false-positive rate is unacceptable.

**Local LLM (Ollama, LM Studio).** Could remove the opencode-server dependency entirely. Rejected because (a) the user already pays for opencode, (b) opencode's tool ecosystem is the value, (c) local models are slower and dumber than cloud models at this size. If opencode subscription lapses, revisit.

**Push-to-talk from day one.** Considered a hotkey fallback alongside the wake word. Deferred to post-MVP because (a) the wake word alone is sufficient for a single user, (b) implementing push-to-talk adds a global hotkey library and a second input mode, (c) we want to see how often the wake word fails before adding the fallback.

---

## 7. Tradeoffs knowingly accepted

A real product would not accept these. A personal tool can.

- **~3-5s first-token latency.** Voice interactions normalize this. A real-time chatbot would reject it.
- **Edge TTS depends on Microsoft's free API.** No quota, no key, no account — but the API could be retired or rate-limited. Has been stable since 2021 with no signs of deprecation. `say` fallback covers outages.
- **macOS-only.** No path to Linux or Windows. The system actions (`osascript`, AppleScript app control) don't port.
- **No push-to-talk.** If wake word fails, the user has to type. That's a real fallback gap.
- **Opencode subscription as single point of failure.** If opencode changes its API, JARVIS breaks. Risk is low (opencode is well-maintained) but real.
- **No conflict resolution on `notes/`.** If the user edits a notes file externally while the LLM writes to it, last-write-wins. Acceptable for MVP; could add a lock later.
- **JARVIS = one process, one user.** No multi-user, no multi-device. If the user has two Macs, two JARVIS instances would conflict on the opencode session.
- **Sentence-level TTS means prosody is choppy.** Each sentence is synthesized independently, so the voice doesn't always flow naturally across sentence boundaries. The persona is dry/formal enough that this works; a more emotive voice would suffer.
- **No observability beyond stderr.** No metrics, no traces, no log aggregation. If JARVIS misbehaves, you read the terminal. Fine for a personal tool.

---

## 8. Constraints and non-goals

Locked in the PRD and reinforced here for emphasis:

- No cross-platform support in MVP.
- No voice biometrics (one user, no need to distinguish).
- No real-time conversation (latency budget accepted).
- No editing files via voice (write/edit denied).
- No arbitrary shell commands (whitelist only).
- No operations outside `~/Documents/projects/` for dev actions.
- No mobile client.
- No web UI.
- No custom wake word training.
- No voice cloning (community voice only).

These are deliberate. Adding any of them would expand scope meaningfully and is not part of the current build.

---

## 9. The vision

A butler that knows the user's projects, addresses them as "sir", refuses politely, and never makes them touch the keyboard for routine work. A personal tool that earns the Iron Man reference, not one that name-drops it.

When it's done, the user should be able to say "hey jarvis, open monoflow, run the tests, and tell me if anything broke" — and get exactly that, without having to type, without having to wait, without the assistant asking for clarification. That's the bar. Not "AI assistant" in the abstract. Specifically that interaction, executed correctly, with personality intact.

If JARVIS ever becomes more than that — a public tool, a platform, a product — it should be rebuilt with a different PRD, a different architecture, and probably a different name. This project is deliberately a personal-butler-shaped object. It should not be generalized.

---

## 10. Open narrative questions

These are not blockers; they're the kinds of things that emerge as the project lives.

1. **Will the persona age?** Dry butler is a strong aesthetic. Will it still feel right after 100 hours of use? Easy to tune in `AGENTS.md`, but worth noticing.
2. **Will the user want a second wake word?** "Computer" is the Star Trek equivalent. Easy to add with openWakeWord's pre-trained models. Defer until asked.
3. **Will memory actually help?** The `notes/` design assumes long-term memory is valuable. If the user doesn't end up telling JARVIS things to remember, the directory will go unused. Check after 30 days.
4. **Will the dev actions actually be used?** "Open the JARVIS project" is a fun demo. If the user only ever asks general questions, the MCP dev wrapper is over-engineered. Build it; see if it's used.
5. **What does JARVIS sound like in 2027?** Microsoft may ship new British voices for Edge TTS. Neural TTS quality keeps improving. Easy to swap the voice ID in `mouth.py`.

These are not bugs in the design. They're future-me's prompts for paying attention.

---

## 11. References

- [opencode CLI docs](https://opencode.ai/docs/cli/) — `run`, `serve`, `session` commands
- [opencode server docs](https://opencode.ai/docs/server/) — HTTP API: `/session`, `/session/:id/message`, `/event`, `/session/:id/abort`
- [opencode SDK docs](https://opencode.ai/docs/sdk/) — typed event shapes
- [openWakeWord](https://github.com/dscripka/openWakeWord) — wake word detection
- [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — Apple Silicon STT
- [edge-tts](https://github.com/rany2/edge-tts) — Python wrapper for Microsoft Edge free neural TTS

---

*Written during the planning phase, Day 0. The design in PRD.md and ARCHITECTURE.md flows from the motivations in this document; if any of those change, those docs need to be revisited.*
