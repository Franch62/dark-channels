from datetime import datetime, timedelta, timezone

from PIL import Image

from fabrica.db import StageStatus, VideoStatus
from fabrica.pipeline import Pipeline
from fabrica.stages.render import RenderStage
from fabrica.stages.upload import publish_time


def test_dry_run_end_to_end(settings):
    p = Pipeline(settings)
    video = p.run(p.create("exemplo-terror").id)
    assert video.status == VideoStatus.scheduled, video.error
    assert all(video.stage_status(n) == StageStatus.done for n in video.stages)
    run_dir = settings.runs_dir / "exemplo-terror" / video.id
    for f in ["script.json", "meta.json", "render.json", "video/film.mp4", "thumbs/thumb.jpg", "fake_upload.json"]:
        assert (run_dir / f).exists(), f
    with Image.open(run_dir / "thumbs/thumb.jpg") as im:
        assert im.size == (1280, 720)
    assert video.youtube_id.startswith("FAKE")
    assert video.topic and video.title


def test_topics_feed_next_script(settings):
    p = Pipeline(settings)
    p.run(p.create("exemplo-terror").id)
    assert p.db.recent_topics("exemplo-terror") == ["O andar 7 que não aparece no elevador"]


def test_failure_then_resume(settings, monkeypatch):
    p = Pipeline(settings)
    original = RenderStage.run

    def boom(self, ctx):
        raise RuntimeError("render caiu")

    monkeypatch.setattr(RenderStage, "run", boom)
    vid = p.create("exemplo-terror").id
    video = p.run(vid)
    assert video.status == VideoStatus.failed
    assert video.stage_status("render") == StageStatus.failed
    assert video.stage_status("script") == StageStatus.done
    assert video.stage_status("upload") == StageStatus.pending

    monkeypatch.setattr(RenderStage, "run", original)
    video = p.run(vid)
    assert video.status == VideoStatus.scheduled, video.error


def test_until_stops_early(settings):
    p = Pipeline(settings)
    video = p.run(p.create("exemplo-terror").id, until="metadata")
    assert video.stage_status("metadata") == StageStatus.done
    assert video.stage_status("render") == StageStatus.pending
    assert video.status == VideoStatus.queued


def test_thumbnail_disabled_is_skipped(settings):
    yml = settings.channels_dir / "exemplo-terror" / "channel.yaml"
    yml.write_text(yml.read_text().replace("thumbnail:\n  enabled: true", "thumbnail:\n  enabled: false"))
    p = Pipeline(settings)
    video = p.run(p.create("exemplo-terror").id)
    assert video.stage_status("thumbnail") == StageStatus.skipped
    assert video.status == VideoStatus.scheduled


def test_publish_time_is_30_min_after_render():
    now = datetime(2026, 10, 28, 14, 0, tzinfo=timezone.utc)
    assert publish_time(now, 30, now=now) == now + timedelta(minutes=30)
    # upload atrasado: nunca agenda no passado
    late = now + timedelta(hours=2)
    assert publish_time(now, 30, now=late) == late + timedelta(minutes=10)
