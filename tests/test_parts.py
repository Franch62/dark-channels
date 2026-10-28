import io

from PIL import Image

from fabrica.providers.renderer import DEFAULT_ALLOWED_TOOLS, LemoOpuscarRenderer, RenderJob
from fabrica.schemas import Metadata
from fabrica.thumbnail_compose import MAX_BYTES, compose


def test_title_and_tags_limits():
    m = Metadata(title="x" * 150, description="d", tags=["a" * 60] * 20, hashtags=[], thumbnail_text="t")
    assert len(m.title) <= 100
    tags = m.clamp_tags(["fixa"])
    assert tags[0] == "fixa"
    assert sum(len(t) for t in tags) + len(tags) - 1 <= 500


def test_compose_fits_youtube(tmp_path):
    art = Image.effect_noise((2000, 2000), 90).convert("RGB")
    buf = io.BytesIO()
    art.save(buf, "PNG")
    out = compose(buf.getvalue(), "não conte as portas", tmp_path / "t.jpg")
    with Image.open(out) as im:
        assert im.size == (1280, 720)
    assert out.stat().st_size <= MAX_BYTES


def test_renderer_uses_scoped_tools(tmp_path):
    job = RenderJob(brief="b", workdir=tmp_path, width=1080, height=1920, duration_s=50, timeout_min=1)
    cmd = LemoOpuscarRenderer().command(job)
    assert "--allowedTools" in cmd
    assert ",".join(DEFAULT_ALLOWED_TOOLS) in cmd
    assert not any("bypass" in c or "dangerously" in c for c in cmd)
