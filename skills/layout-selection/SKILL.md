# Layout Selection

TODO: prompt body. Input: one slide's content + the template's classified layout patterns (from `design_system`) + the chosen variant axis for this deck (see DESIGN_PHILOSOPHY.md / ТЗ п.5: 3 layout variants, axis team-defined). Output: chosen pattern id + any per-pattern parameters (density, grouping, viz type) needed by `packages/layout` to compose the slide.

Must generalize to layout patterns never seen at training/dev time — this is the skill most exposed to the "unseen template" requirement.
