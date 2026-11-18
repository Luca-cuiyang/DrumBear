# Drum transcription regressions and normalization rules

These cases come from user visual review of `推进式飞机.png`. They are
mandatory checks for every future image/PDF -> DB Score conversion.

The eight approved scores in
`/Users/luca/Desktop/DB Score-鼓谱成品-20261117/` are the current golden sample
set. Their event timeline digests are recorded in `STANDARD_SAMPLE_INDEX.json`
and can be checked with `verify_standard_samples.py`.

## M6, beat 2

- The bass-drum attack is the last 16th note of beat 2 (`7/16`).
- It must remain to the right of the upper voice's `3/8` cymbal.
- A dotted rest before it must retain its augmentation dot. Otherwise DB Score
  reads the rest as an eighth rest and shifts the kick left onto `3/8`.

## M12, beat 4

- The final upper-voice eighth-note pair is `3/4` and `7/8`.
- Audiveris' second pair can arrive on a 32nd-note grid. Adjacent equal-value
  beam groups must be rebuilt from one cumulative rhythm.

## M24, beats 2 and 3

- The bass-drum attack at `7/16` is a single 16th note.
- It must not be aligned with the upper voice's `3/8` cymbal.
- The following bass-drum attack at `5/8` is the second half of beat 3 and is
  a single eighth note.
- A nearby eighth-rest hook must not be attached to the preceding kick as
  augmentation dots.

## M35, beat 3

- The bass-drum attack at `5/8` is one eighth note.
- It must not be emitted as a 16th note followed by a 16th rest.
- Graphic beam recovery must not process a standalone flagged stem and change
  its note value.

## M38, beats 1 and 2

- Beat 1 opens with a quarter-note bass drum (together with the pedal hi-hat).
- The bass drum on the second half of beat 2 is an eighth note.
- Neither may be split into a shorter bass-drum value plus an artificial rest.
- An upper-voice beam must never be projected onto a lower-voice kick that
  happens to share the same horizontal position.

## M29-M31, first and second endings

- M29 has no ending bracket.
- M30 is first ending `1.` and carries the repeat end.
- M31 is second ending `2.`.
- Ending numbers restart for each repeat section. Similar x coordinates on
  different systems must not merge unrelated ending groups.
- A one-pixel overlap with the previous measure's right barline is a boundary
  artifact and must not include that measure in the ending.

## Hi-hat symbols

- A small hollow circle above a hi-hat is Open Hi-Hat and must map to MIDI
  pitch 46.
- The circle is consumed as note identity; it must not also become a black
  staccato dot or an inverted-triangle staccatissimo mark.
- Orphan staccato/staccatissimo glyphs, including the false triangle in M55
  beat 3, must not be attached to drum notes.
- Articulations are matched within their own system. Matching by x alone can
  attach a symbol from a lower system to an unrelated measure with the same
  horizontal coordinate.

## Ride notation

- A hollow diamond-shaped cymbal head in the source drum notation means Ride.
- It must map to DB Score's Ride Cymbal (`MIDI 51`), not a normal cross-head
  cymbal.
- A filled diamond-shaped head means Ride Bell and must remain `MIDI 53`.
- Audiveris labels both hollow and filled diamonds as
  `NOTEHEAD_DIAMOND_FILLED`; the converter must inspect the source pixels to
  distinguish the hollow center from the filled center.
- This is a notation-system translation rule, not a rhythmic correction.
- Ride and Hi-Hat use the same onset and beaming rules. Changing the notehead
  from cross to diamond must not change the rhythmic stream or disconnect
  eighth notes that are beamed in the source.

## LATIN reviewed measures

- M10: the upper voice returns to the eighth-note pulse from beat 2. Upper and
  lower voices may legitimately share a beat even when their notehead x
  positions differ.  The final bass-drum attack after the `3/4` rest is
  `7/8`, not `3/4`.
- M33-M34: full-width staff/system lines must not be grouped as beams.
- M59 onward: Ride diamonds use the same eighth-note pulse and beaming as
  Hi-Hat. Ride templates must inherit the nearby chord stem and must not
  create isolated flags.
- M62/M65: a black tom head and hollow Ride diamond sharing a stem are one
  onset/chord even when their notehead centres differ by more than the normal
  x tolerance.
- M82, M110, M113: mixed upper-voice phrases are checked against the source;
  simultaneous upper and lower attacks are not duplicate events.

## Rock reviewed measures

- M16: Ride uses a continuous eighth-note pulse with upper-voice beam pairs;
  the bass drum remains in the lower voice.
- M15: the crash and following Ride are successive upper-voice eighth notes
  and must share the same beam.
- M22: the bass drum is a four-note off-beat pulse at
  `1/8, 3/8, 5/8, 7/8`.  Audiveris' partial slots must not turn it into
  `1/8, 5/16, 1/2, 3/4`.
- M29-M31: both voices begin with two eighths.  An eighth rest occupies
  `1/4`; the next attacks must resume at `3/8` and `1/2`, and the final
  crash/snare hit is at `3/4`.  The sequence must never be compressed into
  `1/4, 3/8, 5/8`.
- M33-M36 beat 2: after a 16th rest, the bass drum is the second 16th
  (`beat + 1/16`) and uses a dotted-eighth duration through the rest of the
  beat.
- M33-M36 beat 3: a dotted-eighth rest is followed by the last 16th of the
  beat (`beat + 3/16`); the bass drum itself is a 16th note.
- M34 beat 2: the upper snare/hi-hat attack is at `1/4`, not `3/16`.
  Audiveris can time the upper chord one 16th before the lower-voice rest even
  though both glyphs share the same printed x position.  An upper attack and
  a sparse lower-pattern rest at the same x must use the rest's beat position.
- Sparse lower-voice measures with only three anchor attacks must not be run
  through whole-voice pulse reconstruction.  Their rests and dotted values
  determine the timeline.
- The final system must fill the printable page width.  A short last system
  (Rock M40-M41) is a layout error even when all notes are correct.

## 摇滚派对 reviewed measures

- System-start measures M25, M29 and M30 use the printed first attack as the
  time-zero origin.  They must not inherit a 1/16 offset from the clef area.
- A valid upper-voice eighth-note pulse is authoritative even when a lower
  voice contains a genuine odd 16th.  The lower voice must not be collapsed
  onto the upper voice's beat boundary.
- Isolated Audiveris values such as `51/64`, `25/32`, `19/32` and slots outside
  a 4/4 bar are recognition noise.  They are resolved from surrounding note
  geometry and must never be emitted into the score.
- Rock M22 and similar evenly spaced off-beat kick pulses remain eligible for
  voice-pulse recovery.  Exact slot support protects irregular 16th attacks,
  not a regular sequence of off-beat kicks.
- M32-M37 carry both ties inside a bar and ties across bar/system boundaries.
  Source curves in this drum-score family belong only to Hi-Hat and Ride
  strokes.  A tie may connect two occurrences of the same HH/Ride pitch.
  Curves whose endpoints include Bass Drum, Snare or Toms are OMR artifacts
  and are discarded without changing either stroke.  Cross-system segments
  are joined through their `left-extension`/`right-extension` IDs before
  either endpoint is resolved.
- M32 to M33, M34 beat 3, M34 to M35, and M36 to M37 each contain real Ride
  ties.  M34 has no Bass Drum curve: its kick attacks at `3/8` and `1/2`
  remain separate notes.  M36's apparent curves through the lower voice are
  also discarded; the only remaining M36 curve is the real Ride tie into M37.
- DB Score 5.0.7 stores a tie on the ending `Note` as
  `Tie/startElement,endElement,eid,track`.  Phrase slurs are score-level
  `SpannerMap/Slur` entries.  The obsolete inline `Spanner type="Tie"` form is
  silently discarded by DB Score on save and is forbidden.
- M34 beats 3 and 4 keep their two independent voices.  The Ride tie ends at
  `1/2`; the Bass Drum is the second half of beat 3 at `5/8`.  Beat 4 begins
  with a Snare sixteenth at `3/4`, followed by a beamed Snare/Crash and Bass
  Drum attack at `13/16`.  The Snare and Crash are one upper-voice beam group;
  the Bass Drum remains in the lower voice without a curve.
- M36 has a mixed beamed group at `1/4, 5/16, 3/8`.  Its drawn durations are
  two 16ths followed by an eighth.  A whole-bar horizontal pass may only fix
  the group anchor; member onsets must still be rebuilt from those durations.
- M36's third and fourth beats place the last Bass Drum on beat 4 at `3/4`,
  followed by the final Snare/Crash chord at `7/8`.  The lower voice is a
  quarter rest at `1/2`, not a dotted-eighth rest followed by a premature
  kick at `11/16`.
- M68's beat-3 group is `16th, eighth, 16th` at
  `1/2, 9/16, 11/16`.  The following beat-4 group is `eighth, 16th, 16th` at
  `3/4, 7/8, 15/16`.  The latter ends on the closing barline, so its anchor is
  computed backwards from the bar end.  Per-note horizontal snapping must not
  shift either group member one sixteenth late.
- A half rest is a beat-level anchor, not an arbitrary slot label.  In
  M68 it and the upper Tom share the beat-3 column at `1/2`; Audiveris' `5/8`
  label on that rest is invalid.
- M71 has a quarter rest on beat 3 and an upper Snare/Ride chord on beat 4.
  When OMR places that chord at `11/16`, the complete rest wins and the chord
  moves to `3/4`.  The lower quarter rest sharing the beat-4 column also moves
  to `3/4`; it must not be emitted as a second overlay rest.
- Avoid generic "coincident rest" rewriting based only on x.  Coincident-rest
  normalization is restricted to an event previously anchored by a complete
  rest; otherwise valid sparse lower-voice rests in M13/M25/M29 can move
  backward without evidence.
- M43 beat 2 contains four consecutive sixteenth-note attacks; the fourth is
  the Bass Drum at `7/16`.  Its upper-voice sixteenth rest may be hidden.
- M43 beats 3 and 4 must have the same structure as M52: the Snare is on the
  beat (`1/2` and `3/4`), a sixteenth rest follows in the lower voice, and a
  dotted-eighth Crash+Bass Drum chord starts at `9/16` and `13/16`.
  Merge/split decisions must preserve that repeated two-beat figure rather
  than letting beam or coincident-event normalization move the Snare onto the
  dotted chord.
- M50 contains no curve.  Its OMR curve is rejected as a false positive even
  though both nominal endpoints are cymbal-compatible.
- Curve endpoints are filtered before tie/slur classification.  The allowed
  drum set is closed/open/pedal Hi-Hat plus Ride and Ride Bell.  No curve is
  emitted for Bass Drum, Snare, Toms or Crash.  This rule applies to image and
  MIDI-derived scores alike; curve removal never changes note onset, duration
  or voice.

## LATIN M58, M63, M66-M67 and M82

- M58 beat 4: the source has a slashed single grace note before the snare.
  It must survive as an `acciaccatura` attached to the `3/4` attack.  Grace
  chords occupy zero rhythmic time.
- M63 beat 4: both hollow-diamond Ride attacks are present.  The first is
  printed close to the floor tom and can score below the normal Ride template
  threshold.  A lower-confidence diamond is accepted only when it sits
  directly above an already recognized upper-voice drum head.
- M66 beat 3: the grace note before the high tom and the preceding Ride are
  both eighth-note attacks in the same upper voice; they must share one beam.
- M67 beat 4: both upper-voice eighth notes, including their simultaneous
  Ride heads, must share one beam group.
- M82 beat 4: the snare/floor-tom attack is at `3/4` and the bass-drum attack
  is at `7/8`.  A cross-voice horizontal displacement of about half a beat
  must not be collapsed into one onset at `3/4`.  The earlier upper-voice
  chord keeps its source duration.
- M78 beat 4: the snare/crash chord is a quarter note at `3/4`; the bass drum
  remains on `7/8`.  Moving the lower voice to `7/8` must not shorten the
  upper-voice chord into an eighth plus an artificial rest.

## LATIN M65 and M69

- M65 is a continuous eighth-note Ride pulse at
  `0, 1/8, 1/4, 3/8, 1/2, 5/8, 3/4, 7/8`.  Audiveris supplies the same
  printed sequence one 16th late.  The regular-pulse normalizer must accept
  small engraving-spacing variation and integer multiples of the eighth-note
  unit caused by a rest, while still refusing to flatten genuine mixed
  sixteenth-note figures.
- M69 has the same eight-note pulse.  A closed eighth-rest contour was falsely
  classified as the tuplet digit `3` (grade `0.565`, context grade `0.766`),
  producing `5/24` and `7/24` onsets.  Tuplets below the reviewed confidence
  floor (`grade >= 0.70`, context grade `>= 0.85`) are rejected.

## LATIN M77 and M105

- Both measures begin a system.  A fixed 110px system-header offset shifted
  every attack one 16th early (`1/16, 3/16, ...` instead of
  `0, 1/8, ...` for M77).  The retiming grid must compare every plausible
  time-zero origin against the complete bar rather than assuming one fixed
  clef width.
- M77 is a continuous upper-voice eighth pulse.  Engraved note spacing varies
  enough that one valid eighth gap measures `0.681` of the nominal width; the
  regular-pulse gate therefore allows a `0.35` spacing tolerance while the
  mixed-parity guard still protects genuine sixteenth-note figures.
- M105 attacks align directly with OMR slots at
  `0, 1/4, 3/8, 1/2, 5/8, 3/4, 7/8`.  When every notehead is confidently
  close to a unique, increasing slot, those exact slots take precedence over
  a reconstructed uniform grid.

## Per-measure release gate

Every reviewed score now has a contract in `standard_contracts/<title>.json`.
Each measure has its own digest covering meter, structural markers, every
onset, instrument, voice, duration, dot count, beam relationship, grace note,
articulation and explicit rest.  `run_pipeline.py` refuses to build or publish
when a locked measure changes, even if the total note count and page count
still match.  Temporary x coordinates, review metadata and internal beam IDs
are deliberately excluded because they are not musical facts.

The release sequence is therefore:

1. Compare the generated score measure by measure with the source image.
2. Correct the general rule and add a focused regression test.
3. Regenerate the complete score, not only the failing measure.
4. Require every locked measure digest to match.
5. Require native DB structural validation, semantic round-trip diagnostics,
   source/output page count and side-by-side visual proof.

## Current rhythm engine

The reviewed converter uses one deterministic arbitration order for every
measure.  This order is implemented by `normalize_measure_rhythm()` and is
recorded in the event map as `rhythm_audit`:

1. Separate different voices incorrectly merged onto one onset.
2. Restore a regular upper-voice pulse when the complete notehead sequence
   supports it.
3. Rebuild durations from printed beam groups.
4. Rebuild beamed groups again after horizontal anchoring and after
   voice-pulse recovery; the final beam pass is authoritative.
5. Use an explicit tuplet or a confidence-checked bar-wide grid only as the
   fallback.
6. Reconcile continuous voice pulses, explicit rests, sparse lower-voice
   16ths, long-rest boundaries, and same-position cross-voice symbols.
7. Hide only reviewed rests explicitly marked as omitted in the source.

The four reviewed core development samples are 推进式飞机, LATIN, Rock and
摇滚派对.  A code change is not release-ready unless complete extraction and
native DB rendering of all four reproduce every locked measure contract.

The following obsolete or redundant code has been removed:

- unused `requires_two_voices()`;
- an unused voice-direction counter in `build_mscx` construction;
- unused `replace_style()` in the MIDI converter.
- unused `PITCH_NAMES`, imports and drawing placeholder variables;
- the obsolete open-hi-hat template parameter and its unused PNG asset;
- empty `corrections: {}` records from approved manifests;
- four duplicated implementations of MSCX voice timing, replaced by one
  `read_voice_timing()` implementation shared by duration, event, grace-note
  and rest validators.
- duplicated duration/event/score validators in the pipeline, replaced by the
  single implementations in `score_validation.py`;
- the unused `run_pipeline.parse_lengths()` compatibility wrapper and stale
  builder imports that belonged to those duplicate validators.

Production files are also checked for song-name or measure-number branches.
Rhythm fixes must be expressed as geometric, notational or confidence rules,
never as `if measure == 77` style special cases.

## Rhythm and notation rules

- The image/PDF input must contain a percussion clef and drum notation only.
- Measure and system boundaries come from the source image. Coordinates from
  different systems must never be matched against each other by x alone.
- Every attack is represented on the whole-note fraction timeline. A lower
  voice 16th note may be at `7/16` while an upper voice cymbal is at `3/8`;
  these must remain separate time positions.
- Confirmed tuplet onsets such as `5/24`, `7/24`, and `23/48` are protected
  from ordinary eighth-note beam normalization.
- Adjacent equal-value beam groups are reconstructed as one continuous
  cumulative rhythm. This prevents a final eighth-note group from drifting to
  32nd-note positions.
- A standalone flag glyph determines the note value:
  `FLAG_1_*` = eighth, `FLAG_2_*` = 16th, and higher flags continue the
  subdivision sequence.
- Graphic beam recovery is limited to beamed stems on the correct side of the
  notehead. It must never turn an eighth-note kick into a 16th note plus rest.
- A confirmed bass drum cannot be shortened merely to make room for a rest.
  A rest cannot begin before the preceding sustained drum note ends.
- Audiveris may report internally valid slots while silently omitting a rest
  between them.  Each voice's notehead-centre x positions must also be checked
  for a regular pulse.  If every adjacent gap is an integer multiple of a half
  beat, rebuild that voice from its first confirmed onset.  This recovers both
  omitted-rest gaps (Rock M29-M31) and repeated off-beat lower-voice pulses
  (Rock M22; LATIN M10, M66, M78, M90, M110).
- The voice-pulse correction must reject irregular phrases whose gaps do not
  fit the half-beat grid.  This prevents grace-note and deliberately
  syncopated figures from being flattened.
- Small filled noteheads are grace notes, not ordinary attacks.  Detect one
  or more small heads immediately before their main notehead, preserve their
  source order, and emit each as an `acciaccatura` chord with zero timeline
  duration.
- Two upper-voice eighth notes in the same beat must share one beam group even
  when one of them is a tom and the other is a Ride/hi-hat.
- A low-confidence hollow Ride diamond may be recovered only when it is
  vertically adjacent to an already recognized upper-voice drum head; this
  prevents arbitrary page marks from becoming Ride notes.
- Sparse lower-voice sixteenth patterns must preserve their written values:
  `16th rest + bass at beat+1/16 + dotted eighth` and
  `dotted eighth rest + bass at beat+3/16 + 16th`.
- A dotted rest or note must retain its full duration. Rest hooks adjacent to
  a note are not augmentation dots.
- Bass drum and pedal hi-hat share the lower voice; snare, toms, and cymbals
  share the upper voice. A simultaneous snare/cymbal hit is one upper-voice
  chord.
- Upper-voice stems/beams point up and lower-voice bass-drum stems point down.

## Repeat and ending rules

- Repeat starts/ends and their repeat counts must survive round-trip into the
  final `.db`.
- First/second endings are numbered independently inside each repeat section.
- Ending bounds touching the previous measure by only a few pixels are treated
  as a boundary artifact, not as belonging to that previous measure.
- M29-M31 and M55-M57 are the canonical examples: M29/M55 have no ending,
  M30/M56 are first endings, and M31/M57 are second endings.

## Cymbal notation rules

- A small hollow circle above a hi-hat means Open Hi-Hat (`MIDI 46`).
- The circle is consumed as note identity and must not generate a black
  staccato dot or an inverted-triangle staccatissimo mark.
- Orphan `STACCATO` and `STACCATISSIMO` glyphs are dropped for this drum
  workflow. They are not rendered into the final score.
- Articulations are matched within their own system, never across systems by
  x-coordinate alone.
- Hollow diamond = Ride (`MIDI 51`); filled diamond = Ride Bell (`MIDI 53`).

## Hard validation gates

- MSCX `dots` must precede `durationType` inside `Chord` and `Rest`.
- The generated MSCX must contain no staccato/staccatissimo articulations.
- Open Hi-Hat circles must be resolved before articulation rendering.
- Hollow/filled diamonds must resolve to Ride/Ride Bell before score build.
- Hi-Hat and Ride must use the same onset and beam-group normalization.
- Freely positioned bass-drum 16th notes must never be snapped to the
  upper-voice cymbal eighth-note grid.
- Event timelines are read back from the generated score and must exactly
  match the reviewed source event map.
- Measure durations, rest ownership, repeat spans, page count, measure count,
  time signatures, and native-score semantics are checked independently.
- A failed invariant blocks the quality certificate, final copy, and release.
