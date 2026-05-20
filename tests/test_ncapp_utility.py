import pytest
from pydantic import ValidationError
from utility import FeatureType, FeatureTypeEnum, guess_feature_type_from_data


def test_feature_type_accepts_valid():
    assert FeatureType(value="timeSeries").value == FeatureTypeEnum.TIMESERIES


def test_feature_type_rejects_invalid():
    with pytest.raises(ValidationError):
        FeatureType(value="not-a-feature-type")


def test_guess_feature_type_bad_url_raises():
    with pytest.raises(ValueError):
        guess_feature_type_from_data("/definitely/not/a/dataset.nc")
