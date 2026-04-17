# use pydantic to define a model for the feautre type string
# it has to be a string and one of the following: 
# point: Data represents individual points.
# timeSeries: Data represents a single point in space varying in time.
# trajectory: Data represents a single point in space moving in time.
# profile: Data represents a vertical profile at a fixed horizontal location and time.
# timeSeriesProfile: Data represents a time series of vertical profiles.
# trajectoryProfile: Data represents a moving vertical profile (e.g., from an aircraft or glider). 

import xarray as xr
from pydantic import BaseModel, AnyHttpUrl, validator
from enum import StrEnum


class FeatureTypeEnum(StrEnum):
    POINT = "point"
    TIMESERIES = "timeSeries"
    TRAJECTORY = "trajectory"
    PROFILE = "profile"
    TIMESERIESPROFILE = "timeSeriesProfile"
    TRAJECTORYPROFILE = "trajectoryProfile"

class FeatureType(BaseModel):
    value: FeatureTypeEnum

# extend pydantic basemodel to check a string to be a proper URL
class URLStr(BaseModel):
    url: AnyHttpUrl

class OpendapURL(URLStr):
    @validator('url')
    def validate_opendap_url(cls, v):
        # check that the url can be opened by xarray and that it contains the necessary attributes
        # for the feature type
        try:
            with xr.open_dataset(str(v)) as ds:
                if 'featureType' not in ds.attrs:
                    raise ValueError('URL does not point to a valid OPeNDAP dataset with featureType attribute')
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f'URL cannot be opened as an OPeNDAP dataset: {e}')
        return v
    
    
    
def guess_feature_type_from_data(data):
    # open the dataset using xarray and check the attributes for featuretype, if not present return None    
    # first validate that the url can be opened by xarray and that it contains the necessary attributes for the feature type, if not return None
    print(f"\n Guess FeatureType got data: {data}") 
    #if not OpendapURL.validate_opendap_url(data):
    #    return None
    url = str(data)
    try:
        with xr.open_dataset(url, decode_times=False) as ds:
            return ds.attrs.get('featureType', None)
    except Exception as e:
        raise ValueError(f'URL cannot be opened as an OPeNDAP dataset: {e}')
    
    
