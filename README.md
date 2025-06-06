<div align="center">

# Metronome

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

Metronome is a swiss-army knife command-line tool to convert, sort, and analyze your music library. It supports batch conversion between audio formats, preserves folder structure, and can analyze tracks using AcoustID and MusicBrainz.

</div>

## Features

- Batch convert audio files (FLAC, MP3, WAV, AAC, OGG, M4A, WMA, ALAC, AIFF, and more) to MP3 or Opus.
- Customizable output file and folder naming (Planned).
- Preserves original folder structure.
- Optional audio analysis using AcoustID/MusicBrainz (Planned).
- Multi-threaded conversion for speed.
- CLI and persistent user settings.
- Safe path and filename checks.

## Requirements

- Python 3.8+
- [ffmpeg](https://ffmpeg.org/) (bundled or system)
- [fpcalc](https://acoustid.org/chromaprint) (for analysis, optional)
- See `requirements.txt` for Python dependencies.

## Installation

1. Clone this repository:
    ```sh
    git clone https://github.com/yourusername/metronome.git
    cd metronome
    ```

2. Install Python dependencies:
    ```sh
    pip install -r requirements.txt
    ```

3. Ensure `ffmpeg` and `ffprobe` are available in `bin/` or your system PATH. The script can download and extract them if missing.

## Usage

```sh
python metronome.py [options]
```

### Common Options

- `-i, --input`  
  Input directory containing original files (default: `input`).

- `-o, --output`  
  Output directory for converted files (default: `output`).

- `-c, --convert`  
  Convert input files to specified format: `mp3` (default) or `opus`.

- `-f, --format`  
  Custom output file format, e.g. `{ArtistName}/{AlbumTitle} [{AlbumYear}]/{TrackNumber} - {TrackTitle}.{Extension}`.

- `--extra-extensions`  
  Comma-separated list of extra file extensions to include.

- `--threads`  
  Number of threads to use for conversion.

- `-a, --all`  
  Perform convert, sort, and analyze in one step.

- `-n, --analyze`  
  Use AcoustID/MusicBrainz to fingerprint and identify tracks.

Run `python metronome.py --help` for the full list of options.

## Example

```sh
python metronome.py -i input -o output --convert opus --threads 4
```

## Configuration

Settings are saved in `~/.metronome.json` and merged with CLI arguments.

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.

---

© 2024 Greg Vogt