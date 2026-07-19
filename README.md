# Analog Devices (Maxim) SVD collection

CMSIS SVD files for Analog Devices MAX32 and MAX78 microcontrollers, pulled
straight out of the vendor's msdk repository. Files are unmodified copies
(provenance: pristine). Every file was parsed with Python's xml.etree and has
a `device` root element.

## Coverage

| Family | Files |
|--------|-------|
| MAX32  | 14    |
| MAX78  | 2     |

Devices: MAX32520, MAX32570, MAX32572, MAX32650, MAX32655, MAX32657,
MAX32660, MAX32662, MAX32665, MAX32670, MAX32672, MAX32675, MAX32680,
MAX32690, MAX78000, MAX78002.

Total: 16 files, about 7.8 MB.

## Source

- Repo: https://github.com/analogdevicesinc/msdk
- Commit: f7c976853973cdeb3f0ab6009bec601ec9ce396f (HEAD of the default
  branch at fetch time, 2026-07-19)
- Path in repo: `Libraries/CMSIS/Device/Maxim/<PART>/Include/<part>.svd`
- Fetch method: partial clone (`--filter=blob:none --depth 1 --sparse`) with
  a sparse checkout of `Libraries/CMSIS/Device/Maxim` only.

## License and redistribution status

The msdk repository root `LICENSE` file is the Apache License 2.0
(SPDX: Apache-2.0). A copy retrieved from the repo is in
`LICENSES/msdk-LICENSE.txt`. The file starts:

> Apache License
> Version 2.0, January 2004

and grants redistribution: "You may reproduce and distribute copies of the
Work or Derivative Works thereof in any medium, with or without
modifications" (Section 4), subject to keeping the license text and notices.
The license file ends with this note:

> This software is subject to the above license but may also include
> additional software components that are identified in the NOTICE file,
> together with their associated licenses.

The SVD files themselves carry no separate license header. Redistribution of
these copies with the license file included is permitted under Apache-2.0.

## Refresh

```
python fetch.py
```

The fetch is incremental: it first compares the upstream HEAD sha (via
`git ls-remote`) with the one recorded in `manifest.json` and only when
they differ does it re-clone msdk into `.work/`, copy and validate the SVD
files, refresh `LICENSES/msdk-LICENSE.txt`, and rewrite `manifest.json`
(the temporary `.work/` clone is removed automatically). A GitHub Action
(`.github/workflows/check-updates.yml`) runs this script every Monday at
06:00 UTC and commits any updates.

## Provenance legend

- pristine: byte-for-byte copy of the upstream file (all files here)
- patched: upstream file with local fixes (none)
- community: third-party maintained file (none)
- converted: generated from another format (none)

## Known gaps

- msdk only covers the current MAX32/MAX78 parts. Older Maxim Arm parts
  (MAX32600, MAX32620, MAX32625, MAX32630 and similar) are not in msdk and
  are not included here.
- The expected part list mentioned about 15 devices. The clone yielded 16:
  MAX32572 and MAX32657 are present in msdk in addition to the expected set.
