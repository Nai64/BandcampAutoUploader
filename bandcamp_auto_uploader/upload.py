import dataclasses
import html
from io import BufferedReader
import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import mutagen
import requests
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE
try:
    from rich.logging import RichHandler
    _rich_handler = RichHandler()
except ImportError:
    _rich_handler = None

from bandcamp_auto_uploader.config import Config

logger = logging.getLogger("bandcamp-auto-uploader")
logger.setLevel(logging.INFO)
logger.addHandler(_rich_handler or logging.StreamHandler())


class UploadCancelled(RuntimeError):
    """Raised when the GUI requests a graceful upload cancellation."""


def _log_response_summary(label: str, response: requests.Response) -> None:
    """Log response shape without leaking page bodies, upload params, or crumbs."""
    content_type = response.headers.get("content-type", "unknown")
    logger.debug(
        "%s: status=%s bytes=%s content_type=%s",
        label,
        response.status_code,
        len(response.content or b""),
        content_type,
    )


def get_audio_sample_rate(audio_path: Path) -> Optional[int]:
    """Return sample rate in Hz when available, otherwise None."""
    file_data = mutagen.File(audio_path)
    if file_data is None or not hasattr(file_data, "info"):
        return None
    return getattr(file_data.info, "sample_rate", None)


def get_audio_bit_depth(audio_path: Path) -> Optional[int]:
    """Return bit depth in bits when available, otherwise None."""
    file_data = mutagen.File(audio_path)
    if file_data is None or not hasattr(file_data, "info"):
        return None
    return getattr(file_data.info, "bits_per_sample", None)


def needs_conversion_to_flac(audio_path: Path) -> bool:
    """Check if audio file needs conversion to FLAC 16-bit 44.1kHz.
    
    Returns True if:
    - Sample rate < 44.1kHz
    - Bit depth < 16 bits
    - Format is not FLAC
    """
    sample_rate = get_audio_sample_rate(audio_path)
    bit_depth = get_audio_bit_depth(audio_path)
    
    # Convert if sample rate is less than 44.1kHz
    if sample_rate is not None and sample_rate < 44100:
        logger.info(f"Sample rate {sample_rate}Hz < 44.1kHz - conversion needed")
        return True
    
    # Convert if bit depth is less than 16 bits
    if bit_depth is not None and bit_depth < 16:
        logger.info(f"Bit depth {bit_depth} bits < 16 bits - conversion needed")
        return True
    
    # Convert if format is not FLAC (MP3, WAV, AIFF, etc.)
    if audio_path.suffix.lower() != '.flac':
        logger.info(f"Format {audio_path.suffix} is not FLAC - conversion needed")
        return True
    
    return False


def convert_to_flac_16bit_44khz(audio_path: Path) -> Path:
    """Convert any audio file to FLAC 16-bit 44.1kHz stereo.

    Args:
        audio_path: Path to audio file

    Returns:
        Path to converted FLAC file

    Raises:
        RuntimeError: If ffmpeg is not found or conversion fails
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg is required to convert audio files. "
            "Please install ffmpeg and ensure it's in your PATH. "
            "Download from: https://ffmpeg.org/download.html"
        )

    # Create output path with .flac extension
    # If input is already .flac, use a temporary file to avoid in-place editing
    if audio_path.suffix.lower() == '.flac':
        import tempfile
        temp_dir = Path(tempfile.gettempdir())
        flac_path = temp_dir / f"{audio_path.stem}_converted.flac"
    else:
        flac_path = audio_path.with_suffix(".flac")
    
    # Build ffmpeg command
    # -i: input file
    # -ar 44100: sample rate 44.1kHz
    # -ac 2: stereo (2 channels)
    # -sample_fmt s16: 16-bit
    # -compression_level 0: FLAC compression level 0 (fastest)
    # -y: overwrite output file if exists
    cmd = [
        "ffmpeg",
        "-i", str(audio_path),
        "-ar", "44100",
        "-ac", "2",
        "-sample_fmt", "s16",
        "-compression_level", "0",
        "-y",
        str(flac_path)
    ]
    
    logger.info(f"Converting {audio_path.name} to FLAC 16-bit 44.1kHz")
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=300  # 5 minute timeout
        )
        logger.info(f"Conversion complete - {flac_path.name}")
        return flac_path
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Conversion timed out for {audio_path.name}")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore')
        raise RuntimeError(f"Conversion failed for {audio_path.name}: {error_msg}")



@dataclasses.dataclass
class BandcampAlbumData:
    id: str = ""
    title: str = ""
    release_date: str = ""
    price: str = "0.00"
    nyp: int = 1
    label_id: int = 0
    label_name: str = ""
    new_desc_format: int = 1
    download_desc: str = ""
    art_id: str = ""
    artist: str = ""
    about: str = ""
    credits: str = ""
    tags: str = ""
    upc: str = ""
    cat_number: str = ""
    public: int = 1
    tralbum_release_message: str = ""
    subscriber_only_message: str = ""
    require_email: int = 0
    pro: int = 0
    composer: str = ""
    publisher: str = ""

    def to_dict(self) -> dict:
        d = {}
        for k, v in dataclasses.asdict(self).items():
            k = f"album.{k}"
            d[k] = v
        return d


@dataclasses.dataclass
class BandcampTrackData:
    id: str = ""
    track_number: int = 1
    action: str = "edit"
    featured: int = 0
    title: str = "track 1"
    streaming: int = 1
    enable_download: int = 1
    price: str = "1.50"
    nyp: int = 1
    label_id: int = 0
    new_desc_format: int = 1
    download_desc: str = ""
    about: str = ""
    lyrics: str = ""
    credits: str = ""
    video_id: str = ""
    video_filename: str = ""
    video_delete: str = ""
    video_caption: str = ""
    artist: str = ""
    art_id: str = ""
    tags: str = ""
    license_type: str = "1"
    isrc: str = ""
    iswc: str = ""
    release_date: str = ""
    encodings_id: str = ""
    require_email: int = 0
    private: int = 0

    def to_dict(self, track_number: int) -> dict:
        d = {}
        for k, v in dataclasses.asdict(self).items():
            if k.startswith("video"):
                k = k.replace("_", "-")
            k = f"track.{k}_{track_number}"
            d[k] = v
        return d


def post_request_with_crumb(
    session: requests.Session,
    url: str,
    data: dict,
    max_retries: int = 3,
    cancel_event=None,
) -> Any:
    """Post request with CSRF token handling and retry logic for 403 errors.
    
    Args:
        session: Authenticated requests session
        url: Target URL
        data: POST data including crumb
        max_retries: Maximum number of retry attempts for transient errors
    
    Returns:
        JSON response from the server
    
    Raises:
        requests.exceptions.HTTPError: If request fails after all retries
    """
    last_exception = None

    def check_cancelled():
        if cancel_event is not None and cancel_event.is_set():
            raise UploadCancelled("Upload cancelled by user")
    
    for attempt in range(max_retries):
        try:
            check_cancelled()
            r = session.post(url, data=data)
            check_cancelled()
            _log_response_summary("Bandcamp API response", r)
            r.raise_for_status()
            res = r.json()
            
            # Handle invalid crumb by updating with server-provided crumb
            if res.get("error") == "invalid_crumb":
                logger.warning("Invalid crumb detected, updating with server-provided crumb...")
                data["crumb"] = res["crumb"]
                check_cancelled()
                r = session.post(url, data=data)
                check_cancelled()
                _log_response_summary("Bandcamp API retry response", r)
                r.raise_for_status()
                res = r.json()
            
            return res
            
        except requests.exceptions.HTTPError as e:
            last_exception = e
            
            # Handle 403 Forbidden errors
            if e.response.status_code == 403:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff: 2, 4, 8 seconds
                    logger.warning(
                        f"403 Forbidden error on attempt {attempt + 1}/{max_retries}. "
                        f"This may indicate an expired session or rate limiting. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    if cancel_event is not None and cancel_event.wait(wait_time):
                        raise UploadCancelled("Upload cancelled by user")
                else:
                    logger.error(
                        f"403 Forbidden error after {max_retries} attempts. "
                        f"Possible causes:\n"
                        f"  - Session expired (try logging in again)\n"
                        f"  - Invalid CSRF token (crumb)\n"
                        f"  - Bandcamp detected automation and blocked the request\n"
                        f"  - Rate limiting (too many requests too quickly)\n"
                        f"  - Insufficient permissions for this account"
                    )
                    raise
            else:
                # For non-403 errors, raise immediately
                raise
    
    # If we exhausted all retries, raise the last exception
    if last_exception:
        raise last_exception


def get_metadata_track_number(audio_path: Path) -> Optional[int]:
    """Read a track number directly from audio metadata when available."""
    try:
        file_data = mutagen.File(audio_path)
    except Exception:
        return None

    if file_data is None:
        return None

    raw_value = None
    if "tracknumber" in file_data:
        value = file_data["tracknumber"]
        raw_value = value[0] if isinstance(value, list) and value else value
    elif "TRCK" in file_data:
        value = file_data["TRCK"]
        raw_value = value.text[0] if hasattr(value, "text") and value.text else value

    if raw_value is None:
        return None

    try:
        return int(str(raw_value).split("/")[0].strip())
    except (TypeError, ValueError):
        return None


UPLOADED_FILE_KEY_REGEX = re.compile(r"<Key>(?P<key>[^<]*)</Key>")


def upload_file(
    session: requests.Session,
    artist_url: str,
    file_name: str,
    crumbs: dict,
    api_path: str,
    file_path: Optional[Path] = None,
    file_data: Optional[bytes] = None,
    max_retries: int = 3,
    timeout: int = 300,
    retry_delay: int = 5,
    cancel_event=None,
):
    def check_cancelled():
        if cancel_event is not None and cancel_event.is_set():
            raise UploadCancelled("Upload cancelled by user")

    file_name = file_name.encode().decode("ascii", errors="replace")
    logger.info(f"Uploading file - {file_name}")
    
    # get upload params
    upload_params_url = urljoin(artist_url, "api/gcsupload_info/1/get_upload_params")
    check_cancelled()
    r = session.post(upload_params_url, json={"filename": file_name})
    check_cancelled()
    _log_response_summary("Upload params response", r)
    r.raise_for_status()
    data = r.json()
    logger.debug("Upload params received")
    gcs_url = data["url"]
    params = {param["key"]: param["value"] for param in data["params"]}

    # upload file with retry logic for SSL errors
    last_exception = None
    for attempt in range(max_retries):
        try:
            check_cancelled()
            start_time = time.time()
            multipart_form_data: dict[str, tuple[str | None, bytes | BufferedReader]] = {
                k: (None, v) for k, v in params.items()
            }
            if file_data is not None:
                multipart_form_data["file"] = (file_name, file_data)
                r = session.post(gcs_url, files=multipart_form_data, timeout=timeout)
                check_cancelled()
                r.raise_for_status()
            elif file_path is not None:
                with open(file_path, "rb") as f:
                    multipart_form_data["file"] = (file_name, f)
                    r = session.post(gcs_url, files=multipart_form_data, timeout=timeout)
                    check_cancelled()
                    _log_response_summary("Storage upload response", r)
                    r.raise_for_status()
            else:
                raise ValueError("Either file_path or file_data must be specified")
            duration = time.time() - start_time
            _log_response_summary("Storage upload complete", r)

            m = UPLOADED_FILE_KEY_REGEX.search(r.text)
            if m is None:
                raise ValueError("Could not find uploaded file key")
            uploaded_file_key = m.group("key")
            uploaded_file_key = html.unescape(uploaded_file_key)

            # tell api we uploaded file
            uploaded_file_data = {
                "type": "gcs",
                "filename": file_name,
                "key": uploaded_file_key,
                "duration": int(duration * 1000),
                "crumb": crumbs[api_path],
            }
            uploaded_track_url = urljoin(artist_url, api_path)
            r = post_request_with_crumb(
                session,
                uploaded_track_url,
                uploaded_file_data,
                cancel_event=cancel_event,
            )
            logger.info(f"File uploaded in {duration:.2f} seconds")
            logger.debug("Uploaded file API returned keys: %s", sorted(r.keys()))
            return r
            
        except requests.exceptions.SSLError as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.warning(
                    f"SSL error on attempt {attempt + 1}/{max_retries}: {e}. "
                    f"Retrying in {retry_delay} seconds..."
                )
                if cancel_event is not None and cancel_event.wait(retry_delay):
                    raise UploadCancelled("Upload cancelled by user")
            else:
                logger.error(
                    f"SSL error after {max_retries} attempts. "
                    f"This may be a network issue or temporary server problem."
                )
                raise
        except requests.exceptions.ConnectionError as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.warning(
                    f"Connection error on attempt {attempt + 1}/{max_retries}: {e}. "
                    f"Retrying in {retry_delay} seconds..."
                )
                if cancel_event is not None and cancel_event.wait(retry_delay):
                    raise UploadCancelled("Upload cancelled by user")
            else:
                logger.error(f"Connection error after {max_retries} attempts: {e}")
                raise
    
    # If we exhausted all retries, raise the last exception
    if last_exception:
        raise last_exception



class CoverArt:
    def __init__(
        self,
        path: Optional[Path] = None,
        data: Optional[bytes] = None,
        file_name: Optional[str] = None,
    ):
        self.path = path
        self.data = data

        if path is not None:
            self.file_name = path.name
        else:
            assert file_name is not None
            self.file_name = file_name

        if path is None and (data is None or file_name is None):
            raise ValueError(
                "Either file path or data and name must be initialized for cover art"
            )

    def upload(
        self,
        session: requests.Session,
        artist_url: str,
        crumbs: dict,
        timeout: int = 300,
        retry_delay: int = 5,
        cancel_event=None,
    ) -> str:
        if self.path is not None:
            r = upload_file(
                session,
                artist_url,
                self.file_name,
                crumbs,
                "tralbum_art_uploaded",
                file_path=self.path,
                timeout=timeout,
                retry_delay=retry_delay,
                cancel_event=cancel_event,
            )
        else:
            r = upload_file(
                session,
                artist_url,
                self.file_name,
                crumbs,
                "tralbum_art_uploaded",
                file_data=self.data,
                timeout=timeout,
                retry_delay=retry_delay,
                cancel_event=cancel_event,
            )
        if r.get("error"):
            raise ValueError(r.get("deets"))
        return r["art_id"]


class Track:
    def __init__(
        self,
        path: Path,
        track_data: BandcampTrackData,
        cover_art: Optional[CoverArt] = None,
        config: Optional[Config] = None,
    ):
        self.path = path
        self.file_name = self.path.name  # Keep extension for upload
        self.track_data = track_data
        self.cover_art = cover_art
        self.config = config
        self.converted_file_path = None  # Track converted MP3->FLAC files for cleanup

    @classmethod
    def from_file(cls, path: Path, config: Config):
        path = Path(path)

        try:
            file_data = mutagen.File(path)
        except Exception as e:
            logger.warning(f"Skipping unreadable audio file {path.name}: {e}")
            return None
        if file_data is None:
            ext = path.suffix.lower()
            if ext in ('.mod', '.xm'):
                track_data = BandcampTrackData(
                    price=str(config.track_price),
                    nyp=int(config.name_your_price),
                    enable_download=int(config.track_downloading),
                    streaming=int(config.track_streaming),
                )
                track_data.title = path.stem
                return cls(path=path, track_data=track_data, cover_art=None, config=config)
            return None
        
        track_data = BandcampTrackData(
            price=str(config.track_price),
            nyp=int(config.name_your_price),
            enable_download=int(config.track_downloading),
            streaming=int(config.track_streaming),
        )
        
        # Accept WAV, FLAC, AIFF, MP3, OGG, Opus, and M4A/AAC (non-FLAC will be converted during upload)
        if file_data.__class__ not in (WAVE, FLAC, AIFF, MP3, OggVorbis, OggOpus, MP4):
            raise ValueError("Only WAV, FLAC, AIFF, MP3, OGG, Opus, and M4A/AAC files are supported")
        cover_art = None
        
        # If ignore_all_metadata is enabled, only use filename and skip all metadata reading
        if getattr(config, 'ignore_all_metadata', False):
            track_data.title = path.stem
            # NEVER extract embedded artwork - use only manually added cover art
            cover_art = None
            return cls(path=path, track_data=track_data, cover_art=cover_art, config=config)

        if file_data.__class__ == FLAC:
            # FLAC Vorbis comment tags
            if getattr(config, 'use_filename_as_title', False):
                # Force use filename
                track_data.title = path.stem
            elif "title" in file_data and file_data["title"]:
                # Extract string from list
                title = str(file_data["title"][0]) if isinstance(file_data["title"], list) else str(file_data["title"])
                # Strip audio extensions if present
                for ext in ['.flac', '.wav', '.aiff', '.mp3', '.m4a', '.aac', '.ogg', '.opus', '.mod', '.xm']:
                    if title.lower().endswith(ext):
                        title = title[:-len(ext)]
                        break
                track_data.title = title
            else:
                track_data.title = path.stem
            if "artist" in file_data and not getattr(config, 'ignore_artist_name', False):
                track_data.artist = file_data["artist"][0]
            if "tracknumber" in file_data:
                track_data.track_number = file_data["tracknumber"][0]
            if "comment" in file_data:
                track_data.about = file_data["comment"][0]
            if "genre" in file_data:
                track_data.tags = ",".join(file_data["genre"])
            if "isrc" in file_data:
                track_data.isrc = file_data["isrc"][0]
            # NEVER extract embedded artwork - use only manually added cover art
            cover_art = None
        elif file_data.__class__ == MP3:
            # MP3 ID3 tags
            if getattr(config, 'use_filename_as_title', False):
                # Force use filename
                track_data.title = path.stem
            elif "TIT2" in file_data and file_data["TIT2"].text:
                # Extract title string
                title = str(file_data["TIT2"].text[0])
                # Strip audio extensions if present
                for ext in ['.flac', '.wav', '.aiff', '.mp3', '.m4a', '.aac', '.ogg', '.opus', '.mod', '.xm']:
                    if title.lower().endswith(ext):
                        title = title[:-len(ext)]
                        break
                track_data.title = title
            else:
                track_data.title = path.stem
            if "TPE1" in file_data and not getattr(config, 'ignore_artist_name', False):
                track_data.artist = file_data["TPE1"].text[0]
            if "TRCK" in file_data:
                track_data.track_number = file_data["TRCK"].text[0]
            if "TCON" in file_data:
                track_data.tags = ",".join(file_data["TCON"].text)
            if "TSRC" in file_data:
                track_data.isrc = file_data["TSRC"].text[0]
            if "USLT" in file_data:
                track_data.lyrics = file_data["USLT"].text[0]
            if file_data.tags is not None:
                comments = file_data.tags.getall("COMM")
                if len(comments) > 0:
                    track_data.about = comments[0].text[0]
                # NEVER extract embedded artwork - use only manually added cover art
                cover_art = None
        elif file_data.__class__ == OggVorbis or file_data.__class__ == OggOpus:
            # OGG Vorbis / Opus Vorbis comment tags (same as FLAC)
            if getattr(config, 'use_filename_as_title', False):
                track_data.title = path.stem
            elif "title" in file_data and file_data["title"]:
                title = str(file_data["title"][0]) if isinstance(file_data["title"], list) else str(file_data["title"])
                for ext in ['.flac', '.wav', '.aiff', '.mp3', '.m4a', '.ogg', '.opus', '.mod', '.xm']:
                    if title.lower().endswith(ext):
                        title = title[:-len(ext)]
                        break
                track_data.title = title
            else:
                track_data.title = path.stem
            if "artist" in file_data and not getattr(config, 'ignore_artist_name', False):
                track_data.artist = file_data["artist"][0]
            if "tracknumber" in file_data:
                track_data.track_number = file_data["tracknumber"][0]
            if "comment" in file_data:
                track_data.about = file_data["comment"][0]
            if "genre" in file_data:
                track_data.tags = ",".join(file_data["genre"])
            if "isrc" in file_data:
                track_data.isrc = file_data["isrc"][0]
            cover_art = None
        elif file_data.__class__ == MP4:
            # MP4/M4A tags
            if getattr(config, 'use_filename_as_title', False):
                track_data.title = path.stem
            elif "\xa9nam" in file_data and file_data["\xa9nam"]:
                title = str(file_data["\xa9nam"][0])
                for ext in ['.flac', '.wav', '.aiff', '.mp3', '.m4a', '.aac', '.ogg', '.opus', '.mod', '.xm']:
                    if title.lower().endswith(ext):
                        title = title[:-len(ext)]
                        break
                track_data.title = title
            else:
                track_data.title = path.stem
            if "\xa9ART" in file_data and not getattr(config, 'ignore_artist_name', False):
                track_data.artist = str(file_data["\xa9ART"][0])
            if "trkn" in file_data and file_data["trkn"]:
                track_data.track_number = str(file_data["trkn"][0][0])
            if "\xa9cmt" in file_data:
                track_data.about = str(file_data["\xa9cmt"][0])
            if "\xa9gen" in file_data:
                track_data.tags = ",".join(str(g) for g in file_data["\xa9gen"])
            cover_art = None
        else:
            # WAV/AIFF id3 tags
            if getattr(config, 'use_filename_as_title', False):
                track_data.title = path.stem
            elif "TIT2" in file_data and file_data["TIT2"].text:
                title = str(file_data["TIT2"].text[0])
                for ext in ['.flac', '.wav', '.aiff', '.mp3', '.m4a', '.aac', '.ogg', '.opus', '.mod', '.xm']:
                    if title.lower().endswith(ext):
                        title = title[:-len(ext)]
                        break
                track_data.title = title
            else:
                track_data.title = path.stem
            if "TPE1" in file_data and not getattr(config, 'ignore_artist_name', False):
                track_data.artist = file_data["TPE1"].text[0]
            if "TRCK" in file_data:
                track_data.track_number = file_data["TRCK"].text[0]
            if "TCON" in file_data:
                track_data.tags = ",".join(file_data["TCON"].text)
            if "TSRC" in file_data:
                track_data.isrc = file_data["TSRC"].text[0]
            if "USLT" in file_data:
                track_data.lyrics = file_data["USLT"].text[0]
            if file_data.tags is not None:
                comments = file_data.tags.getall("COMM")
                if len(comments) > 0:
                    track_data.about = comments[0].text[0]
                # NEVER extract embedded artwork - use only manually added cover art
                cover_art = None
        # Extract embedded cover art from track if enabled
        if cover_art is None and getattr(config, 'extract_embedded_cover_art', False):
            cover_data = None
            cover_ext = '.jpg'
            if hasattr(file_data, 'pictures') and file_data.pictures:
                picture = file_data.pictures[0]
                cover_data = picture.data
                cover_ext = '.png' if 'png' in (picture.mime or '') else '.jpg'
            elif file_data.tags is not None:
                pictures = file_data.tags.getall("APIC")
                if pictures:
                    cover_data = pictures[0].data
                    cover_ext = '.png' if 'png' in (pictures[0].mime or '') else '.jpg'
            elif 'covr' in file_data:
                cover = file_data['covr'][0]
                cover_data = bytes(cover)
                cover_ext = '.png' if cover_data[:8] == b'\x89PNG\r\n\x1a\n' else '.jpg'
            if cover_data:
                cover_name = f"{path.stem}_cover{cover_ext}"
                cover_art = CoverArt(data=cover_data, file_name=cover_name)

        # convert track number to int
        if not isinstance(track_data.track_number, int):
            try:
                track_data.track_number = int(track_data.track_number.split("/")[0])
            except (ValueError, AttributeError):
                track_data.track_number = 0
        return cls(path, track_data, cover_art, config=config)

    def upload(
        self,
        session: requests.Session,
        artist_url: str,
        crumbs: dict,
        timeout: int = 300,
        retry_delay: int = 5,
        cancel_event=None,
        emit_progress=None,
        track_index=0,
    ):
        if cancel_event is not None and cancel_event.is_set():
            raise UploadCancelled("Upload cancelled by user")

        upload_path = self.path
        
        # Convert to FLAC 16-bit 44.1kHz if needed
        if getattr(self.config, 'enable_flac_conversion', False) and needs_conversion_to_flac(self.path):
            logger.info(f"Converting to FLAC 16-bit 44.1kHz before upload - {self.path.name}")
            try:
                upload_path = convert_to_flac_16bit_44khz(self.path)
                self.converted_file_path = upload_path  # Store for cleanup after upload
                logger.info(f"Conversion successful - {upload_path.name}")
                if emit_progress:
                    emit_progress("conversion_done", index=track_index, title=self.track_data.title, file_name=self.path.name)
            except Exception as e:
                logger.error(f"Failed to convert to FLAC - {e}")
                raise

        if cancel_event is not None and cancel_event.is_set():
            raise UploadCancelled("Upload cancelled by user")
        
        # Use filename without extension for upload metadata so Bandcamp doesn't use extension as title
        clean_filename = upload_path.stem
        r = upload_file(
            session,
            artist_url,
            clean_filename,
            crumbs,
            "uploaded_track",
            file_path=upload_path,
            timeout=timeout,
            retry_delay=retry_delay,
            cancel_event=cancel_event,
        )
        self.track_data.encodings_id = r["encodings"]["id"]

        # Small delay to avoid rate limiting
        time.sleep(1)

        # upload cover art
        if self.cover_art is not None:
            cover_art_id = self.cover_art.upload(session, artist_url, crumbs, timeout=timeout, retry_delay=retry_delay)
            self.track_data.art_id = cover_art_id
    
    def cleanup_converted_file(self):
        """Delete temporary converted file if one was created for upload."""
        if self.converted_file_path and self.converted_file_path.exists():
            try:
                logger.info(f"Deleting temporary converted file - {self.converted_file_path.name}")
                self.converted_file_path.unlink()
                logger.info(f"Successfully deleted - {self.converted_file_path.name}")
            except Exception as e:
                logger.warning(f"Failed to delete converted file {self.converted_file_path.name}: {e}")
            finally:
                self.converted_file_path = None


class Album:
    CRUMB_DATA_REGEX = re.compile(
        r'<meta id="js-crumbs-data" data-crumbs="(?P<crumbs>[^>]*)">'
    )

    def __init__(
        self,
        album_data: BandcampAlbumData,
        tracks: list[Track],
        cover_art: Optional[CoverArt] = None,
    ):
        self.album_data = album_data
        self.tracks = tracks
        self.cover_art = cover_art

    @staticmethod
    def album_title_to_slug(title: str) -> str:
        """Build a Bandcamp-style public album slug fallback from a title."""
        slug = html.unescape(str(title or "")).strip().lower()
        slug = re.sub(r"[^\w]+", "-", slug, flags=re.UNICODE)
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug or "album"

    @classmethod
    def build_public_album_url(cls, artist_url: str, title: str) -> str:
        """Build the likely public album URL when Bandcamp does not return one."""
        base_url = artist_url.rstrip("/") + "/"
        return urljoin(base_url, f"album/{cls.album_title_to_slug(title)}")

    @staticmethod
    def build_edit_album_url(artist_url: str, album_id: str | int | None) -> str | None:
        """Build an edit URL from the created album id."""
        if not album_id:
            return None
        base_url = artist_url.rstrip("/") + "/"
        return urljoin(base_url, f"edit_album?id={album_id}")

    @classmethod
    def extract_album_url_from_response(cls, response: Any, artist_url: str) -> str | None:
        """Find a public album URL in a Bandcamp JSON response, if one is present."""
        preferred_keys = {
            "url",
            "item_url",
            "public_url",
            "album_url",
            "tralbum_url",
            "canonical_url",
        }

        def normalize_url(value: str) -> str | None:
            value = value.strip()
            if not value or "/album/" not in value:
                return None
            if value.startswith(("http://", "https://")):
                return value
            return urljoin(artist_url.rstrip("/") + "/", value.lstrip("/"))

        def walk(value: Any) -> str | None:
            if isinstance(value, dict):
                for key in preferred_keys:
                    if key in value and isinstance(value[key], str):
                        found = normalize_url(value[key])
                        if found:
                            return found
                for child in value.values():
                    found = walk(child)
                    if found:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = walk(child)
                    if found:
                        return found
            elif isinstance(value, str):
                return normalize_url(value)
            return None

        return walk(response)

    AUDIO_EXTENSIONS = {'.wav', '.flac', '.aiff', '.aif', '.mp3', '.ogg', '.opus', '.m4a', '.aac', '.mod', '.xm'}

    @classmethod
    def from_directory(cls, path: Path, config: Config):
        path = Path(path)
        if not path.is_dir():
            raise ValueError("Album to upload must be a directory")
        album_data = BandcampAlbumData(
            title=path.name,
            price=str(config.album_price),
            nyp=int(config.name_your_price),
        )
        tracks = []
        skipped_paths: list[Path] = []
        seen_stems = set()  # Track file stems to avoid MP3/FLAC duplicates

        # Process all files in directory in file system order, then prioritize embedded track numbers.
        for file_index, file in enumerate(path.iterdir()):
            if not file.is_file():
                continue
            if file.suffix.lower() not in cls.AUDIO_EXTENSIONS:
                continue
            # Skip if we already have a file with this stem (name without extension)
            file_stem = file.stem
            if file_stem in seen_stems:
                continue

            # If this is an MP3 and a FLAC with the same name exists, prefer FLAC
            if file.suffix.lower() == '.mp3':
                potential_flac = file.with_suffix('.flac')
                if potential_flac.exists():
                    logger.info(f"Found both {file.name} and {potential_flac.name} - using FLAC")
                    # Process the FLAC instead
                    track = Track.from_file(potential_flac, config)
                    if track is not None:
                        tracks.append((file_index, track))
                        seen_stems.add(file_stem)
                    continue

            # Process the file normally
            track = Track.from_file(file, config)
            if track is not None:
                tracks.append((file_index, track))
                seen_stems.add(file_stem)
            else:
                skipped_paths.append(file)

        tracks.sort(
            key=lambda item: (
                get_metadata_track_number(item[1].path) is None,
                get_metadata_track_number(item[1].path) or 0,
                item[0],
                item[1].path.name.casefold(),
            )
        )
        tracks = [track for _file_index, track in tracks]

        cover_art = None
        for file in path.iterdir():
            if not file.is_file():
                continue
            s = str(file).lower()
            if s[-4:] in (".jpg", ".png", ".gif") or s[-5:] == ".jpeg":
                cover_art = CoverArt(path=file)
                break
        album = cls(album_data, tracks, cover_art)
        album.skipped_paths = skipped_paths
        return album

    def _fetch_crumbs(self, session: requests.Session, artist_url: str) -> dict:
        """Fetch fresh CSRF tokens (crumbs) from Bandcamp.
        
        Args:
            session: Authenticated requests session
            artist_url: Artist's Bandcamp URL
        
        Returns:
            Dictionary of crumbs for various API endpoints
        
        Raises:
            ValueError: If crumbs cannot be found in the page
            requests.exceptions.HTTPError: If request fails
        """
        logger.info("Fetching fresh crumbs")
        create_album_url = urljoin(artist_url, "edit_album")
        
        # Ensure session has proper headers
        if 'User-Agent' not in session.headers:
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
        
        # Add additional headers that Bandcamp expects
        session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Cache-Control': 'max-age=0'
        })
        
        r = session.get(create_album_url)
        _log_response_summary("Crumb page response", r)
        r.raise_for_status()
        
        # Validate session by checking if we're still logged in
        if "login" in r.url.lower() or "signin" in r.url.lower():
            raise ValueError(
                "Session appears to be invalid - redirected to login page. "
                "Please check your cookies and ensure you're properly authenticated."
            )
        
        m = self.CRUMB_DATA_REGEX.search(r.text)
        if m is None:
            raise ValueError(
                "Could not find crumbs in the page. "
                "This may indicate an invalid session or that Bandcamp's page structure has changed."
            )
        
        crumbs = m.group("crumbs")
        crumbs = json.loads(html.unescape(crumbs))
        logger.info("Got crumbs")
        logger.debug("Crumb keys received: %s", sorted(crumbs.keys()))
        return crumbs
    
    def upload(
        self,
        session: requests.Session,
        artist_url: str,
        timeout: int = 300,
        retry_delay: int = 5,
        retry_failed: bool = False,
        retry_attempts: int = 3,
        progress_callback=None,
        cancel_event=None,
    ):
        logger.info("Starting album upload")

        def emit_progress(event: str, **payload):
            if progress_callback is None:
                return
            try:
                progress_callback(event, payload)
            except Exception as e:
                logger.debug(f"Upload progress callback failed: {e}")

        def check_cancelled():
            if cancel_event is not None and cancel_event.is_set():
                emit_progress("album_cancelled", message="Upload cancelled by user")
                raise UploadCancelled("Upload cancelled by user")

        emit_progress("album_start", total=len(self.tracks))
        check_cancelled()
        crumbs = self._fetch_crumbs(session, artist_url)
        check_cancelled()

        # upload cover art
        if self.cover_art is not None:
            logger.info("Uploading cover art")
            emit_progress("cover_start", message="Uploading cover art")
            cover_art_id = self.cover_art.upload(
                session,
                artist_url,
                crumbs,
                timeout=timeout,
                retry_delay=retry_delay,
                cancel_event=cancel_event,
            )
            check_cancelled()
            self.album_data.art_id = cover_art_id
            emit_progress("cover_done", message="Cover art uploaded")

        # save changes to album
        bandcamp_data = {
            "paypal_aware": "",
            "action": "save",
            "publish_campaign": "false",
            "crumb": crumbs["edit_album_cb"],
        }
        bandcamp_data.update(self.album_data.to_dict())
        edit_album_cb_url = urljoin(artist_url, "edit_album_cb")
        logger.info("Saving changes to album")
        check_cancelled()
        r = post_request_with_crumb(
            session,
            edit_album_cb_url,
            bandcamp_data,
            cancel_event=cancel_event,
        )
        check_cancelled()
        initial_album_response = r
        latest_album_response = r
        album_id = r["album"]["id"]
        logger.info(f"Saved changes to album. ID = {album_id}")
        bandcamp_data["album.id"] = album_id

        successful_tracks = 0

        for i, track in enumerate(self.tracks):
            check_cancelled()
            logger.info(f"Uploading track {i + 1}/{len(self.tracks)}: {track.track_data.title}")
            emit_progress(
                "track_start",
                index=i,
                total=len(self.tracks),
                title=track.track_data.title,
                file_name=track.path.name,
                progress=10,
                status="Uploading"
            )

            track_uploaded = False
            for attempt in range(retry_attempts if retry_failed else 1):
                try:
                    check_cancelled()
                    try:
                        track.upload(
                            session,
                            artist_url,
                            crumbs,
                            timeout=timeout,
                            retry_delay=retry_delay,
                            cancel_event=cancel_event,
                            emit_progress=emit_progress,
                            track_index=i,
                        )
                        check_cancelled()
                        logger.info("Track uploaded")
                        emit_progress(
                            "track_uploaded",
                            index=i,
                            total=len(self.tracks),
                            title=track.track_data.title,
                            file_name=track.path.name,
                            progress=65,
                            status="Saving metadata"
                        )
                        track_uploaded = True
                        break
                    except UploadCancelled:
                        track.cleanup_converted_file()
                        raise
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 403:
                            logger.warning("Got 403 error during track upload. Refreshing crumbs and retrying...")
                            check_cancelled()
                            crumbs = self._fetch_crumbs(session, artist_url)
                            bandcamp_data["crumb"] = crumbs["edit_album_cb"]
                            check_cancelled()
                            track.upload(
                                session,
                                artist_url,
                                crumbs,
                                timeout=timeout,
                                retry_delay=retry_delay,
                                cancel_event=cancel_event,
                                emit_progress=emit_progress,
                                track_index=i,
                            )
                            check_cancelled()
                            logger.info("Track uploaded after retry")
                            emit_progress(
                                "track_uploaded",
                                index=i,
                                total=len(self.tracks),
                                title=track.track_data.title,
                                file_name=track.path.name,
                                progress=65,
                                status="Saving metadata"
                            )
                            track_uploaded = True
                            break
                        elif e.response.status_code == 429:
                            logger.warning(
                                f"Skipping track due to 429 rate limit: {track.track_data.title} ({track.path.name})"
                            )
                            emit_progress(
                                "track_skipped",
                                index=i,
                                total=len(self.tracks),
                                title=track.track_data.title,
                                file_name=track.path.name,
                                progress=100,
                                status="Skipped: rate limited"
                            )
                            break
                        else:
                            if retry_failed and attempt < retry_attempts - 1:
                                logger.warning(
                                    f"Upload error {e.response.status_code} on attempt {attempt + 1}/{retry_attempts}: {track.track_data.title} ({track.path.name}). Retrying in {retry_delay} seconds..."
                                )
                                if cancel_event is not None and cancel_event.wait(retry_delay):
                                    raise UploadCancelled("Upload cancelled by user")
                            else:
                                logger.warning(
                                    f"Skipping track due to upload error {e.response.status_code}: {track.track_data.title} ({track.path.name})"
                                )
                                emit_progress(
                                    "track_skipped",
                                    index=i,
                                    total=len(self.tracks),
                                    title=track.track_data.title,
                                    file_name=track.path.name,
                                    progress=100,
                                    status=f"Skipped: HTTP {e.response.status_code}"
                                )
                                break
                    except UploadCancelled:
                        track.cleanup_converted_file()
                        raise
                    except Exception as e:
                        if retry_failed and attempt < retry_attempts - 1:
                            logger.warning(
                                f"Upload error on attempt {attempt + 1}/{retry_attempts}: {track.track_data.title} ({track.path.name}): {e}. Retrying in {retry_delay} seconds..."
                            )
                            if cancel_event is not None and cancel_event.wait(retry_delay):
                                raise UploadCancelled("Upload cancelled by user")
                        else:
                            logger.warning(
                                f"Skipping track due to error: {track.track_data.title} ({track.path.name}): {e}"
                            )
                            emit_progress(
                                "track_skipped",
                                index=i,
                                total=len(self.tracks),
                                title=track.track_data.title,
                                file_name=track.path.name,
                                progress=100,
                                status="Skipped: error"
                            )
                            break
                except UploadCancelled:
                    track.cleanup_converted_file()
                    raise
                except Exception as e:
                    logger.warning(
                        f"Skipping track due to error: {track.track_data.title} ({track.path.name}): {e}"
                    )
                    emit_progress(
                        "track_skipped",
                        index=i,
                        total=len(self.tracks),
                        title=track.track_data.title,
                        file_name=track.path.name,
                        progress=100,
                        status="Skipped: error"
                    )
                    break

            if track_uploaded:
                check_cancelled()
                # Track numbers and payload indices must be contiguous for successfully uploaded tracks only.
                track_index = successful_tracks
                track.track_data.track_number = track_index + 1
                logger.debug(f"Set track position: {track_index + 1}")

                bandcamp_data.update(track.track_data.to_dict(track_index))
                logger.info("Saving changes to album")
                emit_progress(
                    "track_saving",
                    index=i,
                    total=len(self.tracks),
                    title=track.track_data.title,
                    file_name=track.path.name,
                    progress=80,
                    status="Saving metadata"
                )

                try:
                    r = post_request_with_crumb(
                        session,
                        edit_album_cb_url,
                        bandcamp_data,
                        cancel_event=cancel_event,
                    )
                    check_cancelled()
                    latest_album_response = r
                except UploadCancelled:
                    track.cleanup_converted_file()
                    raise
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 403:
                        logger.warning("Got 403 error during album save. Refreshing crumbs and retrying...")
                        check_cancelled()
                        crumbs = self._fetch_crumbs(session, artist_url)
                        bandcamp_data["crumb"] = crumbs["edit_album_cb"]
                        check_cancelled()
                        r = post_request_with_crumb(
                            session,
                            edit_album_cb_url,
                            bandcamp_data,
                            cancel_event=cancel_event,
                        )
                        check_cancelled()
                        latest_album_response = r
                    else:
                        logger.warning(
                            f"Skipping track after upload because album save failed ({e.response.status_code}): "
                            f"{track.track_data.title} ({track.path.name})"
                        )
                        emit_progress(
                            "track_skipped",
                            index=i,
                            total=len(self.tracks),
                            title=track.track_data.title,
                            file_name=track.path.name,
                            progress=100,
                            status=f"Skipped: save failed {e.response.status_code}"
                        )
                        continue

                logger.info(f"Saved changes to album. Last track ID = {r['track_ids'][-1]}")
                bandcamp_data[f"track.id_{track_index}"] = r["track_ids"][-1]
                successful_tracks += 1
                emit_progress(
                    "track_done",
                    index=i,
                    total=len(self.tracks),
                    title=track.track_data.title,
                    file_name=track.path.name,
                    progress=100,
                    status="Complete"
                )
                # Always delete temporary converted files after this track finishes.
                track.cleanup_converted_file()
        
        skipped_tracks = len(self.tracks) - successful_tracks
        album_url = self.extract_album_url_from_response(latest_album_response, artist_url)
        if not album_url:
            album_url = self.extract_album_url_from_response(initial_album_response, artist_url)
        if not album_url:
            album_url = self.build_public_album_url(artist_url, self.album_data.title)
        edit_url = self.build_edit_album_url(artist_url, album_id)
        logger.info(f"Upload complete - Successful tracks: {successful_tracks}/{len(self.tracks)}; skipped: {skipped_tracks}")
        emit_progress(
            "album_done",
            total=len(self.tracks),
            successful=successful_tracks,
            skipped=skipped_tracks,
            album_id=album_id,
            album_url=album_url,
            edit_url=edit_url,
        )
        return {
            "album_id": album_id,
            "album_url": album_url,
            "edit_url": edit_url,
            "successful": successful_tracks,
            "skipped": skipped_tracks,
            "total": len(self.tracks),
        }
