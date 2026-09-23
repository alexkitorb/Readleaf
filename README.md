# Readleaf

Readleaf is a small, native GTK 4 reader for Rich Text Format (`.rtf`) files.
It is designed for Arch Linux and stays useful offline: documents are parsed
inside the app and no office suite, web service, or Electron runtime is used.

## Features

- Opens files from the chooser, command line, or drag and drop
- Displays fonts, sizes, bold, italic, underline, strike-through, colors,
  highlights, alignment, superscript, and subscript
- Incremental find with next/previous match navigation
- Zoom from 60% to 220%
- Document title, author, word count, and character count
- Ignores embedded objects, scripts, images, and other non-reading content
- Follows the GTK light/dark desktop preference

## Run it from the source folder

Arch dependencies:

```sh
sudo pacman -S --needed gtk4 python python-gobject
./run.sh
```

Open a file directly:

```sh
./run.sh ~/Documents/example.rtf
```

## Install on Arch Linux

Build and install the included package:

```sh
makepkg -si
```

After installation, launch **Readleaf** from the application menu or run:

```sh
readleaf document.rtf
```

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Open document |
| `Ctrl+F` | Find in document |
| `Ctrl++` / `Ctrl+-` | Zoom in / out |
| `Ctrl+0` | Reset zoom |
| `Ctrl+Q` | Quit |

## Scope

RTF has decades of vendor extensions. Readleaf supports the common text and
formatting controls used by Word, LibreOffice, WordPad, and TextEdit documents.
It intentionally does not execute or display embedded OLE objects, fields, or
macros. Images are skipped in version 1.0.

