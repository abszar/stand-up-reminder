# Design brief — "Stand Up Reminder", full 8-bit / pixel-art restyle

## What I need from you

Design a complete 8-bit, pixel-art visual identity — with animation — for an
existing Linux desktop application called **Stand Up Reminder**. Every surface
listed below needs a design. You have full freedom over palette, typography,
character design, layout and motion: nothing about the current look is fixed,
and you should feel free to throw all of it away. What matters is that the
result reads as a real handheld/arcade game HUD rather than as generic "retro"
clip art, and that it stays coherent across every screen.

The design will be implemented in GTK3 on Ubuntu GNOME, so read the
**Implementation constraints** and **Deliverables** sections carefully — a
design I cannot cut into pixel grids, hex values and frame timings is a design
I cannot build.

## What the application does

Stand Up Reminder is a native Ubuntu/GNOME desktop app that tells you to take a
standing break at the end of every work interval (30 minutes by default), and
keeps score of how well you keep those breaks.

The cycle it runs:

1. **Work** — a countdown runs invisibly; only a small top-bar indicator shows
   the time to the next break.
2. **Warning** — 15 seconds before the break, an always-on-top card appears
   counting down to it, offering the same actions as the break itself.
3. **Break** — the card takes over: a 2-minute countdown, an instruction to
   stand up and move, and the actions *snooze*, *skip*, and *I'm standing*.
   Other monitors are dimmed while it shows.
4. **Break complete** — the card waits for the user to confirm they came back,
   with *I'm back* and *I didn't take this break*.
5. Each break ends in one of five recorded outcomes — **taken, away, missed,
   skipped, snoozed** — which feed a day timeline, a daily and weekly
   adherence score, and a twelve-week contribution grid.

The user has a **standing desk**: a dedicated "standing mode" answers the break
by standing up instead of walking away, and puts a small floating pill on the
edge of the screen counting how long they have been on their feet.

Audience: one person, at their desk, all day. The break card interrupts their
work, so it has to be readable in a fraction of a second and pleasant to see
six to twelve times a day, every day. It should feel like a game rewarding you,
never like a nagging dialog.

## Surfaces to design

### 1. Break card — the main event
Always-on-top, undecorated window, currently 440×380 px, centred, not
resizable. Propose whatever size the design needs. It has three states:

**A. Warning (break coming up)**
- eyebrow / title: "Break coming up"
- large countdown, 15 → 0 seconds, currently reddening as it approaches
- secondary line: "Time to stand up in 00:15"
- progress bar draining
- prompt line: "Stand tall. Let your shoulders drop. Take a few steps."
- buttons: *snooze* ("Give me 5 minutes"), *skip* ("Skip this break")
- hint line: "S to snooze · K to skip"
- day timeline strip + score line (see below)

**B. Break running**
- title: "Time to stand up"
- large countdown from 02:00 to 00:00
- secondary line: "Away for 00:45" (counts up)
- progress bar draining
- prompt line, as above
- buttons: *snooze*, *skip*, and *I'm standing — keep counting*
- hint line: "S to snooze · K to skip · T if you're standing"
- timeline + score line

**C. Break complete**
- title: "Break complete"
- countdown reads 00:00
- secondary line: "Away for 02:10" (still counting up)
- buttons: *I'm back — start 30 minutes timer*, *I didn't take this break*,
  *I'm standing — keep counting*
- hint line: "Enter to confirm · T if you're standing"
- timeline + score line

Shared sub-elements on the card:
- **Day timeline**: a horizontal track spanning the worked part of today, with
  one small mark per recorded break, positioned by time of day and coloured by
  outcome (taken / away / missed / skipped / snoozed). Hidden until the first
  outcome of the day exists.
- **Score line**: small text, e.g. "Today: 80% · This week: 72%", with a mood
  glyph reflecting the score.

### 2. Standing pill — floating HUD chip
A small always-on-top widget pinned to the right edge of the screen, currently
about 150×38 px, dragged up and down the edge, that appears when the user
answers a break by standing. Contents: a standing/walking figure, a count-up
timer reading `00:00`, growing to `1:02:11` past an hour, and a control to stop
it when they sit down. It floats over other applications all day, so it must be
legible, small, and not annoying. It is the app's most visible ambient element:
give it real character.

### 3. Statistics window
Closable window, currently 600×700 px. Top to bottom:
- title "Statistics"
- caption "This week" and a large percentage score, e.g. "72%"
- a verdict line: one of "Excellent — you rarely miss a break", "Good — most
  breaks taken", "Could be better — many breaks slip by", "Time to stand up
  more often", "No breaks due yet"
- "Today: 80%"
- the day timeline (bigger than on the card), with the start and end hour
  labelled underneath ("09:12" … "18:40") and a colour legend: taken, away,
  missed, skipped, snoozed
- a **twelve-week contribution grid**: one column per week, one row per weekday,
  each day a square shaded by how well its breaks were kept (four levels plus
  an empty state), weekday labels down the left (Mon/Wed/Fri), month names
  along the top, and a "Less ▢▢▢▢ More" scale beneath. Hovering a day shows a
  tooltip with its counts.
- two summary lines: "Today: 3 breaks taken · 1 missed", "This week: 14 breaks
  taken · 2 missed · 1 skipped"
- a *Close* button

This is the app's score screen. It is the one place the design can be
celebratory and dense.

### 4. Top-bar indicator icon
A monochrome symbolic icon that sits in the GNOME top bar at 16 px (and 24 px
on HiDPI), next to a short text countdown like "24:00". It must read at 16 px
in a single colour and stay legible against both light and dark panels.

### 5. Dimmer overlay
While the break card shows, every other monitor is covered by a full-screen
dark overlay. Today it is a flat dark fill. It can carry texture — scanlines,
dither, a repeating motif — as long as it stays dark enough to push the other
screens back and cheap enough to redraw full-screen.

### 6. Top-bar dropdown menu (text and glyphs only)
Clicking the indicator opens a menu drawn by GNOME Shell itself, which the
application cannot style. What *can* be designed is the wording and any block
or arrow glyphs inside the labels. The items, in order:
status line ("Next break in 24:00") · daily summary ("3 breaks taken · 1
missed") · Statistics · Start break now · I'm back — restart the work timer ·
Pause reminders (submenu: For 30 minutes / For 1 hour / Until I resume) ·
Resume reminders · Durations (submenus: Work interval, Break length) · Sleep
and lock timing (Active time only / Wall-clock time) · Options (Show countdown
in top bar / Count time away as a break / Count away after / Play a sound at
each break) · Quit.

Optional, and I'd like your opinion on it: since the menu can't be styled,
should the app gain its own **control panel window** in the pixel language,
opened from the menu, carrying these same settings? If you think it earns its
place, design it; if you think the menu is enough, say so.

## Motion

Animation is wanted, and it is the part I most want your point of view on. It
should serve the app's idea — that keeping your breaks is a game you are
winning or losing — rather than decorate it. Things worth considering, none of
them required:

- a character whose state tracks the user's: sitting and working, standing,
  stretching, walking
- the countdown's own behaviour: blinking separators, digits that flip or
  shudder, urgency as the number approaches zero
- the progress bar draining in discrete steps rather than smoothly
- what happens at the moments that matter: the card appearing, a break being
  confirmed, a break being missed, the standing timer starting
- ambient life in the pill while it counts all day
- the score screen rewarding a good week

Specify frame counts, frame order, and milliseconds per frame for everything
that moves. Assume a low frame rate is a feature, not a limitation. Also
specify what each animation becomes when the desktop has "reduce animation"
turned on — every motion needs a still fallback.

## Implementation constraints

These are what the design has to survive, not suggestions about how it should
look:

- **Rendering**: GTK3 on X11. Flat fills, hard 1-pixel-grid edges, and sprite
  blitting are all easy. Anything drawn on a pixel grid at integer scale is
  easy. Blur, soft shadows, non-integer scaling, and free-form vector curves
  are not — avoid them entirely rather than approximating them.
- **Pixel grid**: design on a virtual grid where one "art pixel" is rendered as
  a block of 3 or 4 real screen pixels. Name the scale factor you designed at,
  and keep every dimension a whole number of art pixels.
- **Sprites**: give me every sprite as a pixel grid, sized in art pixels,
  ideally 32×32 or smaller, with colours drawn only from the palette you
  define. A PNG at exactly one image pixel per art pixel is perfect; a labelled
  grid of colour indices works too.
- **Typography**: any font can be shipped with the app provided it is
  redistributable — SIL Open Font License, MIT, or CC0. Name the exact font,
  its licence and where to download it. Bitmap-style pixel faces render best at
  their design size and integer multiples of it, so specify each text role's
  size in whole art pixels. Alternatively, design the display type as sprites
  and hand me the glyph grids.
- **Colour**: define a fixed, small palette — hard hex values, each named, each
  with a stated role. No gradients, no alpha blending except fully transparent
  or fully opaque. The whole app should draw from that one palette.
- **Text length**: every label is also translated into French, which typically
  runs 20–30% longer than English. Say the maximum characters each button and
  label may hold, and leave the layout room to take it.
- **States**: buttons need normal, hover, pressed, disabled and keyboard-focus
  treatments — keyboard focus must be visible, since the card is operated with
  S, K, T and Enter.
- **Sizes**: window sizes are yours to choose, but the break card should stay
  comfortably smaller than a laptop screen (roughly 400–700 px wide at 100%
  scale), and the pill must stay small enough to live on the edge of the screen
  all day.

## Copy

The current wording is listed above, screen by screen. You are free to rewrite
all of it — shorter, punchier, in whatever voice the design calls for — as long
as each label still says plainly what it does and what will happen. If your
typeface is wide, tightening the copy is expected. Hand back the final English
string for every label, button, title, hint and status line, including the
top-bar menu items.

## Deliverables

1. **Design rationale** — a short statement of the direction and the one idea
   the design is built around, plus what you deliberately rejected.
2. **Palette** — a table: name, hex, role.
3. **Type spec** — font name, licence, download URL; every text role with its
   size, weight, letter-spacing, line height, and casing.
4. **Screen specs** — for each surface and each of its states: overall size,
   the full layout in art pixels (spacing, sizes, borders, alignment), and an
   image or precise wireframe of the finished screen. Break card × 3 states,
   standing pill, statistics window, dimmer, plus the control panel if you
   decide it earns its place.
5. **Component specs** — window frame and border, buttons in all five states,
   the progress bar (cell count, filled / empty / urgent), timeline marks in
   five outcome colours, contribution-grid tiles across four levels plus empty,
   legend swatches, tooltips, the score and mood treatments.
6. **Sprites** — every frame of every animated element as a pixel grid, with
   frame order, milliseconds per frame, and loop behaviour.
7. **Icon** — the top-bar symbolic icon on a 16×16 art-pixel grid, monochrome,
   plus its 24×24 version.
8. **Motion spec** — every animation: what triggers it, how long it runs, its
   frames, and its reduced-motion fallback.
9. **Copy sheet** — the final English string for every piece of text, with the
   character budget you designed it to.

Take a real point of view. I would rather have one opinionated, cohesive world
that surprises me than a safe collection of retro tropes.
