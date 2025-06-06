import os
import pathlib
import sys
import argparse
import argcomplete  # type: ignore


def get_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser for the Metronome CLI."""
    parser = argparse.ArgumentParser(
        prog="Metronome",
        description="A swiss-army knife to convert, sort, and analyze your music library.",
        epilog="Valid formatters: {ArtistName}, {AlbumArtist}, {AlbumTitle}, {AlbumYear}, {TrackNumber}, {TrackTitle}, {Extension}",
    )

    parser.add_argument(
        "-a",
        "--all",
        help="Performs convert->sort->analyze; treats input directory as read-only.",
        default=False,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Turn on verbose output (WARNING: THIS COULD LEAK SENSITIVE INFORMATION TO OUTPUT BUFFER)",
        default=False,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-c",
        "--convert",
        help="Convert input file(s) to specified format: mp3 (320kpbs) (default) or opus (384kbps).",
        choices=["mp3", "opus"],
        default="mp3",
    )
    parser.add_argument(
        "--threads",
        help="Number of threads to use for conversion",
        default=os.cpu_count() or 2,
    )
    parser.add_argument(
        "-s",
        "--sort",
        help="Sort files using whatever data the script can find according to format specified.",
        default=False,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-n",
        "--analyze",
        help="Use AcoustID to generate audio fingerprint and check against MusicBrainz; will be slow for large libraries.",
        default=False,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Input directory containing original files, folder structure is respected.",
        default="input",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory for final converted files.",
        default="output",
    )
    parser.add_argument(
        "--extra-extensions",
        help="Comma-separated list of extra file extensions to include (e.g. m4a,flac,wav).",
        type=lambda s: [ext.strip() for ext in s.split(",")] if s else [],
        default=[],
    )
    parser.add_argument(
        "-p",
        "--in-place",
        help="Work on input directory directly; irrevocable (WARNING: THIS IS NOT RECOMMENDED)",
        default=False,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-f",
        "--format",
        help="Set custom format for output files, eg; {TrackNumber} - {TrackTitle}, see below for full list of formatters. This supports directory creation.",
        default="{ArtistName}/{AlbumTitle} [{AlbumYear}]/{TrackNumber} - {TrackTitle}.{Extension}",
    )
    parser.add_argument(
        "-t",
        "--strip",
        help="Strip all metadata in library.",
        default=False,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-r",
        "--cover_art",
        help="Place any available cover art in the album directory. Useful with --strip enabled.",
        default=False,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-e",
        "--disable-explicit-check",
        help="By default we will check if a song has an explicit version in the library and skip the clean one.",
        default=False,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--log-level",
        help="Set log level: info, log, warn, debug (default: warn)",
        choices=["info", "log", "warn", "debug"],
        default="warn",
    )
    parser.add_argument(
        "--install-completion",
        help="Print shell completion setup code for this script.",
        action="store_true",
    )

    # Add autocomplete support
    argcomplete.autocomplete(parser)

    # Handle --install-completion before parsing other args
    if "--install-completion" in sys.argv:        

        script_path = os.path.abspath(sys.argv[0])
        completion_cmd = f'eval "$(register-python-argcomplete {script_path})"'

        shell = os.environ.get("SHELL", "")
        home = str(pathlib.Path.home())

        if "zsh" in shell:
            rc_file = os.path.join(home, ".zshrc")
        elif "bash" in shell:
            rc_file = os.path.join(home, ".bashrc")
        elif "fish" in shell:
            rc_file = os.path.join(home, ".config/fish/config.fish")
            completion_cmd = f"register-python-argcomplete {script_path} | source"
        else:
            rc_file = None

        if rc_file:
            # Append to rc file if not already present
            with open(rc_file, "a+") as f:
                f.seek(0)
                contents = f.read()
                if completion_cmd not in contents:
                    f.write(f"\n# Enable argcomplete for Metronome\n{completion_cmd}\n")
            print(f"Added completion to {rc_file}")

            # Source the rc file in the current shell if possible
            if "bash" in shell or "zsh" in shell:
                os.system(f". {rc_file}")
                print(
                    f"Sourced {rc_file}. Completion should now be available in this shell."
                )
            elif "fish" in shell:
                os.system(f"{completion_cmd}")
                print(
                    "Sourced fish config. Completion should now be available in this shell."
                )
            else:
                print("Please restart your shell or source your rc file manually.")
        else:
            print(completion_cmd)
            print(
                "Could not detect your shell. Please add the above line to your shell rc file manually."
            )

        print(
            "Make sure ~/.local/bin is in your PATH to use this script with completion."
        )
        sys.exit(0)
        
    if len(sys.argv) == 1:
        parser.print_help()
        print("Please select at least one option to begin.")
        exit()
    
    # Initialize argcomplete for the parser
    argcomplete.autocomplete(parser)
    return parser
