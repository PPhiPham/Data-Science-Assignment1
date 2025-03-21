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
                          Select, HoverTool, GeoJSONDataSource, Tabs, TabPanel, LogColorMapper, LinearColorMapper, Dropdown, MultiSelect)
from bokeh.layouts import row, column
from bokeh.transform import factor_cmap, dodge
from bokeh.palettes import Plasma256, Viridis256

from bokeh.embed import file_html
from bokeh.resources import CDN

# =====================================================================
# 1) DATA LOADING
# =====================================================================
data_path = os.path.join(os.getcwd(), "data")
csv_files = glob.glob(os.path.join(data_path, "*.csv"))

sales_data = []
crash_data = []
ratings_data_country = []

for file in csv_files:
    with open(file, "rb") as f:
        result = chardet.detect(f.read(100000))
        detected_encoding = result["encoding"]

    df = pd.read_csv(file, encoding=detected_encoding)

    # Identify Sales data
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
            "Charged": "Charge"
        })
        df = df[df["Product id"] == "com.vansteinengroentjes.apps.ddfive"]
        df = df[df["Transaction Type"] == "Charge"]
        if "Transaction Date" in df.columns:
            df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors='coerce')
        sales_data.append(df)

    # Identify Crash data
    elif "Daily Crashes" in df.columns and "Daily ANRs" in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        crash_data.append(df)

    # Identify Ratings_country data
    elif "Daily Average Rating" in df.columns and "Country" in df.columns:
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        ratings_data_country.append(df)

# Operations to make the two aberrant sales files be included      
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

# Put every type of data into their respective dataframe
df_sales = pd.concat(sales_data, ignore_index=True) if sales_data else pd.DataFrame()
df_crashes = pd.concat(crash_data, ignore_index=True) if crash_data else pd.DataFrame()
df_ratings_country = pd.concat(ratings_data_country, ignore_index=True) if ratings_data_country else pd.DataFrame()
df_sales["Month"] = df_sales["Transaction Date"].dt.to_period("M").astype(str)

# =====================================================================
# 2) FIRST VISUALIZATION: Sales Volume Over Time (p1)
# =====================================================================
# Fetch data for this visualization
sales_by_month = df_sales.groupby("Month").agg({
    "Amount (Merchant Currency)": "sum",
    "Transaction Date": "count"
}).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()

source_sales_by_month = ColumnDataSource(sales_by_month)
x_range_values = sales_by_month["Month"].tolist()


# Visualization 1 styling
p1 = figure(
    title="Sales Volume Over Time (All Months)",
    x_range=x_range_values,
    height=700, width=1400,
    x_axis_label="Month", 
    y_axis_label="Transactions",
    toolbar_location="right"
)

line_renderer = None

# Bars for transactions
bars_p1 = p1.vbar(
    x="Month",
    top="Transaction Count",
    source=source_sales_by_month,
    width=0.5,
    fill_color=factor_cmap('Month', palette=Viridis256, factors=x_range_values),
    line_color="black",
    legend_label="Transactions"
)

max_amount = sales_by_month["Amount (Merchant Currency)"].max()
max_transactions = sales_by_month["Transaction Count"].max()
p1.extra_y_ranges = {"amount": Range1d(start=0, end=max_amount * 1.1)}
p1.y_range = Range1d(start=0, end=max_transactions * 1.1)  # Adjust the transaction axis
p1.add_layout(LinearAxis(y_range_name="amount", axis_label="Total Turnover (€)"), 'right')

# Ensure red line is added last so it's always on top (visible)
def add_trend_line():
    global line_renderer
    if line_renderer is not None and line_renderer in p1.renderers:
        p1.renderers.remove(line_renderer)
    line_renderer = p1.line(
        x="Month",
        y="Amount (Merchant Currency)",
        source=source_sales_by_month,
        color="firebrick",
        line_width=3,
        y_range_name="amount",
        legend_label="Total Turnover"
    )
    p1.renderers.append(line_renderer)

add_trend_line()

hover = HoverTool(tooltips=[
    ("Month", "@Month"),
    ("Transactions", "@{Transaction Count}"),
    ("Total Turnover (€)", "@{Amount (Merchant Currency)}{0.00}")
])
p1.add_tools(hover)

p1.legend.location = "top_left"
p1.legend.click_policy = "hide"
p1.xaxis.major_label_orientation = 0.8
p1.ygrid.grid_line_color = None

# Ensure select_overview is defined before calling on_change
select_overview = Select(title="Month Filter", value="All Months", options=["All Months"] + sorted(x_range_values))

def update_overview(attr, old, new):
    selected_overview = select_overview.value
    if selected_overview == "All Months":
        p1.x_range.factors = x_range_values
        source_sales_by_month.data = sales_by_month.to_dict(orient="list")
        p1.title.text = "Sales Volume Over Time (All Months)"
        p1.y_range.end = max_transactions * 1.1  # Reset the transaction axis
        p1.extra_y_ranges["amount"].end = max_amount * 1.1  # Reset the turnover axis
    else:
        df_month = df_sales[df_sales["Month"] == selected_overview].copy()
        if not df_month.empty:
            df_month["Day"] = df_month["Transaction Date"].dt.strftime("%Y-%m-%d")
            sales_by_day = df_month.groupby("Day").agg({
                "Amount (Merchant Currency)": "sum",
                "Transaction Date": "count"
            }).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()
            sales_by_day.rename(columns={"Day": "Month"}, inplace=True)
            day_list = sales_by_day["Month"].tolist()
            p1.x_range.factors = day_list
            source_sales_by_month.data = sales_by_day.to_dict(orient="list")
            p1.title.text = f"Sales Volume Over Time ({selected_overview})"
            max_day_amount = sales_by_day["Amount (Merchant Currency)"].max()
            max_day_transactions = sales_by_day["Transaction Count"].max()
            p1.y_range.end = max_day_transactions * 0.01  # Adjust the transaction axis dynamically
            p1.extra_y_ranges["amount"].end = max_day_amount * 0.01  # Adjust the turnover axis dynamically
        else:
            p1.x_range.factors = []
            source_sales_by_month.data = {}
            p1.title.text = f"Sales Volume Over Time ({selected_overview})"
            p1.y_range.end = max_transactions * 1.1  # Reset if there is no data
            p1.extra_y_ranges["amount"].end = max_amount * 1.1
    
    add_trend_line()  # Ensure the red line is always on top

select_overview.on_change("value", update_overview)
update_overview(None, None, None)

# =====================================================================
# 3) SECOND VISUALIZATION: Sales per SKU (p2)
# =====================================================================
# Fetch data for second visualization 
unique_skus = df_sales["Sku Id"].dropna().unique().tolist()
unique_skus.sort()

sku_sales_df = df_sales.groupby(["Sku Id", "Month"]).agg({
    "Amount (Merchant Currency)": "sum",
    "Transaction Date": "count"
}).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()

source_sku_filtered = ColumnDataSource(data=dict(Month=[], amount=[], count=[]))

# Second visualization styling
p2 = figure(
    title="Sales per SKU (per Month)",
    x_range=x_range_values,
    height=700, width=1400,
    x_axis_label="Month", 
    y_axis_label="Total Turnover (€)",
    toolbar_location="right"
)

# Bars for the selected SKU's revenue
bars_p2 = p2.vbar(
    x="Month",
    top="amount",
    source=source_sku_filtered,
    width=0.5,
    fill_color=factor_cmap('Month', palette=Viridis256, factors=x_range_values)
    if len(x_range_values) > 1 else "dodgerblue",
    line_color="black",
    legend_label="SKU Turnover"
)

# Trendline for overall revenue in p2 (only in the All Months view)
line_renderer2 = None

# SKU filter (active only in the All Months view)
select_sku = Select(title="SKU filter", value=unique_skus[0], options=unique_skus)
def update_sku_plot(attr, old, new):
    selected_sku = select_sku.value
    df_filtered = sku_sales_df[sku_sales_df["Sku Id"] == selected_sku].copy()
    df_filtered = df_filtered.set_index("Month").reindex(x_range_values, fill_value=0).reset_index()
    df_filtered.rename(columns={"index": "Month"}, inplace=True)
    source_sku_filtered.data = dict(
        Month=df_filtered["Month"],
        amount=df_filtered["Amount (Merchant Currency)"],
        count=df_filtered["Transaction Count"]
    )
select_sku.on_change("value", update_sku_plot)
update_sku_plot(None, None, None)

hover_sku = HoverTool(tooltips=[
    ("Month", "@Month"),
    ("Turnover (€)", "@amount{0.00}"),
    ("Transactions", "@count")
])
p2.add_tools(hover_sku)

# =====================================================================
# 4) NEW DROPDOWN: "All Months" or Specific Month
# =====================================================================
select_overview = Select(title="Month Filter", value="All Months", options=["All Months"] + sorted(x_range_values))

def update_overview(attr, old, new):
    global line_renderer2
    selected_overview = select_overview.value
    if selected_overview == "All Months":
        # p1: restore monthly aggregation
        p1.x_range.factors = x_range_values
        source_sales_by_month.data = sales_by_month.to_dict(orient="list")
        p1.title.text = "Sales Volume Over Time (All Months)"
        if len(x_range_values) == 1:
            bars_p1.glyph.fill_color = "dodgerblue"
        else:
            bars_p1.glyph.fill_color = factor_cmap("Month", palette=Viridis256, factors=x_range_values)
        
        # p2: restore monthly aggregation for SKU data
        p2.x_range.factors = x_range_values
        update_sku_plot(None, None, None)
        p2.title.text = "Sales per SKU (per Month)"
        select_sku.visible = True
        if len(x_range_values) == 1:
            bars_p2.glyph.fill_color = "dodgerblue"
        else:
            bars_p2.glyph.fill_color = factor_cmap("Month", palette=Viridis256, factors=x_range_values)
        
        if line_renderer2 is None:
            line_renderer2 = p2.line(
                x="Month",
                y="Amount (Merchant Currency)",
                source=source_sales_by_month,
                color="firebrick",
                line_width=3,
                legend_label="Total Turnover"
            )
            p2.renderers.append(line_renderer2)
            hover_line = HoverTool(renderers=[line_renderer2],
                                   tooltips=[("Month", "@Month"),
                                             ("Total Turnover (€)", "@{Amount (Merchant Currency)}{0.00}")])
            p2.add_tools(hover_line)
    else:
        # Specific month selected:
        # p1: aggregate by day for the selected month
        df_month = df_sales[df_sales["Month"] == selected_overview].copy()
        if not df_month.empty:
            df_month["Day"] = df_month["Transaction Date"].dt.strftime("%Y-%m-%d")
            sales_by_day = df_month.groupby("Day").agg({
                "Amount (Merchant Currency)": "sum",
                "Transaction Date": "count"
            }).rename(columns={"Transaction Date": "Transaction Count"}).reset_index()
            sales_by_day.rename(columns={"Day": "Month"}, inplace=True)
            day_list = sales_by_day["Month"].tolist()
            p1.x_range.factors = day_list
            source_sales_by_month.data = sales_by_day.to_dict(orient="list")
            p1.title.text = f"Sales Volume Over Time ({selected_overview})"
            if len(day_list) == 1:
                bars_p1.glyph.fill_color = "dodgerblue"
            else:
                bars_p1.glyph.fill_color = factor_cmap("Month", palette=Viridis256, factors=day_list)
        else:
            p1.x_range.factors = []
            source_sales_by_month.data = {}
            p1.title.text = f"Sales Volume Over Time ({selected_overview})"
        
        # p2: aggregate by SKU for the selected month
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
        p2.title.text = f"Sales per SKU ({selected_overview})"
        if len(sku_list_month) == 1:
            bars_p2.glyph.fill_color = "dodgerblue"
        else:
            bars_p2.glyph.fill_color = factor_cmap("Month", palette=Viridis256, factors=sku_list_month)
        select_sku.visible = False
        if line_renderer2 is not None:
            try:
                p2.renderers.remove(line_renderer2)
            except Exception:
                pass
            line_renderer2 = None

select_overview.on_change("value", update_overview)

# =====================================================================
# 5) THIRD VISUALIZATION: Ratings vs. Crashes (p3)
# =====================================================================
# Fetch data for the third visualization
df_crashes["Daily Crashes"] = df_crashes.get("Daily Crashes", np.nan).fillna(0)
df_ratings_country["Daily Average Rating"] = df_ratings_country.get("Daily Average Rating", np.nan)
ratings_crashes = df_crashes.merge(df_ratings_country, on="Date", how="left").groupby("Date").agg({
    "Daily Crashes": "first",
    "Daily Average Rating": "mean"
}).reset_index()
# Create moving averages for better readability
ratings_crashes["Rating_MA21"] = ratings_crashes["Daily Average Rating"].rolling(window=21, min_periods=1).mean()
ratings_crashes["Crashes_MA7"] = ratings_crashes["Daily Crashes"].rolling(window=7, min_periods=1).mean()
ratings_crashes_source = ColumnDataSource(ratings_crashes)

# Third visualization styling
p3 = figure(
    title="Ratings vs. Crashes",
    x_axis_label="Date",
    y_axis_label="Crashes (7-day MA)",
    x_axis_type="datetime",
    height=700, width=1400,
    toolbar_location="right",
    background_fill_color="white" 
)

# Add a second y-axis for Average Rating (21-day MA)
p3.extra_y_ranges = {"rating": Range1d(start=0, end=5)}
p3.add_layout(LinearAxis(y_range_name="rating", axis_label="Average Rating (21-day MA)"), 'right')

# Draw the Crashes line in purple (solid)
crashes_line = p3.line(
    x="Date",
    y="Crashes_MA7",
    source=ratings_crashes_source,
    color="purple",
    line_width=3,
    legend_label="Crashes (7-day MA)"
)

# Draw the Average Rating line in black (dashed)
rating_line = p3.line(
    x="Date",
    y="Rating_MA21",
    source=ratings_crashes_source,
    color="black",
    line_width=3,
    line_dash="dashed",
    y_range_name="rating",
    legend_label="Average Rating (21-day MA)",
    line_alpha= 0.75
)

p3.legend.location = "top_left"
p3.legend.click_policy = "hide"
p3.xaxis.major_label_orientation = 0.8
p3.xgrid.grid_line_color = None
p3.ygrid.grid_line_color = None

hover_tool = HoverTool(
    renderers=[crashes_line, rating_line],
    tooltips=[
        ("Date", "@Date{%F}"),
        ("Crashes (7-day MA)", "@Crashes_MA7{0.0}"),
        ("Average Rating (21-day MA)", "@Rating_MA21{0.0}")
    ],
    formatters={"@Date": "datetime"}
)
p3.add_tools(hover_tool)

# =====================================================================
# 6) FOURTH VISUALIZATION: World Map (Sales per Country)
# =====================================================================
# Fetch data fourth visualization 
shapefile_path = os.path.join(os.getcwd(), "worldmap", "ne_110m_admin_0_countries.shp")
world = gpd.read_file(shapefile_path)
world = world.to_crs("EPSG:4326")
country_sales = df_sales.groupby("Buyer Country").agg({"Amount (Merchant Currency)": "sum"}).reset_index()
world_sales = world.merge(country_sales, how="left", left_on="ISO_A2", right_on="Buyer Country")
world_sales["Amount (Merchant Currency)"] = world_sales["Amount (Merchant Currency)"].fillna(0)
geo_source_sales = GeoJSONDataSource(geojson=world_sales.to_json())

# Ensure that the colouring isnt favoured for the US to heavily
low_val = 1  
high_val = world_sales["Amount (Merchant Currency)"].max()
sales_color_mapper = LogColorMapper(palette=Plasma256, low=low_val, high=high_val)

last_idx = df_ratings_country.groupby("Country")["Date"].idxmax()
country_ratings_latest = df_ratings_country.loc[last_idx, ["Country", "Total Average Rating"]].reset_index(drop=True)
world_ratings = world.merge(country_ratings_latest, how="left", left_on="ISO_A2", right_on="Country")
world_ratings["Total Average Rating"] = world_ratings["Total Average Rating"].fillna(0)
geo_source_ratings = GeoJSONDataSource(geojson=world_ratings.to_json())
rating_color_mapper = LinearColorMapper(palette=Plasma256, low=0, high=5)

# Fourth visualization styling
p4 = figure(
    title="Geographical Distribution of Sales",
    x_axis_type="mercator", 
    y_axis_type="mercator",
    match_aspect=True, 
    height=700, 
    width=1400,
    toolbar_location="right"
)

p4.xaxis.visible = False
p4.yaxis.visible = False

sales_patches = p4.patches(
    xs="xs", 
    ys="ys", 
    source=geo_source_sales,
    fill_color={'field': 'Amount (Merchant Currency)', 'transform': sales_color_mapper},
    fill_alpha=0.7, 
    line_color="gray", 
    line_width=0.5
)

ratings_patches = p4.patches(
    xs="xs", 
    ys="ys", 
    source=geo_source_ratings,
    fill_color={'field': 'Total Average Rating', 'transform': rating_color_mapper},
    fill_alpha=0.7, 
    line_color="gray", 
    line_width=0.5
)

ratings_patches.visible = False
hovertool = HoverTool(renderers=[sales_patches, ratings_patches],
                  tooltips=[("Country", "@ADMIN"),
                            ("Volume (€)", "@{Amount (Merchant Currency)}{0.00}")])
p4.add_tools(hovertool)
select_map = Select(title="Map Type", value="Sales Volume", options=["Sales Volume", "Total Average Rating"])
def update_world_map(attr, old, new):
    if select_map.value == "Sales Volume":
        sales_patches.visible = True
        ratings_patches.visible = False
        p4.title.text = "Geographical Distribution of Sales"
        hovertool.tooltips = [("Country", "@ADMIN"),
                              ("Sales (€)", "@{Amount (Merchant Currency)}{0.00}")]
    else:
        sales_patches.visible = False
        ratings_patches.visible = True
        p4.title.text = "Geographical Distribution of Total Average Rating"
        hovertool.tooltips = [("Country", "@ADMIN"),
                              ("Rating", "@{Total Average Rating}{0.00}")]
select_map.on_change("value", update_world_map)
update_world_map(None, None, None)
# =====================================================================
# 7) FIFTH VISUALIZATION: Transactions and Total Average Rating by Country (except the US)
# =====================================================================
# Fetch data for the fifth visualization
transactions_per_country = df_sales.groupby("Buyer Country").size().reset_index(name="Transactions")
transactions_per_country.rename(columns={"Buyer Country": "Country"}, inplace=True)

ratings_per_country = df_ratings_country.groupby("Country").agg({"Total Average Rating": "last"}).reset_index()
country_data = pd.merge(transactions_per_country, ratings_per_country, on="Country", how="outer")

country_data["Transactions"] = country_data["Transactions"].fillna(0)
country_data["Total Average Rating"] = country_data["Total Average Rating"].fillna(0)
country_data = country_data[(country_data["Transactions"] > 0) & (country_data["Country"] != "US")]
country_data = country_data.sort_values(by="Transactions", ascending=False)
countries = list(country_data["Country"])
source = ColumnDataSource(country_data)

max_transactions = country_data["Transactions"].max()

# Fifth visualization styling
p5 = figure(
    x_range=countries,
    title="Transactions and Total Average Rating by \"emerging\" Countries (except the US)",
    height=600,
    width=1200,
    toolbar_location="right",
    x_axis_label="Country",
    y_range=Range1d(start=0, end=max_transactions * 1.1)
)

p5.vbar(
    x=dodge('Country', -0.15, range=p5.x_range),
    top='Transactions',
    width=0.3,
    source=source,
    color="purple",
    legend_label="Transactions"
)

p5.extra_y_ranges = {"rating": Range1d(start=0, end=5)}
p5.add_layout(LinearAxis(y_range_name="rating", axis_label="Total Average Rating"), 'right')

p5.vbar(
    x=dodge('Country', 0.15, range=p5.x_range),
    bottom=0,
    top='Total Average Rating',
    width=0.3,
    source=source,
    color="purple",
    y_range_name="rating",
    legend_label="Total Average Rating",
    fill_alpha=0.25
)

p5.xgrid.grid_line_color = None
p5.legend.location = "top_left"
p5.legend.orientation = "horizontal"

hover_p5 = HoverTool(
    tooltips=[
        ("Country", "@Country"),
        ("Transactions", "@Transactions{0,0}"),
        ("Avg. Rating", "@{Total Average Rating}{0.00}")
    ]
)
p5.add_tools(hover_p5)

unique_countries = ["All Countries"] + sorted(country_data["Country"].unique().tolist())
select_country_p5 = Select(title="Country Filter", value="All Countries", options=unique_countries)

def update_p5(attr, old, new):
    selected_country = select_country_p5.value
    if selected_country == "All Countries":
        filtered_data = country_data
    else:
        filtered_data = country_data[country_data["Country"] == selected_country]

    source.data = {
        "Country": filtered_data["Country"].tolist(),
        "Transactions": filtered_data["Transactions"].tolist(),
        "Total Average Rating": filtered_data["Total Average Rating"].tolist(),
    }

    p5.x_range.factors = filtered_data["Country"].tolist()

    max_filtered_transactions = filtered_data["Transactions"].max() if not filtered_data.empty else 1
    p5.y_range.end = max(max_filtered_transactions * 1.1, 10)

select_country_p5.on_change("value", update_p5)
update_p5(None, None, None)


# =====================================================================
# 8) LAYOUT (Tabs)
# =====================================================================
tab1 = TabPanel(child=column(select_overview, p1), title="Sales Over Time")
tab2 = TabPanel(child=column(row(select_overview, select_sku), p2), title="Sales per SKU")
tab3 = TabPanel(child=p3, title="Ratings vs. Crashes")
tab4 = TabPanel(child=column(select_map, p4), title="World Map")
tab5 = TabPanel(child=column(select_country_p5, p5), title="View per country")
tabs = Tabs(tabs=[tab1, tab2, tab3, tab4, tab5])

curdoc().clear()
curdoc().add_root(tabs)
curdoc().theme = 'light_minimal'
curdoc().title = "Emarald-IT Dashboard"

# =====================================================================
# 9) Queries
# =====================================================================
#query that shows the countries with the lowest/highest Total average rating with their respective number of transactions
latest_idx = df_ratings_country.groupby("Country")["Date"].idxmax()
latest_ratings = df_ratings_country.loc[latest_idx].copy()
result = latest_ratings.merge(transactions_per_country, on="Country", how="left")
result = result.sort_values("Total Average Rating", ascending=True) #False for descending
# 'tabs' is your main layout (the Tabs object in your code)
html = file_html(tabs, CDN, "Data Science Dashboard")

with open("dashboard.html", "w") as f:
    f.write(html)
#print(result[["Country", "Total Average Rating", "Transactions"]].head(50))