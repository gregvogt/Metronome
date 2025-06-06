#!/usr/bin/env python3

import platform

system = platform.system()

if system != "Linux" and system != "Windows":
    raise RuntimeError("{} is not supported.".format(system))

import tempfile
import os
from pathlib import Path
from glob import glob
from tqdm import tqdm  # type: ignore
import atexit
import pathlib
import json
import shutil
from threading import Thread
from queue import Queue

from cli import get_parser
from deps import download, extract
from fileutils import make_dir, is_safe_path, is_safe_filename
from convert import ffmpeg

from logger import setup_logging, logging
from datetime import datetime


def main():
    parser = get_parser()
    args = parser.parse_args()
    metronome_settings = vars(args)

    active_user_dir = pathlib.Path.home()
    metronome_json_settings = os.path.join(active_user_dir, ".metronome.json")

    # Translate CLI debug settings to logging constants
    if metronome_settings.get("log_level") == "debug":
        log_level = logging.DEBUG
    elif metronome_settings.get("log_level") == "warn":
        log_level = logging.ERROR
    else:
        log_level = logging.INFO

    date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    setup_logging("metronome-{}.log".format(date), log_level)
    logging.info("Starting Metronome")

    if os.path.exists(metronome_json_settings):
        try:
            with open(metronome_json_settings, "r") as settings_json:
                file_settings = json.loads(settings_json.read())
                # Only update settings if the CLI value is different from both file and default
                for key, file_value in file_settings.items():
                    cli_value = metronome_settings.get(key)
                    # If CLI value is not set (None) or matches the default, use file value
                    if cli_value is None or cli_value == parser.get_default(key):
                        metronome_settings[key] = file_value
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse settings file: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while loading settings: {e}")

    logging.debug("Metronome settings: %s", metronome_settings)

    @atexit.register
    def termination_handler():
        try:
            with open(metronome_json_settings, "w") as settings_json:
                settings_json.write(json.dumps(metronome_settings))
        except Exception as e:
            logging.error(f"Failed to save settings on exit: {e}")

        logging.info("Metronome terminated gracefully.")

    bin_location = Path(os.getcwd(), "bin")
    current_working_dir = os.getcwd()

    # Ensure input and output are provided
    if not metronome_settings.get("input"):
        logging.error("Input directory not specified.")
        exit(1)
    if not metronome_settings.get("output"):
        logging.error("Output directory not specified.")
        exit(1)

    metronome_settings["input"] = make_dir(metronome_settings["input"])
    metronome_settings["output"] = make_dir(metronome_settings["output"])
    make_dir(str(bin_location))

    if metronome_settings["all"]:
        metronome_settings["sort"] = True
        metronome_settings["convert"] = True
        metronome_settings["analyze"] = True

    try:
        with open("deps.json", "r") as deps_file:
            programs = json.load(deps_file)
    except FileNotFoundError:
        raise RuntimeError(
            "deps.json file not found. Please ensure it exists in the working directory."
        )
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse deps.json: {e}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred while loading deps.json: {e}")

    if (
        metronome_settings["convert"]
        and shutil.which("ffmpeg") is None
        and not os.path.exists(os.path.join(bin_location, "ffmpeg"))
    ):
        ffmpeg_archive = download(
            programs["ffmpeg"][system]["url"], programs["ffmpeg"][system]["checksum"]
        )

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

    # Common music file extensions
    music_extensions = [
        "flac",
        "mp3",
        "wav",
        "aac",
        "ogg",
        "m4a",
        "wma",
        "alac",
        "aiff",
    ]

    # Allow user to specify additional extensions via CLI/settings
    extra_exts = metronome_settings.get("extra_extensions")
    if extra_exts:
        # Split by comma, strip whitespace, and filter out empty strings
        user_exts = [
            ext.strip().lower() for ext in extra_exts.split(",") if ext.strip()
        ]
        music_extensions.extend(
            [ext for ext in user_exts if ext not in music_extensions]
        )
        
    files = []

    for ext in music_extensions:
        for file in glob(
            os.path.join(
                current_working_dir, metronome_settings["input"], "**", f"*.{ext}"
            ),
            recursive=True,
        ):
            # Check for path traversal and unsupported characters
            if not is_safe_path(metronome_settings["input"], file):
                logging.warning(f"Skipping potentially unsafe path: {file}")
                continue
            
            files.append(file)

    try:
        threads = int(metronome_settings.get("threads", 1))
        if threads < 1:
            threads = 1
    except (ValueError, TypeError):
        threads = 1

    thread_list = []
    convert_count = 0

    tqdm.get_lock()

    queue = Queue(maxsize=threads)

    with tqdm(
        desc="Total Files",
        total=len(files),
        position=(threads + 1),
        leave=False,
        ascii=True,
    ) as total_bar:
        index = 0
        for index, file in enumerate(files, 1):
            try:
                # Replace input folder with output to maintain original folder structure in output location
                file_out = Path(
                    file.replace(
                        metronome_settings["input"], metronome_settings["output"]
                    )
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
                    os.makedirs(file_out.parent, exist_ok=True)

                thread = Thread(
                    target=ffmpeg,
                    args=(
                        file,
                        file_out,
                        file_out_name,
                        metronome_settings,
                        bin_location,
                        queue,
                    ),
                )
                queue.put(index)
                thread_list.append(thread)
                thread.start()

                convert_count += 1

                total_bar.update(index - total_bar.n)
                total_bar.refresh()
            except Exception as e:
                tqdm.write(f"Error processing file {file}: {e}")
                logging.error(f"Error processing file {file}: {e}")

        # Join threads back into main to free up Queue
        [thread.join() for thread in thread_list]

    logging.info(f"\nTotal converted files: {convert_count}")


if __name__ == "__main__":
    main()
