# SpektraFilm Windows — visual language

The shell is an image-first darkroom editor. The developed frame owns the window. Controls are short labels, chips, and picture tiles. Longer names and the runtime field they write live in tooltips.

Public editors such as [Fotufilm Engine](https://fotufilm.com/documentation.html) were a UX reference for this layout: a large photograph, a horizontal strip of small film previews, paper kept as its own visual choice, and a drag handle between the picture and the inspector. That is inspiration only. SpektraFilm does not use Fotufilm code, assets, fonts, or branding. The stock tiles are original color studies keyed by profile id. They are not measured science and they are not borrowed artwork.

- **Easel.** The center is the print, with registration corners. Hold the picture, or the Hold control, to see the scene before simulation when the sidecar returned a reference frame.
- **Strips.** Film stocks are a horizontal row of swatches. Papers are a thinner row beneath them. A roll of recently developed frames sits under the easel.
- **Inspector.** One narrow column holds exposure, the yellow and magenta filters, halation, preview or scan, and the file or RAW fields for the source in use. Drag its edge to resize. Double-click, or Home, restores the default width.
- **Type and color.** Newsreader and IBM Plex Mono (SIL OFL 1.1, see `src/fonts/OFL.txt`) carry the wordmark and the figures. The emulsion black, dye cyan / magenta / yellow, and brass expose plate stay. They belong to this shell.

Motion is a safelight sweep while a render runs, and a short fade when a print appears. `prefers-reduced-motion` turns both off. Focus is a yellow ring.
