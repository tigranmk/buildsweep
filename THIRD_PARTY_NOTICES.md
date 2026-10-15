# Third-party notices

buildsweep itself has no required dependencies and contains no code copied from
third-party projects, apart from the macOS Finder trash code shared with
twinsweep (same author, MIT).

## Optional dependency

**Send2Trash**, installed only with `pip install 'buildsweep[trash]'`.
<https://github.com/arsenetar/send2trash>. BSD 3-Clause License.
Copyright (c) 2017, Virgil Dupras. Used, unmodified, to move folders to the
Trash or Recycle Bin on Linux and Windows.

## Design influences (no code used)

- **kondo**: <https://github.com/tbillington/kondo>. MIT License. Cleaning
  project artifacts by detecting project types from marker files.
- **npkill**: <https://github.com/voidcosmos/npkill>. MIT License. Interactive
  removal of `node_modules` with size and last-modified information.
- **twinsweep**: <https://github.com/tigranmk/twinsweep>. MIT License.
  Report-by-default workflow, confirmation and dry-run conventions, Finder
  trash approach.
