import pytest
from pydantic import ValidationError

from fabrica.config import ChannelConfig, load_channels


def test_example_channel_loads(settings):
    channels = load_channels(settings.channels_dir)
    c = channels["exemplo-terror"]
    assert c.content.size == (1080, 1920)
    assert c.schedule.publish_delay_min == 30
    assert c.thumbnail.variants == 3


def test_slug_must_be_kebab_case():
    with pytest.raises(ValidationError):
        ChannelConfig.model_validate({"slug": "Meu Canal", "content": {"niche": "x"}})


def test_slug_must_match_folder(settings):
    yml = settings.channels_dir / "exemplo-terror" / "channel.yaml"
    other = settings.channels_dir / "outro"
    other.mkdir()
    (other / "channel.yaml").write_text(yml.read_text())
    with pytest.raises(ValueError, match="difere"):
        load_channels(settings.channels_dir)
