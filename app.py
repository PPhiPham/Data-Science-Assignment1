import pandas as pd
import numpy as np
import geopandas as gpd
import glob
import os
import chardet

# Bokeh imports
from bokeh.io import curdoc
from bokeh.plotting import figure
from bokeh.models import (ColumnDataSource, Range1d, LinearAxis, 
                          Select, HoverTool, GeoJSONDataSource, Panel, Tabs, TabPanel)
from bokeh.layouts import row, column
from bokeh.transform import linear_cmap
from bokeh.palettes import Plasma256

# =====================================================================
# 1) DATA INLADEN
# =====================================================================
# Pas hier het pad aan naar jouw CSV-bestanden
data_path = os.path.join(os.getcwd(), "data")
csv_files = glob.glob(os.path.join(data_path, "*.csv"))

sales_data = []
crash_data = []
ratings_data = []

for file in csv_files:
    # Encoding detecten
    with open(file, "rb") as f:
        result = chardet.detect(f.read(100000))
        detected_encoding = result["encoding"]

    df = pd.read_csv(file, encoding=detected_encoding)

    # Sales data herkennen
    if "Transaction Type" in df.columns or "Financial Status" in df.columns:
        # Filter op de juiste product id
        if "Product ID" in df.columns:
            df.rename(columns={"Product ID": "Product id"}, inplace=True)
        if "Order Charged Date" in df.columns:
            df.rename(columns={"Order Charged Date": "Transaction Date"}, inplace=True)
        if "Financial Status" in df.columns:
            df.rename(columns={"Financial Status": "Transaction Type"}, inplace=True)
        if "Currency of Sale" in df.columns:
            df.rename(columns={"Currency of Sale": "Buyer Currency"}, inplace=True)
        df["Transaction Type"] = df["Transaction Type"].replace({
            "Charged": "Charge",
            "Refund": "Google fee"
        })
        df = df[
            (df["Product id"] == "com.vansteinengroentjes.apps.ddfive")    
        ]        
        if "Transaction Date" in df.columns:
            df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors='coerce')
        sales_data.append(df)


    # Crash data herkennen
    elif "Daily Crashes" in df.columns and "Daily ANRs" in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        crash_data.append(df)

    # Ratings data herkennen
    elif "Daily Average Rating" in df.columns and "Country" in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        ratings_data.append(df)

conversion_rate_list = []
for df in sales_data:
    if "Currency Conversion Rate" in df.columns:
        conversion_rate_list.append(df[["Buyer Currency", "Currency Conversion Rate"]])

if conversion_rate_list:
    conversion_df = pd.concat(conversion_rate_list, ignore_index=True)
    mean_conversions = conversion_df.groupby("Buyer Currency")["Currency Conversion Rate"].mean()

for idx, df in enumerate(sales_data):
    if "Currency Conversion Rate" not in df.columns:
        df["Currency Conversion Rate"] = df["Buyer Currency"].map(mean_conversions)
        sales_data[idx] = df

for idx, df in enumerate(sales_data):
    if "Amount (Merchant Currency)" not in df.columns:
        df["Charged Amount"] = pd.to_numeric(df["Charged Amount"], errors='coerce')
        df["Currency Conversion Rate"] = pd.to_numeric(df["Currency Conversion Rate"], errors='coerce')
        df["Amount (Merchant Currency)"] = df["Charged Amount"] * df["Currency Conversion Rate"]
        sales_data[idx] = df
   
print(mean_conversions)

print("=== Sales DataFrames ===")
for i, df in enumerate(sales_data):
    print(f"\nSales DataFrame {i}:")
    print(df.head()) 
    print("-" * 40)


# Concateneren tot DataFrames
df_sales = pd.concat(sales_data, ignore_index=True) if sales_data else pd.DataFrame()
df_crashes = pd.concat(crash_data, ignore_index=True) if crash_data else pd.DataFrame()
df_ratings = pd.concat(ratings_data, ignore_index=True) if ratings_data else pd.DataFrame()

# Datums schoonmaken
df_sales.dropna(subset=["Transaction Date"], inplace=True)
df_sales["Month"] = df_sales["Transaction Date"].dt.to_period("M").astype(str)

# =====================================================================
# 2) EERSTE VISUALISATIE: Sales Over Tijd
# =====================================================================
# Aggregeren op maand
sales_by_month = df_sales.groupby("Month").agg({
    "Amount (Merchant Currency)": "sum",
    "Transaction Date": "count"  # aantal transacties
}).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()

source_sales_by_month = ColumnDataSource(sales_by_month)
x_range_values = sales_by_month["Month"].tolist()

p1 = figure(
    title="Sales Volume Over Tijd",
    x_range=x_range_values,
    height=400, width=700,
    x_axis_label="Maand", 
    y_axis_label="Aantal Transacties",
    toolbar_location="right"
)

# Staven voor aantal transacties
p1.vbar(
    x="Month",
    top="Transaction Count",
    source=source_sales_by_month,
    width=0.5,
    color="steelblue",
    legend_label="Aantal Transacties"
)

# Tweede y-as voor omzet
max_amount = sales_by_month["Amount (Merchant Currency)"].max()
p1.extra_y_ranges = {"amount": Range1d(start=0, end=max_amount * 1.1)}
p1.add_layout(LinearAxis(y_range_name="amount", axis_label="Totale Omzet (€)"), 'right')

# Lijn voor omzet
p1.line(
    x="Month",
    y="Amount (Merchant Currency)",
    source=source_sales_by_month,
    color="firebrick",
    line_width=2,
    y_range_name="amount",
    legend_label="Totale Omzet"
)

p1.legend.location = "top_left"

# =====================================================================
# 3) TWEEDE VISUALISATIE: Sales per SKU + Widget
# =====================================================================
unique_skus = df_sales["Sku Id"].dropna().unique().tolist()
unique_skus.sort()

# Aggregatie per SKU en per maand
sku_sales_df = df_sales.groupby(["Sku Id", "Month"]).agg({
    "Amount (Merchant Currency)": "sum",
    "Transaction Date": "count"
}).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()

source_sku_filtered = ColumnDataSource(data=dict(Month=[], amount=[], count=[]))

p2 = figure(
    title="Verkoop per SKU (per Maand)",
    x_range=x_range_values,
    height=400, width=700,
    x_axis_label="Maand", 
    y_axis_label="Totale Omzet",
    toolbar_location="right"
)

bars_sku = p2.vbar(
    x="Month",
    top="amount",
    width=0.5,
    source=source_sku_filtered,
    color="green"
)

# Callback-functie om data te updaten
def update_sku_plot(attr, old, new):
    selected_sku = select_sku.value
    df_filtered = sku_sales_df[sku_sales_df["Sku Id"] == selected_sku].copy()

    # Re-indexen voor alle maanden (ook als er geen data is in een bepaalde maand)
    df_filtered = df_filtered.set_index("Month").reindex(x_range_values, fill_value=0).reset_index()
    df_filtered.rename(columns={"index": "Month"}, inplace=True)

    source_sku_filtered.data = dict(
        Month=df_filtered["Month"],
        amount=df_filtered["Amount (Merchant Currency)"],
        count=df_filtered["Transaction Count"]
    )

# Select-widget
from bokeh.models import Select
select_sku = Select(title="SKU filter", value=unique_skus[0], options=unique_skus)
select_sku.on_change("value", update_sku_plot)

# Initieel aanroepen
update_sku_plot(None, None, None)

# =====================================================================
# 4) DERDE VISUALISATIE: Ratings vs Crashes
# =====================================================================
df_crashes["Daily Crashes"] = df_crashes.get("Daily Crashes", np.nan).fillna(0)
df_ratings["Daily Average Rating"] = df_ratings.get("Daily Average Rating", np.nan).fillna(
    df_ratings["Daily Average Rating"].mean()
)

ratings_crashes = df_crashes.merge(df_ratings, on="Date", how="outer").groupby("Date").agg({
    "Daily Crashes": "sum",
    "Daily Average Rating": "mean"
}).reset_index()

ratings_crashes_source = ColumnDataSource(ratings_crashes)

p3 = figure(
    title="Ratings vs. Crashes",
    x_axis_label="Datum",
    y_axis_label="Crashes",
    x_axis_type="datetime",
    height=400, width=700,
    toolbar_location="right"
)

# Extra y-as voor ratings
p3.extra_y_ranges = {"rating": Range1d(start=0, end=5)}
p3.add_layout(LinearAxis(y_range_name="rating", axis_label="Gemiddelde Rating"), 'right')

# Crashes op linker as
p3.line(
    x="Date", 
    y="Daily Crashes",
    source=ratings_crashes_source,
    color="red",
    legend_label="Crashes"
)

# Ratings op rechter as
p3.line(
    x="Date",
    y="Daily Average Rating",
    source=ratings_crashes_source,
    color="blue",
    line_width=2,
    y_range_name="rating",
    legend_label="Gemiddelde Rating"
)

p3.legend.location = "top_right"

# =====================================================================
# 5) VIERDE VISUALISATIE: Geografische Kaart (Sales per Land)
# =====================================================================
# Pas het pad aan naar jouw shapefile
shapefile_path = os.path.join(os.getcwd(), "worldmap", "ne_110m_admin_0_countries.shp")
world = gpd.read_file(shapefile_path)

# Verkoop per land
country_sales = df_sales.groupby("Buyer Country").agg({"Amount (Merchant Currency)": "sum"}).reset_index()
world = world.merge(country_sales, how="left", left_on="ISO_A2", right_on="Buyer Country")
world["Amount (Merchant Currency)"] = world["Amount (Merchant Currency)"].fillna(0)

# Converteer naar GeoJSON
world = world.to_crs("EPSG:4326")  # Zorg dat het WGS84 is
geo_source = GeoJSONDataSource(geojson=world.to_json())

max_sales = world["Amount (Merchant Currency)"].max()
color_mapper = linear_cmap(
    field_name="Amount (Merchant Currency)",
    palette=Plasma256,
    low=0, 
    high=max_sales
)

p4 = figure(
    title="Geografische Verdeling van Sales",
    match_aspect=True,
    x_axis_type="mercator", 
    y_axis_type="mercator",
    height=400, width=700,
    toolbar_location="right"
)

# Als je een tile-background wilt, uncomment deze regels:
# from bokeh.tile_providers import get_provider, CARTODBPOSITRON
# p4.add_tile(get_provider(CARTODBPOSITRON))

r = p4.patches(
    xs="xs",
    ys="ys",
    source=geo_source,
    fill_color=color_mapper,
    fill_alpha=0.7,
    line_color="gray",
    line_width=0.5
)

# Hovertool
hovertool = HoverTool(
    renderers=[r],
    tooltips=[
        ("Land", "@ADMIN"),  # ADMIN komt uit shapefile
        ("Sales (€)", "@{Amount (Merchant Currency)}{0.00}")
    ]
)
p4.add_tools(hovertool)

# =====================================================================
# 6) LAYOUT (Tabs)
# =====================================================================
from bokeh.models import Panel, Tabs

tab1 = TabPanel(child=p1, title="Sales Over Tijd")
tab2 = TabPanel(child=column(select_sku, p2), title="Sales per SKU")
tab3 = TabPanel(child=p3, title="Ratings vs Crashes")
tab4 = TabPanel(child=p4, title="Wereldkaart")

tabs = Tabs(tabs=[tab1, tab2, tab3, tab4])

curdoc().add_root(tabs)
curdoc().title = "Emerald-IT Dashboard"