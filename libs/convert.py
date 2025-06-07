import os
import shutil
from pathlib import Path
from subprocess import Popen, PIPE, STDOUT
from tqdm import tqdm  # type: ignore
from datetime import datetime
import json


def ffprobe(file: Path, bin_location: str = "bin") -> dict:
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


def ffmpeg(
    in_file: Path,
    out_file: Path,
    file_out_name: str,
    metronome_settings,
    bin_location: str,
    queue,
    logger,
    **kwargs,
) -> bool:
    ffmpeg_path = shutil.which("ffmpeg") or os.path.join(bin_location, "ffmpeg")
    output_format = metronome_settings.get("convert", "mp3")
    if output_format == "opus":
        codec_args = [
            "-c:a",
            "libopus",
            "-b:a",
            "384k",
            "-vbr",
            "on",
            "-compression_level",
            "10",
            "-map_metadata",
            "0",
            "-progress",
            "pipe:1",
            "-loglevel",
            "error",
            "-f",
            "opus",
        ]
        file_out_name = os.path.splitext(file_out_name)[0] + ".opus"
    else:  # mp3
        codec_args = [
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

                if "out_time_us" in stat and "N/A" not in stat[1]:
                    total_time = round(float(status["out_time_us"]) / 1000000)
                    progress.update(total_time - progress.n)

                progress.refresh()

            logger.info(f"Converted {in_file} to {file_out_name}")

            # print(status)
        progress.set_description_str(f"Converted: {desc:<40}")
        progress.close()

    queue.task_done()
    return queue.get()
