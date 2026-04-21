import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
import dash
from dash import dcc, html, Input, Output, State
import dash_leaflet as dl
import concurrent.futures

# API Credentials
API_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"
HEADERS = {
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'authorization': f'ResyAPI api_key="{API_KEY}"'
}

NY_TZ = pytz.timezone("America/New_York")
MAX_RETRIES = 3  # Number of retries for failed requests
RETRY_DELAY = (2, 5)  # Min and max seconds to wait before retrying

# Cuisine types to query separately
CUISINES = [
    "American", "Chinese", "Cocktail Bar", "French", "Indian", "Italian",
    "Japanese", "Korean", "Mediterranean", "Mexican", "New American",
    "Seafood", "Steakhouse", "Sushi", "Thai"
]

# Search area covering Manhattan
MANHATTAN_CENTER = {"latitude": 40.712941, "longitude": -74.006393, "radius": 35420}

def fetch_cuisine_reservations(cuisine, day, party_size, target_time):
    """Fetch reservations for a specific cuisine with retry logic."""
    url = "https://api.resy.com/3/venuesearch/search"
    all_reservations = []

    for attempt in range(1, MAX_RETRIES + 1):
        payload = {
            "availability": True,
            "page": 1,
            "per_page": 100,
            "slot_filter": {"day": day, "party_size": party_size},
            "types": ["venue"],
            "order_by": "availability",
            "geo": MANHATTAN_CENTER,
            "venue_filter": {"cuisine": cuisine}
        }

        if target_time:
            try:
                target_time_24h = datetime.strptime(target_time, "%I:%M %p").strftime("%H:%M")
                payload["slot_filter"]["time_filter"] = target_time_24h
            except ValueError:
                print(f"⚠️ Invalid time format: {target_time}. Expected format: HH:MM AM/PM")
                return []

        try:
            response = requests.post(url, json=payload, headers=HEADERS, timeout=10)

            if response.status_code == 502:
                print(f"⚠️ 502 Bad Gateway for {cuisine}. Retrying... ({attempt}/{MAX_RETRIES})")
                time.sleep(min(RETRY_DELAY) + (attempt * 1))  # Increase delay per attempt
                continue  # Retry request

            if response.status_code != 200:
                print(f"❌ API Error {response.status_code} for {cuisine}: {response.text}")
                return []  # Skip cuisine if the API is failing

            try:
                data = response.json()
            except ValueError:
                print(f"⚠️ Invalid JSON response for {cuisine}. Skipping...")
                return []  # If JSON decoding fails, skip

            if "meta" not in data or "search" not in data:
                print(f"⚠️ Unexpected API structure for {cuisine}: {data}")
                return []

            total_pages = min(10, int(data["meta"].get("total_pages", 0)))

            if total_pages == 0:
                print(f"ℹ️ No reservations found for {cuisine}.")
                return []

            for page in range(1, total_pages + 1):
                payload["page"] = page
                response = requests.post(url, json=payload, headers=HEADERS)

                try:
                    results = response.json()
                except ValueError:
                    print(f"⚠️ Skipping invalid JSON response for {cuisine} page {page}.")
                    continue

                if "search" not in results or "hits" not in results["search"]:
                    continue

                for restaurant in results["search"]["hits"]:
                    venue_name = restaurant["name"]
                    neighborhood = restaurant["neighborhood"].strip()
                    slug = restaurant['url_slug']
                    rating = restaurant.get("rating", {}).get("average", "N/A")
                    total_ratings = restaurant.get("rating", {}).get("count", "N/A")
                    price_range = restaurant.get("price_range_id", 0)
                    cuisine_type = restaurant.get("cuisine", ["Unknown"])[0]
                    latitude = restaurant["_geoloc"]["lat"]
                    longitude = restaurant["_geoloc"]["lng"]

                    try:
                        icon_image = restaurant["images"][0]
                    except:
                        icon_image = 'https://img.freepik.com/premium-vector/cartoon-orange_24381-186.jpg'

                    for slot in restaurant.get("availability", {}).get("slots", []):
                        reservation_dt = NY_TZ.localize(datetime.strptime(slot["date"]["start"], "%Y-%m-%d %H:%M:%S"))

                        all_reservations.append({
                            "Venue Name": venue_name,
                            "Neighborhood": neighborhood,
                            "Rating": rating,
                            "Total Ratings": total_ratings,
                            "Price Range": "$" * price_range,
                            "Cuisine Type": cuisine_type,
                            "Date": reservation_dt.strftime("%Y-%m-%d"),
                            "Time (NYC)": reservation_dt.strftime("%I:%M %p"),
                            "Table Size": party_size,
                            "Dining Type": slot["config"]["type"],
                            "Reservation Link": f"https://resy.com/cities/new-york-ny/venues/{slug}?date={day}&seats={party_size}",
                            "Latitude": latitude,
                            "Longitude": longitude,
                            "Icon Image": icon_image
                        })

            return all_reservations  # Return results if successful

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Network error for {cuisine}: {e}. Retrying ({attempt}/{MAX_RETRIES})")
            time.sleep(min(RETRY_DELAY) + (attempt * 1))  # Increase delay per attempt

    print(f"🚫 Giving up on {cuisine} after {MAX_RETRIES} attempts.")
    return []  # Return empty list if all retries fail

def fetch_available_reservations(day, party_size, target_time=None):
    """Fetch reservations for all cuisines concurrently with better error handling."""
    all_reservations = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:  # Reduce max_workers to avoid API blocks
        futures = {
            executor.submit(fetch_cuisine_reservations, cuisine, day, party_size, target_time): cuisine
            for cuisine in CUISINES
        }

        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                all_reservations.extend(result)
            except Exception as e:
                print(f"⚠️ Error fetching reservations for {futures[future]}: {e}")

    if not all_reservations:
        print("🚫 No reservations found for any cuisine!")

    return pd.DataFrame(all_reservations).drop_duplicates(subset=['Reservation Link'])

def generate_tiles(df_results):
    tiles = []
    for _, row in df_results.iterrows():
        formatted_time = row['Time (NYC)']
        reservation_text = f"Reserve - {formatted_time}"

        avg_rating = round(float(row['Rating']), 2) if pd.notna(row['Rating']) else 0.00
        total_ratings = int(row['Total Ratings']) if pd.notna(row['Total Ratings']) else 0
        price_range = row['Price Range']

        tile = html.Div(
            style={
                'border': '1px solid #FF5722', 'borderRadius': '10px', 'padding': '10px',
                'margin': '10px', 'width': '260px', 'backgroundColor': '#FFFFFF',
                'boxShadow': '0px 4px 8px rgba(0, 0, 0, 0.2)', 'textAlign': 'center',
                'position': 'relative'
            },
            children=[
                # ✅ Title (Centered)
                html.Div([
                    html.H3(row["Venue Name"], style={'color': '#FF5722', 'margin': '0px', 'fontSize': '16px'}),
                ], style={'textAlign': 'center', 'marginBottom': '5px'}),

                # ✅ Price in Top Right Corner
                html.Div(
                    price_range,
                    style={
                        'position': 'absolute', 'top': '10px', 'right': '10px',
                        'color': 'green', 'fontSize': '16px', 'fontWeight': 'bold'
                    }
                ),

                # ✅ Restaurant Image (Smaller)
                html.Img(
                    src=row['Icon Image'],
                    style={'width': '100%', 'height': '120px', 'objectFit': 'cover', 'borderRadius': '10px'}
                ),

                # ✅ Rating & Total Reviews (Same Line)
                html.Div([
                    html.Span(f"⭐ {avg_rating}", style={'color': '#FFC107', 'fontSize': '14px', 'fontWeight': 'bold', 'marginRight': '5px'}),
                    html.Span(f"({total_ratings})", style={'color': 'blue', 'fontSize': '14px', 'fontWeight': 'bold'}),
                ], style={'marginTop': '5px'}),

                # ✅ Neighborhood & Cuisine Type
                html.P(f"{row['Neighborhood']} | {row['Cuisine Type']}", style={'fontWeight': 'bold', 'marginTop': '10px'}),

                # ✅ Reservation Button
                html.A(
                    html.Button(reservation_text, style={
                        'backgroundColor': '#FF5722', 'color': 'white', 'border': 'none',
                        'padding': '8px 15px', 'borderRadius': '5px', 'cursor': 'pointer',
                        'fontSize': '14px', 'marginTop': '10px', 'width': '100%'
                    }),
                    href=row["Reservation Link"], target="_blank"
                )
            ]
        )
        tiles.append(tile)

    return tiles

app = dash.Dash(__name__)
app.title = "Find Reservation"

app.layout = html.Div(style={
    'backgroundColor': '#FFF3E0',
    'padding': '20px',
    'borderRadius': '10px',
    'display': 'flex',
    'flexDirection': 'row',
    'alignItems': 'flex-start'  # Ensures alignment at the top
}, children=[

    # ✅ Store component to hold API data
    dcc.Store(id="stored_data"),

    # Left Sidebar (Search + Filters + Map)
    html.Div(style={'width': '25%', 'padding': '10px', 'display': 'flex', 'flexDirection': 'column'}, children=[

        # ✅ Section 1: Find Reservations (REQUIRED FIELDS)
        html.H3("Find Reservations", style={'color': '#FF5722', 'textAlign': 'center', 'marginBottom': '10px', 'fontSize': '24px'}),

        # ✅ Row Layout for Inputs (Date, Time, Party Size)
        html.Div(style={'display': 'flex', 'flexDirection': 'row', 'gap': '10px', 'alignItems': 'center'}, children=[
            html.Div([
                html.Label("Select Date:", style={'fontWeight': 'bold', 'fontSize': '18px'}),
                dcc.DatePickerSingle(
                    id="date_picker",
                    date=datetime.today().strftime("%Y-%m-%d"),
                    min_date_allowed=datetime.today(),
                    max_date_allowed=datetime.today() + timedelta(days=30),
                    style={'width': '120px'}
                ),
            ], style={'width': '33%'}),

            html.Div([
                html.Label("Enter Time:", style={'fontWeight': 'bold', 'fontSize': '18px'}),
                dcc.Input(
                    id="time_input",
                    type="text",
                    placeholder="06:00 PM",
                    value="06:00 PM",
                    style={'width': '100px'}
                ),
            ], style={'width': '33%'}),

            html.Div([
                html.Label("Party Size:", style={'fontWeight': 'bold', 'fontSize': '18px'}),
                dcc.Input(
                    id="party_size",
                    type="number",
                    value=2,
                    min=1,
                    max=10,
                    step=1,
                    style={'width': '60px'}
                ),
            ], style={'width': '33%'}),
        ]),

        # ✅ Find Reservations Button
        html.Button(
            "Find Reservations",
            id="search_button",
            n_clicks=0,
            style={'backgroundColor': '#FF5722', 'color': 'white', 'width': '100%', 'marginTop': '15px', 'padding': '10px', 'fontSize': '18px', 'fontWeight': 'bold'}
        ),


        # ✅ Section 2: Apply Filters (Optional)
        html.H3("Apply Filters", style={'color': '#FF5722', 'textAlign': 'center', 'marginBottom': '10px'}),

        html.Label("Filter by Price Range:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id="price_filter",
            placeholder="Select Price Range ($,$$,$$$,$$$$)",
            multi=True,
            style={'marginBottom': '10px'}
        ),

        html.Label("Filter by Cuisine Type:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id="cuisine_filter",
            placeholder="Select Cuisine Type",
            multi=True,
            style={'marginBottom': '10px'}
        ),

        html.Label("Filter by Neighborhood:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id="location_filter",
            placeholder="Select Neighborhood",
            multi=True,
            style={'marginBottom': '10px'}
        ),

        # ✅ Apply Filters Button
        html.Button(
            "Apply Filters",
            id="filter_button",
            n_clicks=0,
            style={'backgroundColor': '#FF5722', 'color': 'white', 'width': '100%', 'marginTop': '10px'}
        ),

        # ✅ Map Section (Directly Under Everything)
        html.H3("Map", style={'color': '#FF5722', 'textAlign': 'center', 'marginTop': '20px'}),
        dl.Map(center=[40.7128, -74.0060], zoom=12, children=[
            dl.TileLayer(),
            dl.LayerGroup(id="marker_layer")
        ], style={'width': '100%', 'height': '400px', 'border': '2px solid #FF5722', 'borderRadius': '10px', 'marginTop': '10px'})
    ]),

        # Center Section (Tiles Display)
        html.Div(style={'width': '50%', 'padding': '10px'}, children=[
            html.H1("Manhattan Reservations Finder",
                    style={'textAlign': 'center', 'color': '#FF5722', 'marginBottom': '20px'}),

            # ✅ Loading message (Shown when searching for reservations)
            html.Div(id="loading_message", style={'textAlign': 'center', 'color': '#FF5722', 'fontSize': '20px', 'marginBottom': '10px'}),

            # Display total results and unique restaurants count
            html.Div(id="total_results", style={'textAlign': 'center', 'color': '#FF5722', 'fontSize': '20px', 'marginBottom': '10px'}),
            html.Div(id="total_restaurants", style={'textAlign': 'center', 'color': '#FF5722', 'fontSize': '20px', 'marginBottom': '10px'}),

            # Results Tiles (Three columns, aligned properly)
            html.Div(id='results_tiles',
                    style={
                        'display': 'grid',
                        'gridTemplateColumns': 'repeat(3, 1fr)',  # Three tiles per row
                        'gap': '15px',  # Space between tiles
                        'justifyContent': 'start',  # Aligns left
                        'padding': '20px 10px',  # Padding inside the container
                        'marginTop': '20px',  # Keeps it aligned under filters
                        'width': '100%'  # Ensures full width
                    })
        ])

])


@app.callback(
    [Output("stored_data", "data"),
     Output("results_tiles", "children"),
     Output("price_filter", "options"),
     Output("cuisine_filter", "options"),
     Output("location_filter", "options"),
     Output("total_results", "children"),
     Output("total_restaurants", "children"),
     Output("marker_layer", "children"),
     Output("loading_message", "children")],  # <-- Added output for loading message

    [Input("search_button", "n_clicks"),
     Input("filter_button", "n_clicks")],

    [State("stored_data", "data"),
     State("date_picker", "date"),
     State("time_input", "value"),
     State("party_size", "value"),
     State("price_filter", "value"),
     State("cuisine_filter", "value"),
     State("location_filter", "value")],

    prevent_initial_call=True
)
def update_results(search_clicks, filter_clicks, stored_data, date, time_input, party_size, price_filter, cuisine_filter, location_filter):
    ctx = dash.callback_context
    if not ctx.triggered:
        return None, [], [], [], [], "Total Results: 0", "Unique Restaurants: 0", [], ""

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    # ✅ Show loading message when searching for reservations
    loading_message = "🔄 Finding your table..."

    if triggered_id == "search_button" or stored_data is None:
        print("🔄 Fetching fresh data from API...")
        df_results = fetch_available_reservations(date, party_size, time_input)
        stored_data = df_results.to_json()
    else:
        print("✅ Using cached data...")
        df_results = pd.read_json(stored_data)

    # ✅ Remove loading message once data is fetched
    loading_message = ""

    # Apply filters if Apply Filters button is clicked
    if triggered_id == "filter_button":
        if price_filter:
            df_results = df_results[df_results["Price Range"].isin(price_filter)]
        if cuisine_filter:
            df_results = df_results[df_results["Cuisine Type"].isin(cuisine_filter)]
        if location_filter:
            df_results = df_results[df_results["Neighborhood"].isin(location_filter)]

    # Handle empty results
    if df_results.empty:
        return stored_data, [html.P("No results found.", style={'textAlign': 'center', 'color': 'red'})], [], [], [], "Total Results: 0", "Unique Restaurants: 0", [], ""

    # Generate UI Tiles
    tiles = generate_tiles(df_results)

    # Generate Map Markers
    markers = [
        dl.Marker(
            position=[row["Latitude"], row["Longitude"]],
            children=[dl.Tooltip(row["Venue Name"])]
        ) for _, row in df_results.iterrows()
    ]

    # Update dropdown options dynamically
    price_options = [{"label": p, "value": p} for p in sorted(df_results["Price Range"].unique())]
    cuisine_options = [{"label": c, "value": c} for c in sorted(df_results["Cuisine Type"].unique())]
    location_options = [{"label": l, "value": l} for l in sorted(df_results["Neighborhood"].unique())]

    total_reservations = len(df_results)
    unique_restaurants = df_results["Venue Name"].nunique()

    return stored_data, tiles, price_options, cuisine_options, location_options, f"Total Results: {total_reservations}", f"Unique Restaurants: {unique_restaurants}", markers, loading_message


if __name__ == "__main__":
    app.run_server(debug=False)