#!/usr/bin/env python3

from io import BytesIO
import queue
import sys, platform, tempfile, os, stat  # noqa
from datetime import datetime
from typing import List
from pathlib import Path
from glob import glob
from tqdm import tqdm

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

if len(sys.argv) == 1:
    print("Please select at least one option to begin.")
    exit()

programs = {
    "ffmpeg": {
        "Linux": {
            "url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
            "checksum": "b1e096314a5cc1437b23d675cc1f9941c472b25c4a501e99b7979b3768d8f66b",
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
    help="Convert input file(s) to specified format. Default 320kbps(or highest available) MP3",
    default=False,
    action=argparse.BooleanOptionalAction,
)
parser.add_argument(
    "--threads",
    help="Number of threads to use for conversion",
    default=2,
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

metronome_settings = vars(parser.parse_args())

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


# TODO: verify paths to aboid path traversal
def make_dir(directory: str) -> str:
    if not os.path.isabs(directory):
        directory = os.path.join(current_working_dir, directory)

    if not os.path.exists(directory):
        os.mkdir(directory)

    return directory


metronome_settings["input"] = make_dir(metronome_settings["input"])
metronome_settings["output"] = make_dir(metronome_settings["output"])
make_dir("bin")

if metronome_settings["all"]:
    metronome_settings["sort"] = True
    metronome_settings["convert"] = True
    metronome_settings["analyze"] = True

from tqdm import tqdm  # noqa


def extract(in_file: bytes, out_path: Path, needles: List) -> bool:
    from zipfile import ZipFile  # noqa
    from tarfile import TarFile  # noqa
    import magic

    # if isinstance(in_file, BytesIO):
    # file_prepared = in_file.read()
    file_type = magic.from_buffer(in_file, mime=True)
    # elif isinstance(in_file, Path):
    #    file_prepared = in_file
    #    file_type = magic.from_file(in_file, mime=True)

    #    if not os.path.exists(in_file):
    #        raise RuntimeError("{} does not exist.".format(in_file))
    # else:
    #    print(type(in_file))
    #    exit()

    if file_type == "application/x-xz" or file_type == "application/gzip":
        with TarFile.open(fileobj=BytesIO(in_file), mode="r|*") as tar:
            for file in tar:
                file_path = Path(file.path)

                if "".join(file_path.suffixes) not in ["", "exe"]:
                    continue

                if file_path.stem in needles:
                    with open(os.path.join(out_path, file_path.name), "wb") as file_out:
                        file_bytes = tar.extractfile(file)

                        if file_bytes is None:
                            continue

                        file_out.write(file_bytes.read())

                        if system == "Linux":
                            os.fchmod(file_out.fileno(), stat.S_IEXEC)

                        file_out.close()

    elif file_type == "application/zip":
        # PyRight will complain that this doesnt accept str | BytesIO, but doesnt see that it will never get the combo
        with ZipFile(BytesIO(in_file)) as zip:  # type: ignore
            files = zip.infolist()

            for file in files:
                file_path = Path(file.filename)

                if file_path.stem in needles and file_path.suffix in ["", ".exe"]:
                    with open(os.path.join(out_path, file_path.name), "wb") as file_out:
                        file_out.write(zip.read(str(file.filename)))

                        if system == "Linux":
                            os.fchmod(file_out.fileno(), stat.S_IEXEC)

                        file_out.close()
    else:
        return False

    return True


def download(url: str, checksum: str | None = None) -> bytes:
    import requests

    file_request = requests.get(url, stream=True)
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
            file.extend(bytes(block))

    if file_size != 0 and file_progress_bar.n != file_size:
        raise RuntimeError("Unable to download: {}".format(url))

    if hashlib.sha256(file).hexdigest() != checksum:
        raise RuntimeError(
            "{} checksums do not match! Please obtain from trusted source.".format(url)
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
        and shutil.which("fpcalc") is not None
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
        file.close()

    return file_loaded


def ffprobe(file: Path):
    json_packed = ""

    ffprobe_command = [
        shutil.which("ffprobe"),
        "-v",
        "quiet",
        "-show_format",
        "-show_streams",
        "-print_format",
        "json",
        file,
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
    ffmpeg_command = [
        shutil.which("ffmpeg"),
        "-y",
        "-i",
        in_file,
        "-ab",
        "320k",
        "-vcodec",
        "copy",
        "-map_metadata",
        "0",
        "-id3v2_version",
        "3",
        "-progress",
        "pipe:1",
        "-loglevel",
        "error",
        "-f",
        "mp3",
        os.path.join(out_file.parent, file_out_name),
    ]

    # Limit our filenames to 40 chars so it looks uniform
    desc = (in_file.name[:37] + "...") if len(in_file.name) > 40 else in_file.name

    ffprobe_info = ffprobe(in_file)
    status = {}

    with tqdm(
        desc=desc,
        total=round(float(ffprobe_info["streams"][0]["duration"])),
        unit="s",
        # position=,
        bar_format="{desc:<40}: {percentage:3.0f}%|{bar}|{n_fmt}/{total_fmt} [{elapsed}]({rate_fmt}{postfix})",
        leave=True,
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

    return True


files = glob(
    os.path.join(current_working_dir, metronome_settings["input"], "**", "*.flac"),
    recursive=True,
)


# PyRight is hallucinating, this will only ever return an int
threads = int(
    metronome_settings["threads"] if os.cpu_count() is None else os.cpu_count()  # type: ignore
)
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

            file_out_name = f"{file.stem}.mp3"

            # We dont want to cnvert again
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
