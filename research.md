# research.md — lessons from the old engine

Build-time source for the PRD, `styles/`, and the StyleDirector prompt (ticket 004). Closed after the PRD; never injected into a planner at runtime.

## Provenance and tags

- Source: `vg-short_source_2026-09-08.zip`, SHA-256 `28322b6ddb694209f4813255fbf25de733a4e8ce4922a5a5260b6986963aba04`, 12 parts joined, extracted 18 Sep 2026. Nothing in it was executed.
- Write-date reads, 18 Sep 2026, one scoped copy-only sub-agent each: A presenter/beats/B-roll, B captions, C sound, D ASR, E QA, F render/cost.
- VERBATIM = text a read copied. RECONSTRUCTED = my paraphrase or arithmetic. LOST = artefact that existed and is absent. ESTIMATE = the archive itself calls it an estimate. NOT RECORDED = never captured.
- Scope: GLOBAL = applies to every style. STYLE:explainer = an editorial choice that belongs in `styles/explainer.md` only.
- Parked full copies (git-ignored): `work/beat-tables.md`, `work/asr-fixmap.json`, `work/qa-commands.md`. Computed statistics cite them.

## 1. What the archive was

- Two accepted jobs: Neem Karoli Baba (NKB, 60.0 s, 26 beats, v1 to v4) and Dyson toothbrush (57.5 s, 22 beats, v1 to v2). Owner on NKB v1: "perfectly done … completely satisfied and impressed"; on Dyson v1: "Perfect video" [VERBATIM]. Every revision was sound or PIP framing; the picture plan of each job never changed after v1.
- One hand-coded house style in Remotion 4.0.522 with React [VERBATIM]. Plus ffmpeg for cut, voice stem, mix and encode; plan hand-written by Claude in chat as a TypeScript file; no LLM planner API, no prompt-to-style mapping, no asset cache, no per-job cost log [RECONSTRUCTED]. Both jobs map to `explainer`; the other three v1 styles have no archive evidence.
- The engine ran inside a Claude cloud sandbox with no open internet, so every external call went through n8n bridges (ASR, web scrape, asset download, AI image, Drive chunk relay) [RECONSTRUCTED from the bridges guide].
- Pre-NKB rejection of the August system: "a slideshow", "no editorial thinking" [VERBATIM]. That is the bar the house style was built to clear.
- Branches with no evidence: style mapping, planner call design and schema, asset caching, jobs/product layer (statuses, passcode, retention), test fixtures. Each is a fresh PRD decision.
- Open items for the PRD grilling, not resolved here:
  1. `styles/educational.md` draft says a bed 14 dB under voice plus a soft tick on step changes. That is within 1 dB of the NKB profile in the leave-behind list, and ticks are on explainer's forbidden list.
  2. The brief's ₹50 cap is cash-only. The archive's unexecuted plan projected ₹60 to ₹120 per short including tokens on a subscription. On a shared deployment with `PLANNER=api`, the cap needs a definition.
  3. Hit placement. The brief's settled rule says short bass hits only on reveals. The archive's accepted Dyson v2 profile (section 5) put a bass hit on stamps, reveals and headers, and the channel's thump on card fly-ins. The PRD decides which placement the sound ticket implements.

## 2. Presenter, PIP and beats

Geometry. Frame 1080x1920 at 30 fps [VERBATIM], GLOBAL. Construction rules are GLOBAL; the numbers that place things (diameter, anchor, offsets) are STYLE:explainer.
- PIP rule, GLOBAL: source window is the full master width, square, scaled down to the circle diameter, centred on a per-job face point measured once [RECONSTRUCTED]. PIP numbers, STYLE:explainer: circle diameter 300 px (27.8 % of width, RECONSTRUCTED), anchored left 70, top 960, so it occupies x 70 to 370, y 960 to 1260; scale 300/1080; face points NKB (540, 930), Dyson (540, 1000) [VERBATIM].
- Rule text: "The PIP circle shows the whole head including hair plus neck and collar — 'good view, not just face', never a tight close-up … If a new recording frames him differently, render one PIP still, measure, and set faceCy once for the job." [VERBATIM]. No numeric head-room margin exists; the check was a strip of 8 frames at 3.8, 6.5, 9.5, 17, 25, 36, 44, 53 s eyeballed at 3 to 4 candidate face centres [VERBATIM].
- Dyson landmarks on the master: eyes about y 960, chin 1360, hair top 500, collar 1500; engineer note "for more air next time: sit about 20 % further from the phone" [VERBATIM]. The pre-v3 tighter crop values are NOT RECORDED.
- Ring: 6 px white at 95 % plus 10 px dark halo and a drop shadow; spring enter (damping 14, stiffness 160, mass 0.7), scale 0.6 to 1 [VERBATIM]. Contiguous PIP beats merge into one continuous circle [VERBATIM]. STYLE:explainer for the ring look; GLOBAL for the merge rule.
- Full-frame punch-in: scale from 1.12 to 1.22 easing to 1.03 by 0.9 s then 1.0, origin 50 % 30 %, contrast 1.06, saturate 1.08 [VERBATIM]. STYLE:explainer.

Revision trail [VERBATIM wording, RECONSTRUCTED sequencing].
- NKB v1 to v2: sound only, "video stream md5 identical to v1". v3: owner "PIP must show the whole head incl. hair + neck/collar — 'good view, not just face'"; crop widened to the full 1080 window, full re-render about 40 min, pixel diff outside the circle ≤ 2/255 on sampled frames. v4: sound only, md5 identical to v3.
- Dyson v1: face centre set from a strip before delivery; owner had no PIP feedback. v2: sound only, md5 identical to v1.

Beat statistics, computed from `work/beat-tables.md` [RECONSTRUCTED]. STYLE:explainer.

| Job | Beats | Mean s | Min s | Max s | PIP | Full | Off | Longest same-mode run |
|---|---|---|---|---|---|---|---|---|
| NKB | 26 | 2.31 | 0.68 | 7.14 (list) | 61.5 % of beats, 63.5 % of time | 15.4 % / 12.4 % | 19.2 % / 21.0 % | PIP x6, 11.0 s |
| Dyson | 22 | 2.61 | 1.20 | 4.28 | 63.6 % / 63.7 % | 22.7 % / 19.2 % | 13.6 % / 17.0 % | PIP x6, 17.4 s |

- Both accepted shorts ran PIP for six consecutive beats. The explainer spec's "never more than about 2 consecutive beats in the same mode" is therefore stricter than anything the owner rated "perfect". The 2 to 6 s beat range holds for the median but not the extremes: the spec should say the mean, or allow set-piece beats longer than 6 s.
- Editorial standard for E3: presenter full-frame ≤ 25 % of runtime; E4: a visual event at least every 1.5 s [VERBATIM].

## 3. B-roll

Kinds actually used [VERBATIM names]: presenter full, hook (three cards plus title), full-bleed photo with Ken Burns, framed archival card with zoom-to-point and red ring, list, chart (SVG line), split, wall, finale (orbiting cards plus call to action), presenter cutout (one NKB beat, alpha matte). List, chart, split, wall appear only in NKB.

Motion primitives (GLOBAL renderer capabilities) [VERBATIM values]:
- Ken Burns: eased sine progress over the beat; scale s0 to s1 with pan x0 to x1, y0 to y1 in percent and an optional origin. Covers 1.10 to 1.16 ratio; archival zoom-to-point 1.45 to 2.1 (NKB), 1.65 to 1.9 (Dyson). Standard: "scale change 8 to 15 % over the beat; alternate zoom-in/zoom-out and pan directions".
- Red ring: 6 px `#FF2D2D`, glow, scale 2.2 to 1 over 0.35 s with a 5 % pulse, drawn inside the zoomed layer so it tracks the zoom. Radius 0.07 to 0.13 of image.
- Archival card: width min(980, 650 x aspect), top 200, white 14 px border, rotate −1.5°, blurred darkened cover behind, 30 px caption.
- Enter transitions: whip 0.22 s with 14 px blur, zoom 0.3 s from 1.6, fade 0.35 s. Stamp: scale 2.6 to 1 over 0.16 s with back-easing and a 0.25 s shake, 9 px border, 92 px type. Photo card: spring fly-in from 900 or 1200 px.
- Grade: contrast 1.05, saturate 1.12; black and white variant grayscale plus contrast 1.15; 7 % grain, vignette, watermark.

Kind-to-motion mapping and the grade values are STYLE:explainer. Cards sit above the caption line; stamps stay in the top 60 % of the frame [VERBATIM].

Assets per short, counted from the plans [RECONSTRUCTED]:

| Job | User | Web (Wikimedia) | AI used / generated | Beats |
|---|---|---|---|---|
| NKB | 7 | 13 | 8 / 10 | 26 |
| Dyson | 7 press images | 2 | 5 / 6 | 22 |

- AI image prompts: LOST. "The prompt texts were not retained after context compaction" [VERBATIM]. Only the pattern survives: "<style> photograph, vertical 9:16: <scene>, <lighting>, <lens/film feel>, realistic, no text", with "seen from behind / no faces clearly visible" [VERBATIM]. Generator was Gemini 2.5 Flash Image at 9:16 [VERBATIM].
- Fallback when nothing relevant was found: none in the engine. Practice was to contact-sheet the downloads, reject "wrong person, watermark, tiny size, hot-link HTML", and draw logos in code [VERBATIM]. Spare Commons portraits were downloaded "as fallback" and never used.
- Rights were recorded as a filename suffix (`wm_<subject>_<licence>`, PD, cc0, ccby2 to ccbysa4, godl) with source URLs in a run log, a credits paragraph in the upload notes, and the AI disclosure "Some background scenes are AI-generated illustrations" [VERBATIM]. Owner images carried no tag.
- Owner feedback on B-roll relevance or hooks: NOT RECORDED. Relevance and hook scores in the job records are the engineer's self-assessment.

## 4. Captions

All values VERBATIM unless noted. Typography and animation are STYLE:explainer; the sync mechanism, safe-area constraint and language policy are GLOBAL.
- Font: Poppins for both Hindi and Latin (weights 500 to 900 loaded), rendered at 74 px, weight 800, line height 1.35, letter spacing 0.5 px for Latin tokens only. The checklist states "Poppins 74 px" as the contract.
- Colours: unspoken words white at 86 % opacity; spoken words `#fff`; the active word `#FFD60A` scaled 1.0 to 1.08 over 0.10 s; keywords, once spoken, `#111` on a `#FFD60A` box, 14 px side padding, radius 14, no shadow.
- Stroke: 2 px four-direction fake stroke plus a 3 px drop and an 18 px black glow. No line box.
- Grouping: pages are a hand-authored list of word-index ranges, 2 to 4 words "on phrase boundaries; never split a name across pages"; NKB used 47 pages over 176 words, Dyson 63 over 183. No automatic grouping existed; the validator only checks ranges are increasing.
- Emphasis: a hand-authored set of exact word strings plus an exclusion list by index. Rule: "names, numbers, the 'hidden truth' nouns and verbs, the final question word. Cap at about 1 in 4 words". NKB 39 keywords, Dyson 20.
- Placement: block absolute, left 60, right 60, bottom 460, so the text bottom sits at y 1460, centred, transform origin centre bottom. Avoidance of the PIP is by fixed geometry only: one line spans about y 1360 to 1460, two lines about 1260 to 1460, ending at the PIP's bottom edge [RECONSTRUCTED]. No safe-area constant for platform UI exists.
- Timing: a page appears at first-word start minus 0.04 s and ends at the earlier of last-word end plus 0.9 s or the next page's start; last page holds 1.2 s. A word counts as spoken at start minus 0.02 s and stays active until end plus 0.06 s. Page enter: scale 0.94 to 1 over 0.12 s with back-easing, opacity over 0.06 s. Captions hide before the finale word (NKB 58.85 s, Dyson 55.2 s).
- Word sync: words come from a per-job JSON of `{word, start, end}` in seconds built from the ASR output; the component compares frame/fps against those seconds with no frame quantisation. Two correction layers exist: a spelling map that changes displayed text only, and a hand-edited copy of the ASR file that changes onsets (see section 6).
- Language: same font, size and weight for Devanagari and Latin; English loanwords shown in Latin script ("Facebook", "success"), Hindi with correct nukta and matra; verbatim words with trailing punctuation stripped; mis-spoken spans cut from both audio and words.
- Owner feedback on captions: NOT RECORDED beyond "perfect".

## 5. Sound chain

GLOBAL throughout. The chain that the brief adopted is the Dyson v2 one.

Voice stem, both jobs [VERBATIM]:
```
pan=mono|c0=0.5*c0+0.5*c1,highpass=f=80,acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120,loudnorm=I=-19:TP=-3:LRA=11:measured_I=…:measured_TP=…:measured_LRA=…:measured_thresh=…:offset=…:linear=true
```
Two-pass; the measured values come from a first `loudnorm … print_format=json` pass. Lesson: passing `-ac 1` as an output option instead of in the graph landed the stem 3.6 dB low [VERBATIM].

Dyson v2 mixer, one ffmpeg graph, placeholders in braces [VERBATIM, per-cue and no-SFX branches elided]:
```
[0:a]aformat=channel_layouts=stereo,aresample=48000,volume=1.0,asplit=3[voice][v2][vstem]
[1:a]aformat=channel_layouts=stereo,aresample=48000,atrim=0:{TOTAL},asetpts=PTS-STARTPTS,volume={music_gain}dB,volume={pre_gain}dB:enable='lt(t,{pre_until})',afade=t=in:st=0:d=0.6,afade=t=out:st={TOTAL-1.2}:d=1.2[mus0]
[mus0][v2]sidechaincompress=threshold=0.06:ratio=2.0:attack=20:release=400:makeup=1:level_sc=1.0,asplit=2[mus][mstem]
[{idx}:a]aformat=channel_layouts=stereo,aresample=48000,volume={gain_db}dB,adelay={ms}|{ms}[s{i}]
[s0]…amix=inputs={n}:normalize=0:dropout_transition=0,asplit=2[sfx][sstem]
[voice][mus][sfx]amix=inputs=3:normalize=0:dropout_transition=0,alimiter=limit=0.95:attack=5:release=50[mix]
```
Then a second pass, two-pass with measured values: `loudnorm=I=-14:TP=-1.5:LRA=11:…:linear=true,alimiter=limit=0.891:attack=3:release=60:level=false` [VERBATIM]. Stems for voice, music and SFX are written alongside the mix so balance can be measured.

Numbers:
- Bed: v2 target −11 dB versus voice RMS while speaking, setting −12.5 dB with a +3 dB lift until the first drop at 5.2 s; measured −10.4 dB with 2.6 dB of ducking; acceptance band music −9 to −12 dB, ducking ≤ 4 dB, speech band 250 Hz to 4 kHz at least +20 dB above the bed [VERBATIM].
- Hits (v2 fact profile): a short bass hit about 5 dB under voice on stamps, reveals and headers; a hard drum hit 2 to 3 dB under on the money reveal and finale word; the channel's own thump 8 to 10 dB under on card fly-ins; "Nothing on whip cuts, punch-ins, rings or lower thirds" [VERBATIM]. The two Mixkit hit files themselves are LOST from the archive.
- Master: −14 LUFS, TP −1.5 dBTP, delivered at −14.0 / −1.6 (v2) and −14.4 / −2.1 (NKB), both recorded as PASS; the true-peak figure functioned as a ceiling [RECONSTRUCTED].
- Fades: music in 0.6 s, out 1.2 s [VERBATIM].
- Measurement method [RECONSTRUCTED from the balance script]: 10 ms RMS frames on the stems; "speech" frames are where voice RMS exceeds 6 % of its 95th percentile; report music level under speech versus in gaps (the difference is the ducking), music-to-voice offset, and each cue's 250 ms RMS relative to voice.
- Ban text: "No noise-sweep cues. Nothing with a rising or falling envelope of broadband noise: whooshes, swishes, swooshes, 'air' transitions, risers, helicopter/riser builds, rumble crescendos, low-rumble hums, reverse cymbals" [VERBATIM]. Detector rules R1 to R4: sustained flatness > 0.03 for > 0.45 s; crescendo ≥ 200 ms rising ≥ 8 dB in ≤ 3 dB steps; bed-length > 5 s; slow attack > 150 ms from −20 dB to peak [VERBATIM]. The two detector scripts are LOST; only a reporting tool with no thresholds survives.
- Owner on Dyson v1: "the sound effects and background music give a very artificial feel, not a fact-based-channel feel … do not change the video editing … only the sound effects need to be updated" [VERBATIM]. v1 to v2: 45 cues to 16, every tick, pop, bell, chime and heartbeat removed, ducking ratio 6 to 2, bed raised about 15 dB, music re-chosen by spectrum match to two reference clips (minor key, static harmony, about 15 % percussive, no vocals) and offset so the drop lands on the first stamp [VERBATIM].
- Music and SFX came from Mixkit under its free licence, chosen by tag ("never by title") and a computed feature table; no mood-to-track mapper existed [RECONSTRUCTED].
- Rules document versus scripts: the written NKB rule said 15 dB under; the mixer default was −17.5 dB before ducking and the measured result −25.8 dB. The rules also require the two lost detectors and claim the template ships eight SFX files, while it ships 24 including all 13 banned ones. Treat the rules document as intent and the v2 scripts plus measurements as fact.

## 6. ASR rules

GLOBAL. Engine on both jobs: Groq `whisper-large-v3`, `verbose_json`, word and segment timestamps, `language=hi`, temperature 0, fed 16 kHz mono MP3 at 64 kbps [VERBATIM]. So every rule below was seen on the same engine the new transcriber uses.
- Tail dropout (NKB): Groq's word list ended at 49.28 s of 59.93 s. Check: if audio duration minus last-word end exceeds 1.5 s, re-run on a tail cut from floor(last_end − 3) s and merge with that offset, keeping main words that end before last_end and tail words that start at or after it [VERBATIM]. One document says 2 s instead of 3 s; the actual cut was 3.28 s before [RECONSTRUCTED]. Dyson passed the check (gap 0.57 s).
- Head smear (Dyson): first word started at 0.00 with 1.72 s of real silence, and the opening phrase was mis-heard. Check is manual: "if the first word's start is 0.00 although the recording begins with silence, or the first phrase reads oddly" [VERBATIM]. Fix was a second-opinion ASR (sherpa-onnx Omnilingual CTC) on the first 5 s, then hand-editing onsets in a copy of the ASR file, original untouched.
- Overlaps: after merge and fixes, if a word starts more than 0.05 s before the previous end, start is set to that end; if end ≤ start, end is start plus 0.12 s [VERBATIM].
- Hinglish drift: documented symptom "avg_logprob low, English words garbled", fix "force language=hi, temperature 0" [VERBATIM]; never automated, the log-probability field was never read by any script.
- Fix map: exact whole-token replacement on the displayed word after timing, before cuts; format `{"map": {wrong: right}, "only_before": [{word, next, else}]}`; 38 unique keys merged from both jobs plus one lookahead rule [VERBATIM]. Samples: `"डाइसन": "Dyson"`, `"दाथ": "दाँत"`, `"साफ": "साफ़"`. Content is Hindi-specific; the mechanism is not. Full copy at `work/asr-fixmap.json`.
- A local faster-whisper path was tried and never produced output (model download blocked) [VERBATIM].

## 7. QA gates and revision proofs

GLOBAL. Thresholds VERBATIM; commands VERBATIM where fenced, full set in `work/qa-commands.md`. Six checker scripts the checklist relies on are LOST (sfx check, sweep scan, luma scan, pixel-diff, spectrogram sheet, plan validator); their rules and thresholds survive.

| ID | Intent and threshold | Carried as |
|---|---|---|
| T1/T2 | H.264 yuv420p, AAC 48 kHz stereo, faststart; 1080x1920, 30 fps, frame count = round(dur x 30) | command below |
| T3 | ≤ 60.000 s; end card 0.8 to 1.2 s; beats contiguous within 0.011 s | description; validator LOST |
| T4 | −14.0 ± 0.5 LUFS, TP ≤ −1.5 dBTP on the delivered file | command below |
| T5 | captions on words at 3 random stills; lip sync lag 0 ± 1 frame by envelope cross-correlation | description |
| T6 | every SFX passes R1 to R4; sweep scan on the SFX stem passes | rules kept; scripts LOST |
| T7 | mean luma ≥ 12/255 every frame; no identical-frame run > 0.5 s before the end card | threshold; script LOST |
| T8 | plan validates; no NetworkError in the render log | description |
| T9 | rights: licence per asset, credits, AI disclosure, music licence | human |
| T10 | chat file ≤ 30 MiB, Drive file ≤ 20 MB | description |
| T11 | uploaded file's video-stream md5 equals local | proof (a) |
| T12 | provenance in the job record | human |
| E1–E10 | hook, relevance, variation (full-frame ≤ 25 %), density (event ≤ 1.5 s), captions, PIP head plus collar, sound, payoff, integrity, embarrassment; 1 to 10 each; "deliver only ≥ 8" | human, from contact sheet plus preview |

```
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,width,height,r_frame_rate -of compact=p=0 OUT.mp4
ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 OUT.mp4
ffmpeg -i OUT.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -E "I:|Peak:" | tail -2
```
Contact sheet: one frame per second scaled to 270 px wide, tiled six per row with time labels [VERBATIM description; script survives].

Revision proofs [VERBATIM]:
- (a) Sound-only revision leaves video untouched: `ffmpeg -v error -i FILE -map 0:v:0 -c copy -f md5 -` on old and new; the hashes must match. Precondition: the remux uses `-c:v copy`. Used on NKB v2, v4 and Dyson v2.
- (b) Region-confined change: mean absolute pixel difference ≤ 2/255 outside the changed region on sampled frames (3.8, 6.5, 9.5, 17, 25, 36, 44, 53 s), for example outside a circle at (220, 1110) radius 150. Script LOST; the original was PIL plus numpy over extracted frames.
- Mid-word cut check: none existed. Editorial cuts dropped whole words inside the cut span and shifted later words; nothing verified that a cut boundary avoided a word. The brief's "no cut lands mid-word" is a new check.
- PIP whole-head check: never automated; an 8-frame strip of the circle crops, judged by eye.
- "Done": "technical QC passing is not a publish recommendation"; both gates pass, every E line ≥ 8, then "a delivered cut is frozen" [VERBATIM]. Owner acceptance was a quoted message.

## 8. Render engine evidence (decision deferred to the prototype phone test)

- Remotion delivered [VERBATIM list]: word-synced kinetic captions with per-word state; the circular PIP mask, ring and spring; the alpha-matte cutout; animated set pieces (hook cards, list, chart, split, wall, finale); whip, zoom and fade transitions with blur; Ken Burns, framed card with ring, stamp, photo card, lower-third; grain, vignette and watermark; frame-accurate presenter decode; deterministic per-frame stills for QA. Stated reason: "kinetic typography, layered compositing, easing curves, masks and per-word animation are exactly what a browser layout engine does well and what FFmpeg filter graphs do badly" [VERBATIM]. Remotion rendered picture only, no audio.
- ffmpeg delivered [VERBATIM list]: master cut with word removal, rotation and frame-rate normalisation, voice stem, the full mix, `-c:v copy` mux (which makes proof (a) possible), two delivery encodes, all probes, luma scan, frame extraction, and the alpha-merge for the cutout.
- Render time, all on a 2 vCPU, about 7.2 GiB sandbox, no GPU, concurrency 2 [VERBATIM figures]:

| Figure | Context | Tag |
|---|---|---|
| 0.45 s/frame | feasibility test, trivial composition, 90 frames | VERBATIM |
| 1.2 s/frame, "35 to 40 min" | NKB full renders, read off Remotion's own progress estimate, not a clock | VERBATIM; the same log at frame 900 implies 1.47 s/frame [RECONSTRUCTED] |
| 1.5 s/frame, 43 min for 1725 frames | Dyson full render, the only wall-clock measurement | VERBATIM |
| 2.4 to 2.5 s/frame, "75 min per 60 s" | 6 s template test including about 20 s of bundling, presenter-heavy | VERBATIM |

- Why they differ, per the source: presenter video decode and seeks dominate; the trivial test had none, the template test had proportionally most. Concurrency 2 gave no speed-up over 1. Lesson: measure seconds per frame on the deployment box with a real plan before choosing.
- Deployment weight [VERBATIM]: Node 22, a headless Chromium (the Remotion download was blocked; a Playwright headless shell worked with a specific chrome-mode flag), software GL, about 390 to 680 MB of node modules, every render asset must be local because the render browser rejects HTTPS certificates in the sandbox. Peak RSS and Docker image size are NOT RECORDED. Remotion is free for teams of three or fewer; larger self-hosting needs a company licence [RECONSTRUCTED; verify at remotion.dev before share day].
- Other timings: 540p preview 12 to 15 min; background matte 26 min for 1774 frames; stills 4 to 8 s each; wall clock per short 2.5 to 3 h including bridge work [VERBATIM].

## 9. Cost

- Cash per short: NKB about ₹40 (10 Gemini images at ₹3.7, Groq Whisper about ₹0.2, Commons and Mixkit free, Drive ₹1 to 3); Dyson about ₹23 (6 images) [VERBATIM; the Drive line is ESTIMATE]. Upscaling was local OpenCV at no cost.
- Claude tokens: NOT RECORDED per job. NKB: "not measured for this job (the usage meter was not read before/after)"; Dyson: "usage meter: not read" [VERBATIM]. Every token figure is ESTIMATE, derived from a documentation session's own logs (573 turns in 1.6 h, about 59.5 M cache-read tokens) multiplied by an assumed 3 active hours per job.
- The split: "roughly 98 % of the Claude tokens a job burns are spent on Claude re-reading its own context while it acts as a shell operator … and less than 2 % on the judgement"; about 85 % of turns ran cp, ffprobe, md5sum, zip and ls [VERBATIM; ESTIMATE]. The judgement itself was put at 80 to 170 k input and 15 to 30 k output tokens per short [ESTIMATE].
- The 10 Sep cost-reduction plan projected ₹60 to ₹120 per short with a scripted pipeline calling Claude only at plan, picker, reviewer and editorial gate, versus ₹550 to ₹1,350 at the time [ESTIMATE]. It was never executed: no pipeline, state file or prompt directory exists in the archive.

## 10. Inherit list

Each item names its consumer. GLOBAL unless tagged.
1. Per job, the LLM produces the plan; code executes every render step. The LLM never drives ffmpeg or inspects renders per job. Evidence: the 98 % figure above. Consumer: PRD, ticket 004 adapters.
2. GLOBAL: PIP window is the full master width, square, scaled to the circle diameter, centred on a per-job face point measured once from a still. STYLE:explainer: 300 px circle at (70, 960). Consumer: renderer ticket, PIP QA check.
3. Sound chain as in section 5: two-pass loudnorm for stem (−19) and master (−14 / −1.5), sidechain threshold 0.06 ratio 2 attack 20 release 400, bed −9 to −12 dB with ducking ≤ 4 dB, fades 0.6 / 1.2. Hit placement is open item 3 in section 1. Consumer: sound ticket, T4.
4. Write voice, music and SFX stems on every mix and measure the balance from them; a mix without stems cannot be checked. Consumer: sound ticket.
5. Sweep detector rules R1 to R4 and the stem scan become a real, tested check; the archive's scripts are lost. Consumer: ticket 009.
6. ASR: tail-dropout check at 1.5 s with a 3 s tail re-run, head-smear check on a 0.00 first onset, overlap clamp at 0.05 / 0.12 s, fix maps per language as data files with tests, starting from `work/asr-fixmap.json` for Hindi. Consumer: transcriber ticket.
7. Store every image-generation prompt with the asset and its rights entry. Consumer: asset and rights-log tickets.
8. Capture the owner's rating and note per job; the archive never did, so no caption, B-roll or hook feedback exists. Consumer: editorial gate ticket.
9. Revision proofs (a) and (b) as commands in the QA suite. Consumer: ticket 009.
10. Add a mid-word cut check; none existed. Consumer: ticket 009.
11. Prototype must measure seconds per frame on the deployment box with a real plan before the engine is chosen; treat every archive timing as sandbox-specific. Consumer: render-engine prototype ticket.
12. GLOBAL: captions must clear the PIP by construction. STYLE:explainer: bottom anchor at y 1460 with two lines occupying at most y 1260 upward. Consumer: caption ticket 007.
13. Read the ASR log-probability per segment and flag low values; the archive documented the rule and never ran it. Consumer: transcriber ticket.
14. STYLE:explainer: caption typography (Poppins 74 px, weight 800, yellow active word, keyword box), page rule 2 to 4 words on phrase boundaries, emphasis cap 1 in 4, ring and card looks, grade values, hit vocabulary. Consumer: `styles/explainer.md`, ticket 004 prompt.
15. STYLE:explainer: reconcile the spec's beat rules with the measured 2.3 to 2.6 s mean, 0.7 to 7.1 s range, six-beat PIP runs, full-frame ≤ 25 %, event every 1.5 s. Consumer: PRD grilling on `styles/explainer.md`.

## 11. Leave behind

1. Heavy ducking profile (bed 15 dB under, ratio 6, 45 cues with ticks, pops, bells): owner called the result "very artificial". Replaced by inherit 3.
2. Claude as shell operator per job: 98 % of token cost. Replaced by inherit 1.
3. Plan hand-written in chat as a TypeScript file with hand-authored caption pages and keyword sets: not reproducible, no schema, no validation. Replaced by a planner behind an interface with a fake.
4. Licence encoded in the asset filename: not queryable, no source URL next to the file, owner images untagged. Replaced by the brief's per-asset rights log.
5. One house style hard-coded in Remotion components: no prompt-to-style mapping. Replaced by `styles/<name>.md`.
6. No asset cache and no per-job cost record: revisions re-fetched, tokens never measured. Replaced by per-job caching and cost accounting in the product layer.
7. n8n bridges for ASR, scraping, downloads, image generation and file relay: an external orchestrator dependency conflicts with a self-contained, shareable product. Replacement to be decided in the PRD.

## 12. Prototype findings (18 Sep 2026; laptop 8 cores, Node v24.19.0, ffmpeg 9.0.1, Remotion 4.0.526)
Measured in this repo, not archive claims; the five tags do not apply here. Inputs: work/sample.mp4 (1080x1920, 30 fps, 57 s), cut 20–50 s, PIP over a CC BY-SA still at output 10–20 s, section-4 captions, section-5 sound chain.
- Version A, ffmpeg (proto/ffmpeg_proto.py): 0.069 s/frame, 62 s wall for 900 frames, x264 medium CRF 18, 39.3 MB; one filter_complex (geq circle mask, zoompan 1.10→1.16 with explicit s= and fps=, libass captions via fontsdir); master −13.95 LUFS / −1.50 dBTP.
- Version B, Remotion (proto/remotion-captions/): 0.170 s/frame, 153 s wall at concurrency 4; toolchain 699 MB incl. 270 MB headless Chrome. First render failed on the phone clip's H.264 B-frame pyramid (OffthreadVideo "No frame found at position"); fixed with @remotion/media Video (WebCodecs). Audio muxed from A, byte-identical.
- ASS cannot express four section-4 items: line-height 1.35, page-enter scale 0.94→1, exact keyword rectangle (needs text measurement outside ASS), true 86 % unspoken opacity. Remotion does all four.
- Phone verdict, arm's length, same segment and audio: no visible difference on readability, keyword box, word spacing, line spacing, circle edge or still motion. The four ASS gaps are invisible at this size for explainer captions.
- Both used hard cuts into and out of the PIP; animated transitions untested. ffmpeg: per-frame expressions on overlay/scale. Remotion: one interpolate call.
- Presenter framing: hair top ≈300 to collar ≈1500 (1200 px) exceeds the 1080 px source square, so the GLOBAL "whole head + collar" rule cannot hold on close framing; collar was cut. PRD must set a priority (keep chin) and/or a recording guideline.
- Active-word scale 1.08 eats the inter-word gap on long words in both engines; the old engine's word gap is NOT RECORDED. Spec item for styles/explainer.md, not an engine point.
- Remotion tags full-range yuvj420p, ffmpeg limited-range yuv420p; pass --color-space bt709 if outputs must match.
- Verdict: Remotion for the visual layer (captions, PIP, stills, transitions); ffmpeg for cut, stems, mix and mux. Reason: parity on explainer today, and the animated/hitech styles and transitions are where ffmpeg's ceiling is. Constraint: plan JSON stays engine-agnostic so the renderer can be swapped. Accepted costs: 2.5× render time, ~1 GB toolchain, TypeScript in the renderer module, re-encode the cut clip before Remotion.
