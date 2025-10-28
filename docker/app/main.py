"""
====================

Copyright 2022 MET Norway

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import panel as pn
import pandas as pd

# Load the Tabulator extension
pn.extension('tabulator')

# Now you can safely create and use Tabulator widgets
data = {'col1': [1, 2, 3], 'col2': ['A', 'B', 'C']}
df = pd.DataFrame(data)

tabulator_widget = pn.widgets.Tabulator(df)

tabulator_widget.servable()
