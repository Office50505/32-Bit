# ProvenanceLab design system

The accepted concept images are:

- `docs/design/source-workspace-concept.png`
- `docs/design/validation-results-concept.png`
- `docs/design/prosion-inspired-validation-concept.png`

## Direction

The product uses a scientific-editorial visual language inspired by contemporary biotech publishing: an ice-blue workspace, midnight typography, spectral cyan-to-magenta navigation accents, fine cool-slate rules, and molecular diagrams as the primary visual material. The language is original to ProvenanceLab and does not reuse third-party logos, artwork, copy, animation files, or commercial typefaces. Amber is reserved for ambiguity, rose for invalidity, green for verified results, and grey-blue for unavailable evidence.

## Typography

- Display and interface: bundled `Manrope Variable`, followed by `Avenir Next`, `Segoe UI`, and system sans-serif fallbacks. Manrope is the redistributable visual substitute for the reference site's commercial Aeonik typeface.
- Display headings use a light geometric weight, tight tracking, and editorial scale.
- Data headings and controls use compact, deliberate weights rather than browser defaults.

## Tokens

```text
background      #f2f6fa
surface         #ffffff
surface-muted   #f5faff
text            #102539
text-soft       #29435b
text-muted      #71869a
border          #d7e2ec
border-strong   #bfcddb
accent-cyan     #25cec4
accent-blue     #2e9af5
accent-violet   #966cf1
accent-magenta  #ed48cc
verified        #087b73
ambiguous       #c66a00
ambiguous-soft  #fff0cf
invalid         #c31f58
invalid-soft    #ffe4f0
unknown         #66758c
radius-sm       4px
radius-md       6px
radius-lg       8px
```

## Container model

- Quiet top navigation.
- Slim left provenance progress rail on desktop.
- Open two-column source/candidate workspace rather than a card grid.
- Master-detail validation region followed by a full-width comparison table.
- Borders provide structure; shadows are used only for active or modal elevation.
- The molecule canvas remains the primary visual focal point and atom labels are always visible.
- Gradient accents are limited to brand geometry, active progress, selected underlines, and the primary footer action.

## Component inventory

- Atoms: button, icon button, status mark, status label, spinner.
- Molecules: input-mode tab, dropzone, progress step, property value, molecule list item.
- Organisms: app header, progress rail, source workspace, candidate panel, validation detail, property table.
- Templates: analysis shell and results shell.
- Pages: new analysis and validation results.

## Above-the-fold copy lock

The source screen uses “Start with your source” and the results screen uses “Validation complete”. Do not add decorative eyebrow text, marketing claims, metrics, or unrelated navigation.
