"""Upload agendado no YouTube (Data API v3). Um token OAuth por canal."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]


@dataclass
class UploadRequest:
    file: Path
    title: str
    description: str
    tags: list[str]
    category_id: str
    publish_at: datetime
    language: str
    made_for_kids: bool = False
    synthetic_media: bool = True
    thumbnail: Path | None = None
    playlist_id: str | None = None
    subtitles: Path | None = None


@dataclass
class UploadResult:
    video_id: str
    thumbnail_ok: bool
    warnings: list[str] = field(default_factory=list)


class Uploader(Protocol):
    def upload(self, req: UploadRequest) -> UploadResult: ...


def rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class YouTubeUploader:
    def __init__(self, token_file: Path):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not token_file.exists():
            raise RuntimeError(f"token OAuth não encontrado em {token_file}; rode `fabrica auth-youtube <canal>`")
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json(), encoding="utf-8")
        self.yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    def upload(self, req: UploadRequest) -> UploadResult:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        body = {
            "snippet": {
                "title": req.title,
                "description": req.description,
                "tags": req.tags,
                "categoryId": req.category_id,
                "defaultLanguage": req.language,
                "defaultAudioLanguage": req.language,
            },
            "status": {
                # agendado: precisa ser privado com publishAt no futuro
                "privacyStatus": "private",
                "publishAt": rfc3339(req.publish_at),
                "selfDeclaredMadeForKids": req.made_for_kids,
                "containsSyntheticMedia": req.synthetic_media,
            },
        }
        media = MediaFileUpload(str(req.file), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
        insert = self.yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _, response = insert.next_chunk()
        video_id = response["id"]

        warnings: list[str] = []
        thumb_ok = False
        if req.thumbnail:
            try:
                self.yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(req.thumbnail))).execute()
                thumb_ok = True
            except HttpError as e:  # canal não verificado, arquivo grande demais etc.
                warnings.append(f"thumbnail não enviada: {e}")
        if req.playlist_id:
            try:
                self.yt.playlistItems().insert(part="snippet", body={"snippet": {
                    "playlistId": req.playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
            except HttpError as e:
                warnings.append(f"playlist: {e}")
        if req.subtitles:
            try:
                self.yt.captions().insert(
                    part="snippet",
                    body={"snippet": {"videoId": video_id, "language": req.language, "name": "", "isDraft": False}},
                    media_body=MediaFileUpload(str(req.subtitles), mimetype="application/octet-stream"),
                ).execute()
            except HttpError as e:
                warnings.append(f"legendas: {e}")
        return UploadResult(video_id, thumb_ok, warnings)


class FakeUploader:
    """Grava o que seria enviado em fake_upload.json, sem tocar no YouTube."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir

    def upload(self, req: UploadRequest) -> UploadResult:
        vid = "FAKE" + uuid.uuid4().hex[:7]
        record = {k: (str(v) if isinstance(v, (Path, datetime)) else v) for k, v in req.__dict__.items()}
        record["publish_at"] = rfc3339(req.publish_at)
        record["video_id"] = vid
        (self.out_dir / "fake_upload.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return UploadResult(vid, req.thumbnail is not None)


def authorize(client_secrets: Path, token_file: Path) -> None:
    """Fluxo OAuth no navegador, feito uma vez por canal com a conta dona do canal."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
