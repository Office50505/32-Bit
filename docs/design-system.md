# ProvenanceLab design system

The accepted concept images are:

- `docs/design/source-workspace-concept.png`
- `docs/design/validation-results-concept.png`

## Direction

The product uses a scientific-editorial visual language: a true white workspace, deep navy typography, restrained teal actions, fine cool-slate rules, and molecular diagrams as the primary visual material. Amber is reserved for ambiguity, red for invalidity, green for verified results, and grey-blue for unavailable evidence.

## Typography

- Display: Georgia, `Times New Roman`, serif.
- Interface: Inter when available, followed by system sans-serif fallbacks.
- Headings are compact and high contrast; control typography is deliberately 13–15px rather than browser defaults.

## Tokens

```text
background      #ffffff
surface-muted   #f7fafc
text            #0b1a33
text-muted      #52627a
border          #d8e1ea
accent          #007f83
accent-soft     #e8f7f7
verified        #087f73
ambiguous       #c66a00
ambiguous-soft  #fff7e8
invalid         #cf202f
invalid-soft    #fff1f2
unknown         #66758c
radius-sm       6px
radius-md       10px
radius-lg       12px
```

## Container model

- Quiet top navigation.
- Slim left provenance progress rail on desktop.
- Open two-column source/candidate workspace rather than a card grid.
- Master-detail validation region followed by a full-width comparison table.
- Borders provide structure; shadows are used sparingly.

## Component inventory

- Atoms: button, icon button, status mark, status label, spinner.
- Molecules: input-mode tab, dropzone, progress step, property value, molecule list item.
- Organisms: app header, progress rail, source workspace, candidate panel, validation detail, property table.
- Templates: analysis shell and results shell.
- Pages: new analysis and validation results.

## Above-the-fold copy lock

The source screen uses “Start with your source” and the results screen uses “Validation complete”. Do not add decorative eyebrow text, marketing claims, metrics, or unrelated navigation.
