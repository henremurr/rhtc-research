from fastapi import HTTPException
import pytest

from app.options.youtube import SERIES_ARTWORKS, artwork_for_series


def test_youtube_series_map_has_seven_unique_artworks():
    filenames = [filename for _, filename in SERIES_ARTWORKS.values()]
    assert len(filenames) == 7
    assert len(set(filenames)) == 7


def test_invalid_youtube_series_is_rejected():
    with pytest.raises(HTTPException) as error:
        artwork_for_series("unknown")
    assert error.value.status_code == 400
