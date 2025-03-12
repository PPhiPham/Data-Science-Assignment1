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
                          Select, HoverTool, GeoJSONDataSource, Tabs, TabPanel, LogColorMapper, Select, LinearColorMapper, Dropdown)
from bokeh.layouts import row, column
from bokeh.transform import linear_cmap, factor_cmap
from bokeh.palettes import Plasma256, Viridis256, Category20

# =====================================================================
# 1) DATA INLADEN
# =====================================================================
data_path = os.path.join(os.getcwd(), "data")
csv_files = glob.glob(os.path.join(data_path, "*.csv"))

sales_data = []
crash_data = []
ratings_data_country = []
ratings_data_overview = []

for file in csv_files:
    with open(file, "rb") as f:
        result = chardet.detect(f.read(100000))
        detected_encoding = result["encoding"]

    df = pd.read_csv(file, encoding=detected_encoding)

    # Sales data herkennen
    if "Transaction Type" in df.columns or "Financial Status" in df.columns:
        if "Product ID" in df.columns:
            df.rename(columns={"Product ID": "Product id"}, inplace=True)
        if "Order Charged Date" in df.columns:
            df.rename(columns={"Order Charged Date": "Transaction Date"}, inplace=True)
        if "Financial Status" in df.columns:
            df.rename(columns={"Financial Status": "Transaction Type"}, inplace=True)
        if "Currency of Sale" in df.columns:
            df.rename(columns={"Currency of Sale": "Buyer Currency"}, inplace=True)
        if "SKU ID" in df.columns:
            df.rename(columns={"SKU ID": "Sku Id"}, inplace=True)
        df["Transaction Type"] = df["Transaction Type"].replace({
            "Charged": "Charge",
            "Refund": "Google fee"
        })
        df = df[df["Product id"] == "com.vansteinengroentjes.apps.ddfive"]
        if "Transaction Date" in df.columns:
            df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors='coerce')
        sales_data.append(df)

    # Crash data herkennen
    elif "Daily Crashes" in df.columns and "Daily ANRs" in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        crash_data.append(df)

    # Ratings_country data herkennen
    elif "Daily Average Rating" in df.columns and "Country" in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        ratings_data_country.append(df)
    
    # Rating_overview
    elif "Daily Average Rating" in df.columns and "Country" not in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        ratings_data_overview.append(df)
    
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
   
# Concateneren tot DataFrames
df_sales = pd.concat(sales_data, ignore_index=True) if sales_data else pd.DataFrame()
df_crashes = pd.concat(crash_data, ignore_index=True) if crash_data else pd.DataFrame()
df_ratings_country = pd.concat(ratings_data_country, ignore_index=True) if ratings_data_country else pd.DataFrame()
df_ratings_overview = pd.concat(ratings_data_overview, ignore_index=True) if ratings_data_overview else pd.DataFrame()

# Datums schoonmaken
df_sales.dropna(subset=["Transaction Date"], inplace=True)
df_sales["Month"] = df_sales["Transaction Date"].dt.to_period("M").astype(str)

# =====================================================================
# 2) EERSTE VISUALISATIE: Sales Over Tijd (p1)
# =====================================================================
sales_by_month = df_sales.groupby("Month").agg({
    "Amount (Merchant Currency)": "sum",
    "Transaction Date": "count"
}).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()

source_sales_by_month = ColumnDataSource(sales_by_month)
x_range_values = sales_by_month["Month"].tolist()

p1 = figure(
    title="Sales Volume Over Time (All Months)",
    x_range=x_range_values,
    height=500, width=1000,
    x_axis_label="Month", 
    y_axis_label="Transactions",
    toolbar_location="right"
)

# --- We maken hier een variabele bars_p1 aan, zodat we later de kleur kunnen aanpassen
bars_p1 = p1.vbar(
    x="Month",
    top="Transaction Count",
    source=source_sales_by_month,
    width=0.5,
    fill_color=factor_cmap('Month', palette=Viridis256, factors=x_range_values),
    line_color="black",
    legend_label="Aantal Transacties"
)

max_amount = sales_by_month["Amount (Merchant Currency)"].max()
p1.extra_y_ranges = {"amount": Range1d(start=0, end=max_amount * 1.1)}
p1.add_layout(LinearAxis(y_range_name="amount", axis_label="Totale Omzet (€)"), 'right')

# --- Verwijder de dubbele line() aanroep en houd er slechts één
line_renderer = p1.line(
    x="Month",
    y="Amount (Merchant Currency)",
    source=source_sales_by_month,
    color="firebrick",
    line_width=3,
    y_range_name="amount",
    legend_label="Totale Omzet"
)
p1.renderers.append(line_renderer)  # Zodat de lijn bovenop de bars komt

hover = HoverTool(tooltips=[
    ("Month", "@Month"),
    ("Transactions", "@{Transaction Count}"),
    ("Total revenue (€)", "@{Amount (Merchant Currency)}{0.00}")
])
p1.add_tools(hover)

p1.legend.location = "top_left"
p1.legend.click_policy = "hide"
p1.xaxis.major_label_orientation = 0.8
p1.ygrid.grid_line_color = None

# =====================================================================
# 3) TWEEDE VISUALISATIE: Sales per SKU (p2)
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
# 4) NIEUWE DROPDOWN: "Alle maanden" of specifieke maand
# =====================================================================
select_overview = Select(title="Month filter", value="All Months", options=["All Months"] + sorted(x_range_values))

def update_overview(attr, old, new):
    selected_overview = select_overview.value
    if selected_overview == "All Months":
        # --- p1 terug naar de originele maandaggregatie
        p1.x_range.factors = x_range_values
        source_sales_by_month.data = sales_by_month.to_dict(orient="list")
        p1.title.text = "Sales Volume Over Time (All Months)"

        # Als we meerdere factoren hebben, gebruik factor_cmap
        if len(x_range_values) == 1:
            bars_p1.glyph.fill_color = "dodgerblue"  # fallback als er maar 1 factor is
        else:
            bars_p1.glyph.fill_color = factor_cmap("Month", palette=Viridis256, factors=x_range_values)

        # --- p2 terug naar de originele maandaggregatie
        p2.x_range.factors = x_range_values
        update_sku_plot(None, None, None)
        p2.title.text = "Sales per SKU (per Month)"
        select_sku.visible = True

        # Ook hier: als er maar 1 factor is, fallback
        if len(x_range_values) == 1:
            bars_p2.glyph.fill_color = "dodgerblue"
        else:
            bars_p2.glyph.fill_color = factor_cmap("Month", palette=Viridis256, factors=x_range_values)

    else:
        # --- p1: aggregeren per dag
        df_month = df_sales[df_sales["Month"] == selected_overview].copy()
        if not df_month.empty:
            df_month["Day"] = df_month["Transaction Date"].dt.strftime("%Y-%m-%d")
            sales_by_day = df_month.groupby("Day").agg({
                "Amount (Merchant Currency)": "sum",
                "Transaction Date": "count"
            }).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()
            # Hernoem "Day" naar "Month" zodat de bar + line glyphs werken
            sales_by_day.rename(columns={"Day": "Month"}, inplace=True)
            day_list = sales_by_day["Month"].tolist()

            p1.x_range.factors = day_list
            source_sales_by_month.data = sales_by_day.to_dict(orient="list")
            p1.title.text = f"Sales Volume Over Time ({selected_overview})"

            # Fallback kleur als er maar 1 dag is
            if len(day_list) == 1:
                bars_p1.glyph.fill_color = "dodgerblue"
            else:
                bars_p1.glyph.fill_color = factor_cmap("Month", palette=Viridis256, factors=day_list)
        else:
            # Geen data
            p1.x_range.factors = []
            source_sales_by_month.data = {}
            p1.title.text = f"Sales Volume Over Time ({selected_overview})"

        # --- p2: aggregeren per SKU
        df_month_sku = df_sales[df_sales["Month"] == selected_overview].groupby("Sku Id").agg({
            "Amount (Merchant Currency)": "sum",
            "Transaction Date": "count"
        }).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()

        sku_list_month = df_month_sku["Sku Id"].tolist()
        p2.x_range.factors = sku_list_month
        source_sku_filtered.data = {
            "Month": sku_list_month,
            "amount": df_month_sku["Amount (Merchant Currency)"].tolist(),
            "count": df_month_sku["Transaction Count"].tolist()
        }
        p2.title.text = f"🛒 Verkoop per SKU ({selected_overview})"

        # Als er maar 1 SKU is, fallback kleur
        if len(sku_list_month) == 1:
            bars_p2.glyph.fill_color = "dodgerblue"
        else:
            bars_p2.glyph.fill_color = factor_cmap("Month", palette=Viridis256, factors=sku_list_month)

        # SKU dropdown onzichtbaar als specifieke maand
        select_sku.visible = False

select_overview.on_change("value", update_overview)

# =====================================================================
# 5) DERDE VISUALISATIE: Ratings vs. Crashes
# =====================================================================
df_crashes["Daily Crashes"] = df_crashes.get("Daily Crashes", np.nan).fillna(0)
df_ratings_country["Daily Average Rating"] = df_ratings_country.get("Daily Average Rating", np.nan)

ratings_crashes = df_crashes.merge(df_ratings_country, on="Date", how="left").groupby("Date").agg({
    "Daily Crashes": "first",
    "Daily Average Rating": "mean"
}).reset_index()

ratings_crashes["Rating_MA7"] = ratings_crashes["Daily Average Rating"].rolling(window=21, min_periods=1).mean()
ratings_crashes["Crashes_MA7"] = ratings_crashes["Daily Crashes"].rolling(window=7, min_periods=1).mean()
ratings_crashes_source = ColumnDataSource(ratings_crashes)
p3 = figure(
    title="Ratings vs. Crashes",
    x_axis_label="Datum",
    y_axis_label="Crashes(MA7)",
    x_axis_type="datetime",
    height=800, width=1400,
    toolbar_location="right"
)
p3.extra_y_ranges = {"rating": Range1d(start=0, end=5)}
p3.add_layout(LinearAxis(y_range_name="rating", axis_label="Gemiddelde Rating(MA21)"), 'right')

# Crashes op linker as
p3.line(
    x="Date", 
    y="Crashes_MA7",
    source=ratings_crashes_source,
    color="red",
    legend_label="Crashes(MA7)"
)
p3.line(
    x="Date",
    y="Rating_MA7",
    source=ratings_crashes_source,
    color="blue",
    line_width=2,
    y_range_name="rating",
    legend_label="Gemiddelde Rating(MA21)"
)
p3.legend.location = "top_right"

# =====================================================================
# 6) VIERDE VISUALISATIE: Geografische Kaart (Sales per Land)
# =====================================================================
shapefile_path = os.path.join(os.getcwd(), "worldmap", "ne_110m_admin_0_countries.shp")
world = gpd.read_file(shapefile_path)
world = world.to_crs("EPSG:4326")

# Verkoop per land
country_sales = df_sales.groupby("Buyer Country").agg({"Amount (Merchant Currency)": "sum"}).reset_index()
world_sales = world.merge(country_sales, how="left", left_on="ISO_A2", right_on="Buyer Country")
world_sales["Amount (Merchant Currency)"] = world_sales["Amount (Merchant Currency)"].fillna(0)

# Converteer naar GeoJSON
geo_source_sales = GeoJSONDataSource(geojson=world_sales.to_json())

# Zorgen dat één outlier niet alle kleur weghaalt
low_val = 1  
high_val = world_sales["Amount (Merchant Currency)"].max()
sales_color_mapper = LogColorMapper(palette=Plasma256, low=low_val, high=high_val)

last_idx = df_ratings_country.groupby("Country")["Date"].idxmax()
country_ratings_latest = df_ratings_country.loc[last_idx, ["Country", "Total Average Rating"]].reset_index(drop=True)
world_ratings = world.merge(country_ratings_latest, how="left", left_on="ISO_A2", right_on="Country")
world_ratings["Total Average Rating"] = world_ratings["Total Average Rating"].fillna(0)

geo_source_ratings = GeoJSONDataSource(geojson=world_ratings.to_json())

rating_color_mapper = LinearColorMapper(palette=Plasma256, low=0, high=5)
p4 = figure(title="Geografische Verdeling van Sales",
               x_axis_type="mercator", y_axis_type="mercator",
               match_aspect=True, height=800, width=1400,
               toolbar_location="right")


# Als je een tile-background wilt, uncomment deze regels:
# from bokeh.tile_providers import get_provider, CARTODBPOSITRON
# p4.add_tile(get_provider(CARTODBPOSITRON))

sales_patches = p4.patches(xs="xs", ys="ys", source=geo_source_sales,
                              fill_color={'field': 'Amount (Merchant Currency)', 'transform': sales_color_mapper},
                              fill_alpha=0.7, line_color="gray", line_width=0.5)

ratings_patches = p4.patches(xs="xs", ys="ys", source=geo_source_ratings,
                                fill_color={'field': 'Total Average Rating', 'transform': rating_color_mapper},
                                fill_alpha=0.7, line_color="gray", line_width=0.5)
ratings_patches.visible = False

# Hovertool
hover = HoverTool(renderers=[sales_patches, ratings_patches],
                  tooltips=[("Country", "@ADMIN"),
                            ("Volume (€)", "@{Amount (Merchant Currency)}{0.00}")])
p4.add_tools(hover)

select_map = Select(title="Map Type", value="Sales Volume", options=["Sales Volume", "Total Average Rating"])

def update_world_map(attr, old, new):
    if select_map.value == "Sales Volume":
        sales_patches.visible = True
        ratings_patches.visible = False
        p4.title.text = "Geografische Verdeling van Sales"
        hover.tooltips = [("Country", "@ADMIN"),
                          ("Sales (€)", "@{Amount (Merchant Currency)}{0.00}")]
    else:
        sales_patches.visible = False
        ratings_patches.visible = True
        p4.title.text = "Geografische Verdeling van Total Average Rating"
        hover.tooltips = [("Country", "@ADMIN"),
                          ("Rating", "@{Total Average Rating}{0.00}")]

select_map.on_change("value", update_world_map)
update_world_map(None, None, None)

# =====================================================================
# 7) LAYOUT (Tabs)
# =====================================================================
tab1 = TabPanel(child=column(select_overview, p1), title="Sales Over Tijd")
tab2 = TabPanel(child=column(select_overview, select_sku, p2), title="Sales per SKU")
tab3 = TabPanel(child=p3, title="Ratings vs Crashes")
tab4 = TabPanel(child=column(select_map, p4), title="Wereldkaart")

tabs = Tabs(tabs=[tab1, tab2, tab3, tab4])
curdoc().clear()
curdoc().add_root(tabs)
curdoc().title = "Data Science Dashboard"