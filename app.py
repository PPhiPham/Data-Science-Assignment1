import pandas as pd
import numpy as np
import geopandas as gpd
import glob
import os
import chardet

# Bokeh libs
from bokeh.io import output_file, output_notebook
from bokeh.plotting import figure, show
from bokeh.models import ColumnDataSource, Range1d, LinearAxis
from bokeh.layouts import row, column, gridplot
from bokeh.models import Tabs, Panel

# Pad naar de map met CSV-bestanden
data_path = os.path.join(os.getcwd(), "data")

# Zoek alle CSV-bestanden in map
csv_files = glob.glob(os.path.join(data_path, "*.csv"))

# Laad en filtert de data
sales_data = []
crash_data = []
ratings_data = []

for file in csv_files:
    # Encoding detecten, want ik kreeg csv niet gelezen
    with open(file, "rb") as f:
        result = chardet.detect(f.read(100000))
        detected_encoding = result["encoding"]

    df = pd.read_csv(file, encoding=detected_encoding)

    # Sales data
    if "Product id" in df.columns and "Transaction Type" in df.columns:
        df = df[(df["Product id"] == "com.vansteinengroentjes.apps.ddfive") & 
                (df["Transaction Type"] == "Charge")]
        
        if "Transaction Date" in df.columns:
            df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors='coerce')

        sales_data.append(df)

    # Crash data
    elif "Daily Crashes" in df.columns and "Daily ANRs" in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        
        crash_data.append(df)

    # Ratings data
    elif "Daily Average Rating" in df.columns and "Total Average Rating" in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        
        ratings_data.append(df)

# Combineer de ingelezen bestanden per type
df_sales = pd.concat(sales_data, ignore_index=True) if sales_data else pd.DataFrame()
df_crashes = pd.concat(crash_data, ignore_index=True) if crash_data else pd.DataFrame()
df_ratings = pd.concat(ratings_data, ignore_index=True) if ratings_data else pd.DataFrame()

# Controleer of alles goed is geladen
print("Sales kolommen:", df_sales.columns)
print("Crashes kolommen:", df_crashes.columns)
print("Ratings kolommen:", df_ratings.columns)

output_file('index.html', title='Test Bokeh Figure')

# Controleren datum
df_sales = df_sales.dropna(subset=["Transaction Date"])  
df_sales["Month"] = df_sales["Transaction Date"].dt.to_period("M").astype(str)

# Sales per maand
sales_by_month = df_sales.groupby("Month").agg({
    "Amount (Merchant Currency)": "sum", 
    "Transaction Date": "count"  # Dit telt het aantal transacties per maand
}).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()

source = ColumnDataSource(sales_by_month)
x_range_values = sales_by_month["Month"].astype(str).tolist()

# Sales
p1 = figure(title="Sales Volume Over Tijd",
            x_range=x_range_values, height=400, width=700,
            x_axis_label="Maand", y_axis_label="Aantal Transacties",
            toolbar_location=None)

p1.vbar(x="Month", top="Transaction Count", source=source, width=0.5, color="blue", legend_label="Aantal Transacties")
p1.line(x="Month", y="Amount (Merchant Currency)", source=source, color="red", legend_label="Totale Omzet", line_width=2)

p1.legend.location = "top_left"

# SKU
sku_sales = df_sales.groupby("Sku Id").agg({"Amount (Merchant Currency)": "sum"}).reset_index()
source_sku = ColumnDataSource(sku_sales)

p2 = figure(title="Verkoop per SKU ID",
            x_range=sku_sales["Sku Id"], height=400, width=700,
            x_axis_label="SKU ID", y_axis_label="Totale Omzet",
            toolbar_location=None)

p2.vbar(x="Sku Id", top="Amount (Merchant Currency)", source=source_sku, width=0.5, color="green", legend_label="Totale Omzet")

# Crash vs Rating
df_crashes["Daily Crashes"] = df_crashes.get("Daily Crashes", np.nan).fillna(0)
df_ratings["Daily Average Rating"] = df_ratings.get("Daily Average Rating", np.nan).fillna(df_ratings["Daily Average Rating"].mean())

ratings_crashes = df_crashes.merge(df_ratings, on="Date", how="outer").groupby("Date").agg({
    "Daily Crashes": "sum",
    "Daily Average Rating": "mean"
}).reset_index()

source_ratings = ColumnDataSource(ratings_crashes)

p3 = figure(title="Ratings vs. Crashes",
            x_axis_label="Datum", height=400, width=700,
            x_axis_type="datetime", y_axis_label="Crashes")

# Maak rating as
p3.extra_y_ranges = {"rating": Range1d(start=0, end=5)}
p3.add_layout(LinearAxis(y_range_name="rating", axis_label="Gemiddelde Rating"), 'right')  
p3.add_layout(p3.yaxis[1], 'right') 

#Voeg crashes links
p3.line(x="Date", y="Daily Crashes", source=source_ratings, color="red", legend_label="Crashes")

# Voeg rating rechts
p3.line(x="Date", y="Daily Average Rating", source=source_ratings, color="blue", legend_label="Gemiddelde Rating",
        line_width=2, y_range_name="rating")

p3.legend.location = "top_right"

# Geoggrafisch
shapefile_path = os.path.join(os.getcwd(), "worldmap", "ne_110m_admin_0_countries.shp")  
world = gpd.read_file(shapefile_path)

country_sales = df_sales.groupby("Buyer Country").agg({"Amount (Merchant Currency)": "sum"}).reset_index()
world = world.merge(country_sales, how="left", left_on="ISO_A2", right_on="Buyer Country")

# Show dashboard
show(gridplot([[p1, p2], [p3]]))