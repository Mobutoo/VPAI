# MeTube Documentation

## README - Overview and Quick Start

MeTube is a web interface for yt-dlp that enables downloading videos from YouTube and dozens of other platforms, with playlist support.

**Docker command:**
```bash
docker run -d -p 8081:8081 -v /path/to/downloads:/downloads ghcr.io/alexta69/metube
```

**Docker Compose:**
```yaml
services:
  metube:
    image: ghcr.io/alexta69/metube
    container_name: metube
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - /path/to/downloads:/downloads
```

**Source:** https://github.com/alexta69/metube

## README - Configuration Environment Variables

### Download Behavior
- **MAX_CONCURRENT_DOWNLOADS**: Limits simultaneous downloads (default: 3)
- **DELETE_FILE_ON_TRASHCAN**: Removes files when trashed (default: false)
- **DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT**: Maximum playlist items downloadable (default: 0/unlimited)
- **CLEAR_COMPLETED_AFTER**: Auto-removes completed downloads after specified seconds (default: 0/disabled)

### Storage and Directories
- **DOWNLOAD_DIR**: Where downloads save (default: /downloads in Docker)
- **AUDIO_DOWNLOAD_DIR**: Separate path for audio-only downloads
- **CUSTOM_DIRS**: Enable custom directory dropdown (default: true)
- **CREATE_CUSTOM_DIRS**: Support auto-creating directories (default: true)
- **CUSTOM_DIRS_EXCLUDE_REGEX**: Exclude directories matching pattern (default: "(^|/)[.@].*$")
- **DOWNLOAD_DIRS_INDEXABLE**: Make directories web-accessible (default: false)
- **STATE_DIR**: Queue persistence location (default: /downloads/.metube in Docker)
- **TEMP_DIR**: Intermediary file storage (default: /downloads in Docker)
- **CHOWN_DIRS**: Set directory ownership on startup (default: true)

### File Naming and yt-dlp
- **OUTPUT_TEMPLATE**: Filename format per yt-dlp spec (default: "%(title)s.%(ext)s")
- **OUTPUT_TEMPLATE_CHAPTER**: Template for chapter-split videos
- **OUTPUT_TEMPLATE_PLAYLIST**: Template for playlists (default: "%(playlist_title)s/%(title)s.%(ext)s")
- **OUTPUT_TEMPLATE_CHANNEL**: Template for channels (default: "%(channel)s/%(title)s.%(ext)s")
- **YTDL_OPTIONS**: Additional yt-dlp options in JSON format
- **YTDL_OPTIONS_FILE**: Path to JSON configuration file (auto-reloads on changes)

### Web Server and URLs
- **HOST**: Binding address (default: 0.0.0.0)
- **PORT**: Listening port (default: 8081)
- **URL_PREFIX**: Base path for reverse proxy use (default: /)
- **PUBLIC_HOST_URL**: Base URL for download links
- **PUBLIC_HOST_AUDIO_URL**: Base URL for audio downloads
- **HTTPS**: Enable HTTPS (requires CERTFILE and KEYFILE)
- **ROBOTS_TXT**: Path to robots.txt file

### Basic Setup
- **PUID**: Running user (default: 1000)
- **PGID**: Running group (default: 1000)
- **UMASK**: File permission mask (default: 022)
- **DEFAULT_THEME**: UI theme - light/dark/auto (default: auto)
- **LOGLEVEL**: DEBUG/INFO/WARNING/ERROR/CRITICAL/NONE (default: INFO)
- **ENABLE_ACCESSLOG**: Enable access logging (default: false)

## README - Browser Cookies

Upload cookies via the UI's Advanced Options to access restricted content. Browser extensions available for extracting cookies from Firefox and Chrome.

## README - Browser Extensions

- **Chrome**: Available on Google Chrome Webstore (contributed by Rpsl)
- **Firefox**: Available on Firefox Addons (contributed by nanocortex)

## README - iOS Support

iOS Shortcut available for sending URLs from Safari. For iOS compatibility, MeTube offers "Best (iOS)" format option requiring h264/h265 video and AAC audio in MP4 container.

Force iOS-compatible codec conversion:
```yaml
environment:
  - 'YTDL_OPTIONS={"format": "best", "exec": "ffmpeg -i %(filepath)q -c:v libx264 -c:a aac %(filepath)q.h264.mp4"}'
```

## README - Reverse Proxy Configuration

### NGINX
```nginx
location /metube/ {
        proxy_pass http://metube:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
}
```

### Apache
```apache
<Location /metube/>
    ProxyPass http://localhost:8081/ retry=0 timeout=30
    ProxyPassReverse http://localhost:8081/
</Location>

<Location /metube/socket.io>
    RewriteEngine On
    RewriteCond %{QUERY_STRING} transport=websocket [NC]
    RewriteRule /(.*) ws://localhost:8081/socket.io/$1 [P,L]
    ProxyPass http://localhost:8081/socket.io retry=0 timeout=30
    ProxyPassReverse http://localhost:8081/socket.io
</Location>
```

### Caddy
```caddyfile
example.com {
  route /metube/* {
    uri strip_prefix metube
    reverse_proxy metube:8081
  }
}
```

## README - Updating yt-dlp

Nightly builds automatically check for yt-dlp updates. Using Watchtower is recommended for automated container updates.

## README - Troubleshooting

Issues with authentication, postprocessing, permissions, or YTDL_OPTIONS should be debugged with the yt-dlp command directly. Access container shell via:
```bash
docker exec -ti metube sh
cd /downloads
```

## README - Development

Requires Node.js 22+ and Python 3.13:
```bash
cd ui
curl -fsSL https://get.pnpm.io/install.sh | sh -
pnpm install
pnpm run build
cd ..
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run python3 app/main.py
```

Build Docker image locally:
```bash
docker build -t metube .
```

## Source Code - ytdl.py - Output Template and Path Handling

The `ytdl.py` module handles all download logic. Key components:

**Output template substitution** (`_outtmpl_substitute_field`): Substitutes a single field in an output template, applying format specifiers to the value. Uses compiled regex patterns (`_compile_outtmpl_pattern`) for performance.

**Path sanitization** (`_sanitize_path_component`): Replaces characters invalid in Windows/NTFS path components (`\\:*?"<>|`) with underscores. Only applies to string values; non-string values pass through unchanged for format spec coercion.

**SRT to TXT conversion** (`_convert_srt_to_txt_file`): Converts SRT subtitle files into plain text by stripping cue numbers and timestamps. Normalizes newlines, splits by double newlines, removes HTML tags, and writes clean text output.

## Source Code - ytdl.py - DownloadInfo Class

The `DownloadInfo` class stores all metadata for a download:
- `id`, `title`, `url`, `quality`, `download_type`, `codec`, `format`, `folder`
- `custom_name_prefix`: Optional prefix for filenames
- `status`: pending/preparing/downloading/finished/error
- `percent`, `speed`, `eta`, `size`, `msg`
- `playlist_item_limit`, `split_by_chapters`, `chapter_template`
- `subtitle_language` (default: "en"), `subtitle_mode` (default: "prefer_manual")
- `subtitle_files`: List of downloaded subtitle files

Backward compatibility via `__setstate__`: Migrates old format (format/video_codec/subtitle_format) to new schema (download_type/codec/format).

## Source Code - ytdl.py - Download Class

The `Download` class manages individual download processes:

- Uses `multiprocessing.Process` for isolation (each download runs in a separate process)
- `_download()`: Creates `yt_dlp.YoutubeDL` instance with configured params (paths, output templates, format, hooks)
- Progress hooks report: tmpfilename, filename, status, total_bytes, downloaded_bytes, speed, eta
- Postprocessor hooks capture: MoveFiles (final filename), SplitChapters (chapter files)
- `start()`: Spawns process, creates async status update task
- `cancel()`: Kills process, sets canceled flag
- Chapter splitting: Adds `FFmpegSplitChapters` postprocessor when `split_by_chapters=True`
- Captions mode: Filters non-caption extensions, handles SRT-to-TXT conversion

## Source Code - ytdl.py - PersistentQueue Class

The `PersistentQueue` class provides persistent storage for download queues using Python's `shelve` module:

- Stores download state in DBM files (survives container restarts)
- `repair()`: Detects DB format (GNU DBM or SQLite) and performs appropriate recovery
  - GDBM: Uses `gdbmtool` for recovery, cleans up NUL-byte keys
  - SQLite: Uses `sqlite3 .recover` command
- Creates backups before repair attempts
- Ordered dict maintains FIFO order by timestamp

## Source Code - ytdl.py - DownloadQueue Class

The `DownloadQueue` class orchestrates all downloads:

- Three queues: `queue` (active), `done` (completed), `pending` (not auto-started)
- `add()`: Extracts info via yt-dlp, handles playlists/channels recursively, creates `DownloadInfo`
- `__start_download()`: Uses asyncio semaphore for concurrency control (`MAX_CONCURRENT_DOWNLOADS`)
- `_post_download_cleanup()`: Moves completed downloads to done queue, triggers notifications, handles auto-clear
- `cancel()`: Tracks canceled URLs to prevent re-queuing during playlist processing
- `start_pending()`: Moves pending downloads to active queue
- `clear()`: Removes from done queue, optionally deletes files (`DELETE_FILE_ON_TRASHCAN`)
- Output template resolution: Applies playlist/channel templates with field substitution and path sanitization

## Source Code - main.py - Config Class

The `Config` class in `main.py` manages all configuration:

**Defaults** (loaded from environment or defaults dict):
- DOWNLOAD_DIR, AUDIO_DOWNLOAD_DIR, TEMP_DIR, STATE_DIR
- OUTPUT_TEMPLATE: "%(title)s.%(ext)s"
- OUTPUT_TEMPLATE_CHAPTER: "%(title)s - %(section_number)02d - %(section_title)s.%(ext)s"
- OUTPUT_TEMPLATE_PLAYLIST: "%(playlist_title)s/%(title)s.%(ext)s"
- OUTPUT_TEMPLATE_CHANNEL: "%(channel)s/%(title)s.%(ext)s"
- MAX_CONCURRENT_DOWNLOADS: "3", PORT: "8081", HOST: "0.0.0.0"

**Boolean config keys**: DOWNLOAD_DIRS_INDEXABLE, CUSTOM_DIRS, CREATE_CUSTOM_DIRS, DELETE_FILE_ON_TRASHCAN, HTTPS, ENABLE_ACCESSLOG

**YTDL_OPTIONS handling**:
- Parsed from JSON env var or JSON file (YTDL_OPTIONS_FILE)
- File is watched for changes via `watchfiles` (auto-reloads)
- Runtime overrides (e.g., cookie file) applied on top

**Frontend-safe config**: Only exposes CUSTOM_DIRS, CREATE_CUSTOM_DIRS, OUTPUT_TEMPLATE_CHAPTER, PUBLIC_HOST_URL, PUBLIC_HOST_AUDIO_URL, DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT to browser.

## Source Code - main.py - API Endpoints

MeTube exposes these HTTP API endpoints:

**POST /add** - Add a download:
- Required: `url`, `download_type` (video/audio/captions/thumbnail), `quality`
- Optional: `codec`, `format`, `folder`, `custom_name_prefix`, `playlist_item_limit`, `auto_start`, `split_by_chapters`, `chapter_template`, `subtitle_language`, `subtitle_mode`
- Validates all inputs (download_type, codec, format, quality combinations)
- Legacy API migration: old format/video_codec/subtitle_format auto-converted

**POST /delete** - Cancel or clear downloads:
- `ids`: list of URLs, `where`: "queue" or "done"

**POST /start** - Start pending downloads:
- `ids`: list of URLs to move from pending to active queue

**POST /cancel-add** - Cancel ongoing playlist add operation

**POST /upload-cookies** - Upload cookies.txt file (multipart, max 1MB)
**POST /delete-cookies** - Remove uploaded cookies
**GET /cookie-status** - Check if cookies are configured

**GET /history** - Get all download history (queue, done, pending)
**GET /version** - Returns yt-dlp and MeTube versions

## Source Code - main.py - WebSocket Events

MeTube uses Socket.IO for real-time communication:

**Server events emitted:**
- `all`: Full queue state on client connect
- `configuration`: Frontend-safe config on connect
- `custom_dirs`: Available download directories
- `ytdl_options_changed`: When YTDL_OPTIONS_FILE is modified
- `added`: New download added
- `updated`: Download progress update
- `completed`: Download finished
- `canceled`: Download canceled
- `cleared`: Download removed from history

## Source Code - main.py - Input Validation

Strict input validation on the `/add` endpoint:

**Valid download types**: video, audio, captions, thumbnail
**Valid video codecs**: auto, h264, h265, av1, vp9
**Valid video formats**: any, mp4, ios
**Valid audio formats**: m4a, mp3, opus, wav, flac
**Valid subtitle formats**: srt, txt, vtt, ttml, sbv, scc, dfxp
**Valid subtitle modes**: auto_only, manual_only, prefer_manual, prefer_auto

**Video qualities**: best, worst, 2160, 1440, 1080, 720, 480, 360, 240
**MP3 qualities**: best, 320, 192, 128
**M4A qualities**: best, 192, 128

**Security**: custom_name_prefix and chapter_template reject path traversal (.. or leading /)
**Subtitle language**: Must match `[A-Za-z0-9-]`, max 35 chars

## Source Code - main.py - Reverse Proxy and Static Files

MeTube serves static files and supports reverse proxy:

- `URL_PREFIX` config adds base path for all routes (e.g., `/metube/`)
- Static files served from `ui/dist/metube/browser/`
- Download directories optionally indexable via `DOWNLOAD_DIRS_INDEXABLE`
- CORS handled via `on_prepare` middleware (reflects Origin header)
- Supports HTTPS with configurable cert/key files
- `SO_REUSEPORT` used when available
- Robots.txt configurable or defaults to disallowing download paths
- Theme cookie set on first visit (light/dark/auto)

## Source Code - main.py - Legacy API Migration

The `_migrate_legacy_request` function converts old API format to new:

Old schema: `format` (any/mp4/m4a/mp3/opus/wav/flac/thumbnail/captions), `quality`, `video_codec`, `subtitle_format`
New schema: `download_type` (video/audio/captions/thumbnail), `codec`, `format`, `quality`

Migration rules:
- Audio formats (m4a/mp3/opus/wav/flac) -> download_type=audio
- "thumbnail" -> download_type=thumbnail, format=jpg
- "captions" -> download_type=captions, format from subtitle_format
- quality="best_ios" -> format=ios, quality=best
- quality="audio" -> download_type=audio, format=m4a
