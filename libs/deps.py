import os
import requests  # type: ignore
import hashlib
import stat
from io import BytesIO
from pathlib import Path
from typing import List
from tqdm import tqdm  # type: ignore
from sys import platform


def extract(in_file: bytes, out_path: Path, needles: List) -> bool:
    from zipfile import ZipFile  # noqa
    from tarfile import TarFile  # noqa
    import magic  # type: ignore

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

                        if platform == "Linux":
                            os.fchmod(file_out.fileno(), stat.S_IEXEC) # type: ignore

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

                        if platform == "Linux":
                            os.fchmod(file_out.fileno(), stat.S_IEXEC) # type: ignore

                        file_out.close()
    else:
        return False

    return True


def download(url: str, checksum: str | None = None) -> bytes:

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
            "{} checksums do not match! Please obtain from trusted source. {} Expected: {} {} Found: {}".format(
                url, os.linesep, checksum, os.linesep, calculated_checksum
            )
        )

    return bytes(file)
