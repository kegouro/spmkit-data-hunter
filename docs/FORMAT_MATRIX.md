# AFM/SPM format matrix

This matrix describes discovery signals, not guaranteed reader support.

## Strong native-format signals

| Family | Typical suffixes | Notes |
|---|---|---|
| Nanosurf | `.nid`, `.nhf` | Strong native signal |
| JPK | `.jpk`, `.jpk-force`, `.jpk-qi-data`, `.jpk-qi-image`, `.h5-jpk` | Compound suffixes must be checked before generic suffix parsing |
| Gwyddion | `.gwy`, `.gsf` | May contain imported or processed channels |
| Asylum Research | `.ibw`, `.ardf` | Context and header inspection recommended |
| Nanonis | `.sxm` | Strong native signal |
| NT-MDT | `.mdt`, `.sm2`, `.sm3` | Multiple generations |
| WSxM | `.top`, `.stp`, `.cur` | Suffixes may collide with unrelated data |
| Omicron/Matrix | `.mtrx` | Strong contextual signal |
| Generic surface metrology | `.sdf`, `.sur`, `.x3p`, `.bcr`, `.bcrf` | May be processed or instrument-neutral |

## Ambiguous formats

| Suffix | Why ambiguous |
|---|---|
| `.spm` | Used by more than one vendor/tool |
| `.dat` | Generic binary or text data |
| `.h5`, `.hdf5` | Container, not a domain-specific format |
| `.tif`, `.tiff` | Native vendor data, exported map, or rendered image |
| `.csv`, `.txt` | Raw curve export, processed table, log, or documentation |
| `.mat`, `.npy`, `.npz` | Arbitrary scientific arrays |
| numeric suffixes such as `.001` | Can be Bruker/Nanoscope data or unrelated file numbering |

Ambiguous suffixes require metadata, filename tokens, MIME/magic inspection, or
a format-aware reader before receiving high format confidence.

## Planned support matrix

Future manifests should separately report:

```text
format detected
SPM-Kit reader support
AFMReader support
Gwyddion import support
verification method
confidence and reasons
```
