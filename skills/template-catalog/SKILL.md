# Template Catalog

You catalogue the slides of a presentation template so a generator can later
pick the right slide for each part of a new deck. Every slide is given as one
row: its number, layout name, structure (what text areas it has), picture
count, and the text currently on it.

## Output

A single JSON object — no prose, no markdown fences:

```json
{"entries": [{"index": 7, "usable": true, "purpose": "title",
              "description": "Title slide: team name, task name, organizer logos"}]}
```

One entry per slide, `index` = the number shown after `#`.

- `usable` — **false** for slides that are not meant to end up in a real deck:
  - instructions to the template's user ("Привет, участник!", "Используй для
    оформления слайды 8–11", "Обязательный блок", recommended structure lists,
    "how to use this template");
  - style sheets: colour swatches and HEX codes, font specimens, icon sets,
    logo libraries, links to resources;
  - empty leftovers with no real place for content.

  **true** for every slide designed to carry deck content — even when its
  current text is sample content ("Lorem ipsum", "Имя Фамилия", a sample
  topic): that is exactly what the generator will replace.
- `purpose` — one word from: `title`, `agenda`, `section`, `problem`,
  `solution`, `features`, `stats`, `steps`, `timeline`, `comparison`, `team`,
  `demo`, `quote`, `image`, `content`, `contacts`, `closing`. Judge by what the
  slide is *built* for (its structure, labels, sample text), not by the sample
  topic: a section divider with a big number is `section` whether the sample
  says "Tourism" or "Finance".
- `description` — ≤ 15 words: what the slide is designed to hold, in terms a
  writer can use ("5 team member cards: name, role, messenger, phone",
  "big number + label ×3", "section divider: number and section name").
  Describe the slot design, not the sample topic. Empty for unusable slides.

## Rules

- Never skip a slide; never invent slide numbers.
- When unsure whether a slide is an instruction or content, mark it usable —
  a wrongly excluded content slide is worse than an included odd one.
