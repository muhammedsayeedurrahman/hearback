# Fonts

IBM Plex Sans (variable) and IBM Plex Mono, self-hosted.

These files are committed rather than fetched at build time. The README promises the demo comes
up on a dead venue network, and `next/font/google` resolves over the network during the build —
committing the subsets keeps that promise true for the typeface as well as for the code.

| File | Family | Weights |
|---|---|---|
| `ibm-plex-sans-latin-wght-normal.woff2` | IBM Plex Sans Variable | 100–700 |
| `ibm-plex-mono-latin-400-normal.woff2` | IBM Plex Mono | 400 |
| `ibm-plex-mono-latin-500-normal.woff2` | IBM Plex Mono | 500 |

Latin subsets taken from the Fontsource distribution of the upstream IBM Plex release
(`@fontsource-variable/ibm-plex-sans@5`, `@fontsource/ibm-plex-mono@5`). 75 KB in total.

Licensed under the SIL Open Font License 1.1, Copyright 2017 IBM Corp. Full text in `OFL.txt`.
