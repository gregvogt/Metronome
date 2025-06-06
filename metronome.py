#!/usr/bin/env python3

from io import BytesIO
import sys, platform, tempfile, os, stat
from datetime import datetime
from typing import List
from pathlib import Path
from glob import glob
from tqdm import tqdm # type: ignore
import re
import argcomplete # type: ignore

# Conversion Deps
import shutil
import json
from threading import Thread
from queue import Queue
from subprocess import Popen, PIPE, STDOUT

system = platform.system()
temp_directory = tempfile.gettempdir()

bin_location = Path(os.getcwd(), "bin")

if system != "Linux" and system != "Windows":
    raise RuntimeError("{} is not supported.".format(system))

import argparse  # noqa

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
    "--debug",
    help="Turn on debug info and methods",
    default=False,
    action=argparse.BooleanOptionalAction,
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
    import os
    import pathlib

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
        completion_cmd = f'register-python-argcomplete {script_path} | source'
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
            os.system(f'. {rc_file}')
            print(f"Sourced {rc_file}. Completion should now be available in this shell.")
        elif "fish" in shell:
            os.system(f'{completion_cmd}')
            print("Sourced fish config. Completion should now be available in this shell.")
        else:
            print("Please restart your shell or source your rc file manually.")
    else:
        print(completion_cmd)
        print("Could not detect your shell. Please add the above line to your shell rc file manually.")

    print("Make sure ~/.local/bin is in your PATH to use this script with completion.")
    sys.exit(0)

metronome_settings = vars(parser.parse_args())

if len(sys.argv) == 1:
    parser.print_help()
    print("Please select at least one option to begin.")
    exit()

programs = {
    "ffmpeg": {
        "Linux": {
            "url": "https://www.johnvansickle.com/ffmpeg/old-releases/ffmpeg-6.0.1-amd64-static.tar.xz",
            "checksum": "28268bf402f1083833ea269331587f60a242848880073be8016501d864bd07a5",
        },
        "Windows": {
            "url": "https://github.com/GyanD/codexffmpeg/releases/download/7.0.1/ffmpeg-7.0.1-full_build.zip",
            "checksum": "a69ad4e55e7608db31f265c334ebd16d6df013f094777e5814f1ac3c223b0a90",
        },
    },
    "chromaprint": {
        "Linux": {
            "url": "https://github.com/acoustid/chromaprint/releases/download/v1.5.1/chromaprint-fpcalc-1.5.1-linux-x86_64.tar.gz",
            "checksum": "4d7433a7f778e5946d7225230681cbcd634e153316ecac87c538c33ac32387a5",
        },
        "Windows": {
            "url": "https://github.com/acoustid/chromaprint/releases/download/v1.5.1/chromaprint-fpcalc-1.5.1-windows-x86_64.zip",
            "checksum": "36b478e16aa69f757f376645db0d436073a42c0097b6bb2677109e7835b59bbc",
        },
    },
}

import atexit, platform, pathlib, json  # noqa

current_working_dir = os.getcwd()
active_user_dir = pathlib.Path.home()

metronome_json_settings = os.path.join(active_user_dir, ".metronome.json")


# Runs on script exit, even when SIGINT is called
@atexit.register
def termination_handler():
    # Make sure we save everytime
    # TODO: Add exception handling in case we lose filesystem
    with open(metronome_json_settings, "w") as settings_json:
        settings_json.write(json.dumps(metronome_settings))
        settings_json.close()

    print("Exiting...")


# Load previous sessions settings
# if os.path.exists(metronome_json_settings):
#    with open(metronome_json_settings, "r") as settings_json:
#        # FIXME: this will overwrite new settings always, needs proper fix
#        metronome_settings.update(json.loads(settings_json.read()))
#        settings_json.close()


def make_dir(directory: str) -> str:
    if not os.path.isabs(directory):
        directory = os.path.join(current_working_dir, directory)
    directory = os.path.abspath(directory)

    base_dir = os.path.abspath(current_working_dir)
    if not directory.startswith(base_dir + os.sep) and directory != base_dir:
        raise ValueError(f"Path traversal detected: {directory} is outside {base_dir}")

    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

    return directory


metronome_settings["input"] = make_dir(metronome_settings["input"])
metronome_settings["output"] = make_dir(metronome_settings["output"])
make_dir("bin")

if metronome_settings["all"]:
    metronome_settings["sort"] = True
    metronome_settings["convert"] = True
    metronome_settings["analyze"] = True


def extract(in_file: bytes, out_path: Path, needles: List) -> bool:
    from zipfile import ZipFile  # noqa
    from tarfile import TarFile  # noqa
    import magic # type: ignore

    def safe_extract_path(base_dir: Path, target_path: Path) -> Path:
        # Resolve the absolute path and ensure it's within base_dir
        abs_target = (base_dir / target_path.name).resolve()
        if not str(abs_target).startswith(str(base_dir.resolve()) + os.sep):
            raise ValueError(f"Blocked path traversal attempt: {abs_target}")
        return abs_target

    file_type = magic.from_buffer(in_file, mime=True)

    if file_type == "application/x-xz" or file_type == "application/gzip":
        with TarFile.open(fileobj=BytesIO(in_file), mode="r|*") as tar:
            for file in tar:
                file_path = Path(file.path)

                if "".join(file_path.suffixes) not in ["", "exe"]:
                    continue

                if file_path.stem in needles:
                    safe_path = safe_extract_path(out_path, file_path)
                    with open(safe_path, "wb") as file_out:
                        file_bytes = tar.extractfile(file)

                        if file_bytes is None:
                            continue

                        file_out.write(file_bytes.read())

                        if system == "Linux":
                            os.fchmod(file_out.fileno(), stat.S_IEXEC)

                        file_out.close()

    elif file_type == "application/zip":
        with ZipFile(BytesIO(in_file)) as zip:  # type: ignore
            files = zip.infolist()

            for file in files:
                file_path = Path(file.filename)

                if file_path.stem in needles and file_path.suffix in ["", ".exe"]:
                    safe_path = safe_extract_path(out_path, file_path)
                    with open(safe_path, "wb") as file_out:
                        file_out.write(zip.read(str(file.filename)))

                        if system == "Linux":
                            os.fchmod(file_out.fileno(), stat.S_IEXEC)

                        file_out.close()
    else:
        return False

    return True


def download(url: str, checksum: str | None = None) -> bytes:
    import requests # type: ignore
    import hashlib
    try:
        file_request = requests.get(url, stream=True)
        file_request.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download {url}: {e}")

    file_size = int(file_request.headers.get("Content-Length", 0))
    file = bytearray()

    print("Downloading: {}".format(url))

    with tqdm(
        total=file_size,
        unit="B",
        unit_scale=True,
    ) as file_progress_bar:
        for block in file_request.iter_content(1024):
            file_progress_bar.update(len(block))
            file.extend(block)

        # Check if download completed
        if file_size != 0 and file_progress_bar.n != file_size:
            raise RuntimeError("Unable to download: {}".format(url))

    calculated_checksum = hashlib.sha256(file).hexdigest()
    if calculated_checksum != checksum:
        raise RuntimeError(
            "{} checksums do not match! Please obtain from trusted source. {} Expected: {} {} Found: {}".format(url, os.linesep, checksum, os.linesep, calculated_checksum)
        )

    return bytes(file)


if metronome_settings["analyze"] or metronome_settings["convert"]:
    import shutil, hashlib  # noqa

    if (
        metronome_settings["convert"]
        and shutil.which("ffmpeg") is None
        and not os.path.exists(os.path.join(bin_location, "ffmpeg"))
    ):
        ffmpeg_archive = download(
            programs["ffmpeg"][system]["url"], programs["ffmpeg"][system]["checksum"]
        )

        # total_size = int(ffmpeg_zip.headers.get("Content-Length", 0))
        # block_size = 1024

        # with tqdm(total=total_size, unit="B", unit_scale=True) as ffmpeg_progress:
        #    with open(ffmpeg_zip_location, "wb") as ffmpeg_zip_out:
        #        for data in ffmpeg_zip.iter_content(block_size):
        #            ffmpeg_progress.update(len(data))
        #            ffmpeg_zip_out.write(data)

        #        ffmpeg_zip_out.close()

        # if total_size != 0 and ffmpeg_progress.n != total_size:
        #    raise RuntimeError(
        #        "Unable to download: {}".format(ffmpeg_urls[system]["url"])
        #    )

        if not extract(ffmpeg_archive, bin_location, ["ffmpeg", "ffprobe"]):
            raise RuntimeError(
                "Unable to extract {}, please obtain manually.".format(
                    programs["ffmpeg"][system]["url"]
                )
            )

    if (
        metronome_settings["analyze"]
        and shutil.which("fpcalc") is None
        and not os.path.exists(os.path.join(bin_location, "fpcalc"))
    ):
        chromaprint_archive = download(
            programs["chromaprint"][system]["url"],
            programs["chromaprint"][system]["checksum"],
        )

        if not extract(chromaprint_archive, bin_location, ["fpcalc"]):
            raise RuntimeError(
                "Unable to extract {}, please obtain manually.".format(
                    programs["chromaprint"][system]["url"]
                )
            )


# A small primer on order, to avoid I/O hammering by grabbing
# the file over and over again for different stages we'll grab
# each file and load it into memory and do what we need while
# we have it loaded and export it at the end of the chain.


def open_file(filename: pathlib.Path) -> bytes:
    with open(filename, "rb") as file:
        file_loaded = file.read()

    return file_loaded


def ffprobe(file: Path):
    json_packed = ""

    ffprobe_path = shutil.which("ffprobe") or os.path.join(bin_location, "ffprobe")
    ffprobe_command = [
        ffprobe_path,
        "-v",
        "quiet",
        "-show_format",
        "-show_streams",
        "-print_format",
        "json",
        str(file),
    ]
    with Popen(
        ffprobe_command,
        shell=False,
        stdout=PIPE,
        stderr=STDOUT,
        universal_newlines=True,
    ) as probe:
        for line in probe.stdout:  # type: ignore
            json_packed += line

        # Make sure no ghost processes stay
        probe.kill()

    return json.loads(json_packed)


def ffmpeg(in_file: Path, out_file: Path, file_out_name: str, **kwargs) -> bool:
    ffmpeg_path = shutil.which("ffmpeg") or os.path.join(bin_location, "ffmpeg")
    output_format = metronome_settings.get("convert", "mp3")
    if output_format == "opus":
        codec_args = [
            "-c:a", "libopus",
            "-b:a", "384k",
            "-vbr", "on",
            "-compression_level", "10",
            "-map_metadata", "0",
            "-progress", "pipe:1",
            "-loglevel", "error",
            "-f", "opus",
        ]
        file_out_name = os.path.splitext(file_out_name)[0] + ".opus"
    else:  # mp3
        codec_args = [
            "-ab", "320k",
            "-vcodec", "copy",
            "-map_metadata", "0",
            "-id3v2_version", "3",
            "-progress", "pipe:1",
            "-loglevel", "error",
            "-f", "mp3",
        ]
        file_out_name = os.path.splitext(file_out_name)[0] + ".mp3"

    ffmpeg_command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(in_file),
        *codec_args,
        os.path.join(str(out_file.parent), file_out_name),
    ]

    # Limit our filenames to 40 chars so it looks uniform
    desc = (in_file.name[:37] + "...") if len(in_file.name) > 40 else in_file.name

    ffprobe_info = ffprobe(in_file)
    status = {}

    with tqdm(
        desc=desc,
        total=round(float(ffprobe_info["streams"][0]["duration"])),
        unit="s",
        bar_format="{desc:<40}: {percentage:3.0f}%|{bar}|{n_fmt}/{total_fmt} [{elapsed}]({rate_fmt}{postfix})",
        leave=False,
        ascii=True,
    ) as progress:
        # tqdm.write("Processing: {}".format(in_file))
        with Popen(
            ffmpeg_command,
            shell=False,
            stdout=PIPE,
            stderr=STDOUT,
            universal_newlines=True,
            **kwargs,
        ) as process:
            for line in process.stdout:  # type: ignore
                stat = line.split("=")

                if len(stat) < 2:
                    continue
                
                status.update({stat[0]: stat[1]})

                if "out_time_us" in stat:
                    total_time = round(float(status["out_time_us"]) / 1000000)
                    progress.update(total_time - progress.n)

                progress.refresh()

                if metronome_settings["debug"]:
                    with open(
                        os.path.join(
                            os.getcwd(),
                            "logs/{}-log-{}".format(
                                in_file.stem, datetime.now().strftime("%H-%M-%S")
                            ),
                        ),
                        "w+",
                    ) as log:
                        log.write(line)

            # print(status)
        progress.set_description_str(f"Converted: {desc:<40}")
        progress.close()

    queue.task_done()
    return queue.get()


def is_safe_path(base_dir: str, path: str) -> bool:
    # Prevent path traversal and ensure path is within base_dir
    abs_base = os.path.abspath(base_dir)
    abs_path = os.path.abspath(path)
    return abs_path.startswith(abs_base + os.sep) or abs_path == abs_base


def is_safe_filename(filename: str) -> bool:
    # Disallow forbidden characters for Windows and Unix filesystems
    forbidden = '<>:"/\\|?*\0'
    
    if metronome_settings["debug"]:
        print(f"Checking: {repr(filename)}")
        print(f"Forbidden: {any(char in filename for char in forbidden)}")
        print(f"Control: {any(ord(char) < 32 for char in filename)}")
        print(f"Strip: {filename.strip(' .') != filename}")
        print(f"Empty: {not filename}")
    
    if any(char in filename for char in forbidden):
        return False
    # Disallow ASCII control characters
    if any(ord(char) < 32 for char in filename):
        return False
    # Disallow leading/trailing spaces or dots
    if filename.strip(" .") != filename:
        return False
    # Disallow empty filenames
    if not filename:
        return False
    return True


files = []
for file in glob(
    os.path.join(current_working_dir, metronome_settings["input"], "**", "*.flac"),
    recursive=True,
):
    # Check for path traversal and unsupported characters
    if not is_safe_path(metronome_settings["input"], file):
        tqdm.write(f"Skipping potentially unsafe path: {file}")
        continue
    if not is_safe_filename(os.path.basename(file)):
        tqdm.write(f"Skipping file with unsupported characters: {file}")
        continue
    files.append(file)


threads = int(metronome_settings["threads"])

thread_list = []

if metronome_settings["convert"]:
    convert_count = 0

    # Just to make sure tqdm does't start freaking out
    tqdm.get_lock()

    queue = Queue(threads)

    with tqdm(
        desc="Total Files",
        total=len(files),
        position=(threads + 1),
        leave=False,
        ascii=True,
    ) as total_bar:
        for index, file in enumerate(files, 1):
            # Replace input folder with output to maintain original folder structure in output location
            file_out = Path(
                file.replace(metronome_settings["input"], metronome_settings["output"])
            )
            file = Path(file)

            output_ext = metronome_settings["convert"]
            file_out_name = f"{file.stem}.{output_ext}"
            
            # We dont want to convert again
            if os.path.exists(os.path.join(file_out.parent, file_out_name)):
                tqdm.write(f"{file_out_name} already exists! Skipping...")
                continue

            # Create folder structure if does not exist
            if not os.path.exists(file_out.parent):
                os.makedirs(file_out.parent)

            thread = Thread(target=ffmpeg, args=(file, file_out, file_out_name))

            queue.put(index)
            thread_list.append(thread)
            thread.start()

            convert_count = convert_count + 1

            total_bar.update(index - total_bar.n)
            total_bar.refresh()

        # Join threads back into main to free up Queue
        [thread.join() for thread in thread_list]

    print(f"\nTotal converted files: {convert_count}")
    