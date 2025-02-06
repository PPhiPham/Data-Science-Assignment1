import pandas as pd
import numpy as np
import geopandas

# Bokeh libraries
from bokeh.io import output_file, output_notebook
from bokeh.plotting import figure, show
from bokeh.models import ColumnDataSource
from bokeh.layouts import row, column, gridplot
from bokeh.models import Tabs, Panel

output_file('index.html')

# Set up the figure(s)
fig = figure()  # Instantiate a figure() object

# Preview and save 
show(fig)  # See what I made, and save if I like it