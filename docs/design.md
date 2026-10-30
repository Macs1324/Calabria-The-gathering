# Table design

Why the v0.3 table looked cheap, and the rules the redesign follows.

## What was wrong

1. **Emoji as icons.** 📷 🎙 🎲 ↶ ⟳ ➜ ✕ render differently on every OS,
   don't align with text, and can't take the theme's colour. They are the
   quickest tell of a UI nobody designed.
2. **The accent was everywhere.** Every button turned orange on hover, the
   active board got a thick orange frame and glow, the turn pill glowed, the
   toast had an orange stripe. When everything is highlighted nothing is, and
   the one action that matters (End turn) had to shout to be found.
3. **A flat toolbar of equals.** Fifteen same-sized controls in one row
   (room, phases, Voice, ?, Undo, Untap, d20, d6, New game…, Leave, End turn),
   with debug-flavoured labels like `T1` and `main 2`. No grouping, no
   hierarchy, rare actions as loud as frequent ones.
4. **Boxes inside boxes, mostly empty.** Each player was a bordered panel
   on a dark page, the sidebar was three more bordered panels, and the piles
   were disabled `Graveyard 0` buttons at 35% opacity — they read as broken.
   An empty board was a big dark rectangle saying "Nothing in play yet".
5. **Admin-form sidebar.** Uppercase micro-headings (`MAT CAMERA`,
   `PLAY BY NAME`, `LOG`), native `<select>` and checkboxes, and a plain
   text log: it looked like a settings page bolted onto a game.

There was also no typographic identity: the CSS named Inter but never loaded
it, so every machine fell back to its system font next to a fantasy logo.

## The design

**One table, not panels.** The play area is a single felt surface. Seats are
separated by a hairline, not boxed. Opponents sit at the top, you at the
bottom, like a real table. Whoever's turn it is gets a quiet ember edge on
their side — not a frame.

**Seats have identity.** Each seat gets a mana colour (white, blue, black,
red, green, in seat order) used for the avatar ring, their name in the
activity log and their life medallion. Life totals are big, set in the
display face, and readable across a room.

**Zones look like zones.** Graveyard, exile and command are small
card-shaped slots showing the top card and a count; empty slots are dashed
outlines, not disabled buttons.

**A three-part top bar.** Left: sigil and room code (click to copy the
invite). Centre: the turn — whose turn, which phase as a stepper. Right: the
three things you do every turn as icon buttons (voice, undo, untap), a "More"
menu for rare things (dice, new game, leave), and End turn — the only filled
accent button on the screen.

**A dock, not forms.** The sidebar is your dock: the camera is a framed
viewport with its status inside the frame; "play a card" is a search field
with chip toggles instead of a native select and checkboxes; the log is an
activity feed grouped by turn, with names in seat colours.

**Rules**

- The ember accent means "act now" or "yours": End turn, your turn, focus,
  selection. Nothing else is orange.
- Icons are one inline SVG set (24px grid, 1.75 stroke, `currentColor`).
  No emoji in the UI.
- Two typefaces: _Cinzel_ for display (life totals, names, room code, turn),
  _Inter_ for everything else. Numbers are tabular.
- Surfaces are separated by tone first and hairlines second; no nested
  borders.
- Rare actions live one click deeper than frequent ones.
