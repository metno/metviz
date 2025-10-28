import panel as pn
import pandas as pd

# Load the Tabulator extension
pn.extension('tabulator')

# Now you can safely create and use Tabulator widgets
data = {'col1': [1, 2, 3], 'col2': ['A', 'B', 'C']}
df = pd.DataFrame(data)

tabulator_widget = pn.widgets.Tabulator(df)

tabulator_widget.servable()
