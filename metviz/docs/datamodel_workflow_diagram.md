# Metviz Data Ingestion & Visualization Workflow Diagram

```mermaid
flowchart TD
    A(User Input: Data URL or File) --> B{Validate URL}
    B -- Valid --> C(Open Dataset: xarray)
    B -- Invalid --> Z(Error: Invalid URL)
    C --> D{Feature Type}
    D -- Trajectory --> E(Trajectory Workflow)
    D -- TimeSeries --> F(TimeSeries Workflow)
    D -- TimeSeries Profile --> G(TimeSeries Profile Workflow)
    D -- Profile --> H(Profile Workflow)
    E --> E1(Extract lat/lon/time/variables)
    E1 --> E2(Compute trajectory stats)
    E2 --> E3(Build widgets: variable select, time slider)
    E3 --> E4(Render plot: Holoviews/Panel)
    E3 --> E5(Render map: ipyleaflet)
    F --> F1(Identify plottable variables)
    F1 --> F2(Build widgets: variable, axis, frequency, export)
    F2 --> F3(User selects variable/dimension)
    F3 --> F4(Render plot: hvplot/bokeh)
    F2 --> F5(Export/download data)
    F2 --> F6(Show metadata)
    G --> G1(Identify plottable variables)
    G1 --> G2(Build widgets: variable, axis, frequency, export)
    G2 --> G3(User selects variable/dimension)
    G3 --> G4(Render plot: hvplot/bokeh)
    G2 --> G5(Export/download data)
    G2 --> G6(Show metadata)
    H --> H1(Identify plottable variables)
    H1 --> H2(Build widgets: variable, axis, export)
    H2 --> H3(User selects variable/dimension)
    H3 --> H4(Render plot: hvplot/bokeh)
    H2 --> H5(Export/download data)
    H2 --> H6(Show metadata)
    style Z fill:#faa,stroke:#f00
    style A fill:#bbf,stroke:#00f
    style C fill:#bbf,stroke:#00f
    style E fill:#bfb,stroke:#080
    style F fill:#bfb,stroke:#080
    style G fill:#bfb,stroke:#080
    style H fill:#bfb,stroke:#080
```


