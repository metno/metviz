# MetViz

A visualization tool for meteorological data with support for OPeNDAP dataset and OGC services (CSW, WMS).

## Features

### Data Visualization
- Interactive plotting of CF-compliant OPeNDAP URLs for:
  - Time Series
  - Time Series Profiles
  - Vertical Profiles
- Prototype visualization support for datasets with Trajectory FeatureType   

### Data Management
- Flexible data selection and download options:
  - Raw data export
  - Time-resampled dataset export

### OGC Services Integration
- Built-in OGC client supporting:
  - WMS (Web Map Service) resource testing and consumption
  - CSW (Catalog Service for the Web) catalogue exploration

## Technology Stack

### Core Components
- **Docker** - Containerization for consistent deployment and development
- **PyViz Stack**
  - HoloViews - Declarative data visualization
  - Panel - Interactive visualization dashboards
  - Ipyleaflet - Interactiv JS map canvas
- **Scientific Python Stack**
  - Xarray - N-dimensional labeled arrays and datasets
  - NumPy - Numerical computing
  - Pandas - Data manipulation and analysis

### Development
The application is containerized using Docker for easy deployment and consistency across environments. The visualization stack leverages the powerful combination of HoloViews and Panel for interactive data exploration, while Xarray handles the heavy lifting of scientific data operations.