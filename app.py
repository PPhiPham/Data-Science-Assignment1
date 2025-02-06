import pandas as pd
import numpy as np
import geopandas as gpd
import glob
import os
import chardet

# Bokeh libs
from bokeh.io import output_file, output_notebook
from bokeh.plotting import figure, show
from bokeh.models import ColumnDataSource
from bokeh.layouts import row, column, gridplot
from bokeh.models import Tabs, Panel

# Pad naar de map met CSV-bestanden
data_path = os.path.join(os.getcwd(), "data")

# Zoek alle CSV-bestanden in map
csv_files = glob.glob(os.path.join(data_path, "*.csv"))

# Laad en filtert de data
dataframes = []
for file in csv_files:
    # Encoding detecten, want ik kreeg csv niet gelezen
    with open(file, "rb") as f:
        result = chardet.detect(f.read(100000))
        detected_encoding = result["encoding"]

    df = pd.read_csv(file, encoding=detected_encoding)

    # Filter
    if "Product id" in df.columns:
        df = df[df["Product id"] == "com.vansteinengroentjes.apps.ddfive"] 
        df = df[df["Transaction Type"] == "Charge"] 

    
    for col in ["Transaction Date", "Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')  

    dataframes.append(df)


df_combined = pd.concat(dataframes, ignore_index=True)
print(df_combined.columns)

output_file('index.html', title='Test Bokeh Figure')

# Zet data om naar een Bokeh ColumnDataSource

df_combined["Month"] = df_combined["Transaction Date"].dt.to_period("M").astype(str)
sales_by_month = df_combined.groupby("Month").agg({"Amount (Merchant Currency)": "sum", "Transaction Date": "count"}).reset_index()
source = ColumnDataSource(sales_by_month)


# Graph sales

p1 = figure(title="Sales Volume Over Tijd",
            x_range=sales_by_month["Month"], height=400, width=700,
            x_axis_label="Maand", y_axis_label="Aantal Transacties",
            toolbar_location=None)

p1.vbar(x="Month", top="Transaction Date", source=source, width=0.5, color="blue", legend_label="Aantal Transacties")
p1.line(x="Month", y="Amount (Merchant Currency)", source=source, color="red", legend_label="Totale Omzet", line_width=2)

p1.legend.location = "top_left"

# Filter SKU
sku_sales = df_combined.groupby("Sku Id").agg({"Amount (Merchant Currency)": "sum"}).reset_index()
source_sku = ColumnDataSource(sku_sales)

p2 = figure(title="Verkoop per SKU ID",
            x_range=sku_sales["Sku Id"], height=400, width=700,
            x_axis_label="SKU ID", y_axis_label="Totale Omzet",
            toolbar_location=None)

p2.vbar(x="Sku Id", top="Amount (Merchant Currency)", source=source_sku, width=0.5, color="green", legend_label="Totale Omzet")

# Rating vs Crashes

df_combined["Daily Crashes"] = df_combined.get("Daily Crashes", np.nan)
df_combined["Daily Average Rating"] = df_combined.get("Daily Average Rating", np.nan)

ratings_crashes = df_combined.groupby("Transaction Date").agg({"Daily Crashes": "sum", "Daily Average Rating": "mean"}).reset_index()
source_ratings = ColumnDataSource(ratings_crashes)

p3 = figure(title="Ratings vs. Crashes",
            x_axis_label="Datum", y_axis_label="Crashes",
            height=400, width=700, x_axis_type="datetime")

p3.line(x="Transaction Date", y="Daily Crashes", source=source_ratings, color="red", legend_label="Crashes")
p3.line(x="Transaction Date", y="Daily Average Rating", source=source_ratings, color="blue", legend_label="Gemiddelde Rating", line_width=2)

p3.legend.location = "top_right"

# Geographisch

shapefile_path = os.path.join(os.getcwd(), "worldmap", "ne_110m_admin_0_countries.shp")  
world = gpd.read_file(shapefile_path)
print(world.columns)
country_sales = df_combined.groupby("Buyer Country").agg({"Amount (Merchant Currency)": "sum"}).reset_index()
world = world.merge(country_sales, how="left", left_on="ISO_A2", right_on="Buyer Country")


# Show dashboard
show(gridplot([[p1, p2], [p3]]))