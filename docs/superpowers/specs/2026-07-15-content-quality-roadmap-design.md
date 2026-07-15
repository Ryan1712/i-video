# Content quality roadmap

**Date:** 2026-07-15
**Status:** Approved (roadmap-level; each item gets its own design when picked up)

## Context

After rebuilding EP1 (`docs/superpowers/plans/2026-07-14-episode-render-quality-fix.md` — catalog filtering, caption legibility, new English voice), the user reviewed `output_en_v3.mp4` and found the result clearly improved, but flagged six further quality gaps versus a genuinely engaging zombie-story video:

1. Images aren't realistic enough.
2. No character consistency across scenes (same character looks different from cut to cut).
3. Narration reads like a textbook, not dramatic storytelling.
4. Word choice/phrasing isn't natural.
5. Voice delivery may not be able to carry tension (or might need a real voice actor).
6. No sound at all besides narration — no music, no sound effects. ("Phim zombie mà không có âm thanh thì đúng là cùi bắp.")

This spec is the roadmap tying these six gaps together into an ordered plan. It does not design each item in technical depth — each phase gets its own brainstorm/design/implementation-plan cycle when its turn comes, the same pattern already used for `2026-07-10-product-vision-v3-design.md` → per-feature plans.

## Decisions

- **Depth:** roadmap-level only (item list + difficulty + order + rationale), not a full technical spec for every item.
- **Priority order:** easiest/cheapest first, hardest last — get visible wins fast, defer open-ended technical risk (character consistency, scene-level SFX) to when there's time to prototype properly.
- **Audio sourcing (music + SFX):** undecided by the user — this roadmap's job is to propose a direction (see Phase 1 item 1 and Phase 3 item 5), to be confirmed when that phase starts.

## Roadmap

### Phase 1 — Quick wins on existing hooks

**1. Whole-episode background music**
`agent_video/video_builder.py::build_episode` already mixes a `music.mp3` under narration via ffmpeg `amix` if the file is present in `video_dir` (config: `config["audio"]["music_volume"]`) — this path is untested/unused because no build has ever supplied a music file. No code change needed to turn it on, only a source track.
Sourcing is open (see Open Questions) — leading candidate is generating an ambient/tense track via ElevenLabs' music API (already the TTS vendor, one integration to maintain) rather than curating a royalty-free library by hand.

**2. More dramatic voice delivery**
`agent_video/tts.py`'s ElevenLabs call hardcodes `voice_settings={"stability": 0.5, "similarity_boost": 0.75}` and never sets `style` (ElevenLabs' 0–1 expressiveness/exaggeration knob). Try raising `style` and re-listening to a few scenes before deciding whether AI delivery is "dramatic enough" or a real voice actor is genuinely required for this channel. This item directly answers the user's question ("liệu giọng AI có làm được không") — the answer should come from an actual before/after listening test, not from the roadmap.

### Phase 2 — Prompt engineering, no architecture change

**3. Narrative script style (less textbook, more storytelling)**
The script-writing prompt in `saas/ai/` (`generate_script` / the narration side of `script_analysis.py`) needs rewriting toward tension-building, sensory, second-person-adjacent horror narration — likely via few-shot examples of the target voice — instead of the current expository/report-like tone. Covers both gaps #3 (storytelling) and #4 (natural word choice) from the user's feedback, since both come from the same prompt.

**4. More realistic images**
Extend the image style bible / prompt (already touched by the punch-list #3 composition-hint fix) to push toward photorealism instead of the current flat-illustration look, while keeping the existing "keep subject centered" composition guidance from that earlier fix.

### Phase 3 — Needs its own investigation/design before building

**5. Scene-level sound effects**
Requires new infrastructure, not a tweak: an SFX catalog (parallel to the existing background-asset catalog), an AI tagging step so `analyze_script` (or a sibling step) marks which scenes need which cue, and extending `video_builder.py`'s ffmpeg filter graph to layer timed clips into a scene's audio instead of only one continuous whole-track mix. Proposed sourcing direction: generate SFX on demand via ElevenLabs' Sound Effects API (text-to-SFX), consistent with the project's existing generate-on-demand approach for images, rather than curating a fixed clip library. This needs its own brainstorm before implementation — do not start coding from this bullet alone.

**6. Character consistency across scenes**
The hardest item. `saas/ai/image_provider.py`'s `GptImageProvider` only calls OpenAI's `/v1/images/generations` (pure text-to-image, no reference image input). OpenAI's `/v1/images/edits` endpoint accepts input images and could plausibly be used to feed a stored "character reference" image alongside each scene's prompt to hold the same face/outfit across cuts — but this is unverified. Before committing to building a character-sheet subsystem (storage, `ImageProvider` interface change, catalog changes for which character(s) appear in which scene), run a small spike: a handful of manual `/v1/images/edits` calls with a fixed reference image and different scene prompts, and judge whether consistency actually holds up. If the spike fails, this item needs a different technical approach (e.g. a different image provider) before a real design is possible.

## Out of scope for this roadmap

- Applying any of the above to the Vietnamese track. Product vision v3 calls for VN + EN, but this roadmap was scoped against the English EP1 rebuild just completed; each phase should note when it's ready to extend to VN (script style and voice tuning are very likely to need separate tuning per language — Vietnamese narration doesn't take the same prompt or voice provider as English).
- Detailed technical design for any Phase 2/3 item — deferred to that item's own brainstorm.
- A firm decision on music/SFX sourcing — deferred to Phase 1 item 1 / Phase 3 item 5 respectively.

## Open Questions

- Music/SFX sourcing: AI-generated (ElevenLabs) vs. a royalty-free library vs. something else — needs a short research pass when Phase 1 item 1 / Phase 3 item 5 start.
- Whether ElevenLabs' `style` parameter alone is enough for dramatic delivery, or a different provider/voice is needed — resolved empirically in Phase 1 item 2.
- Whether `/v1/images/edits` genuinely holds character identity across generations — resolved by the Phase 3 item 6 spike.
