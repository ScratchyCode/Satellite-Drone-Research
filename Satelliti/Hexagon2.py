# Coded by Pietro Squilla
# Analisi foto satellitari per la ricerca e pianificazione delle attività (mitigazione limitazioni di Google)

# installare le librerie necessarie con:
#     pip install googlemaps
#     pip install Jinja2

##################
#    LIBRERIE    #
##################

import googlemaps
import os
import requests
from math import log2, tan, pi
from io import BytesIO
from PIL import Image
import numpy as np
from jinja2 import Template
from functools import cmp_to_key
from googlemaps.exceptions import ApiError
import sys
import time
from jinja2 import Template
import math
import re

#############
#    KEY    #
#############
API_KEY = "xxx" # <--------------------------------------------------------------------------------------------------------

##################
#    FUNZIONI    #
##################

def create_folder_if_not_exists(folder_name):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)


def save_text_file(folder_name, file_name, content):
    create_folder_if_not_exists(folder_name)
    with open(os.path.join(folder_name, file_name), "w", encoding="utf-8") as text_file:
        text_file.write(content)


def download_image(url, folder_name, file_name):
    create_folder_if_not_exists(folder_name)
    response = requests.get(url)
    with open(os.path.join(folder_name, file_name), "wb") as img_file:
        img_file.write(response.content)


def calculate_green_percentage(image_path):
    image = Image.open(image_path).convert('RGB') # forza l'rgb a prescindere
    image_data = np.array(image)
    
    green_pixel_count = 0
    total_pixel_count = image_data.shape[0] * image_data.shape[1]
    
    for row in image_data:
        for pixel in row:
            red, green, blue = pixel[:3]
            if green > red and green > blue:
                green_pixel_count += 1
    
    return (green_pixel_count / total_pixel_count) * 100


def search_places(client, lat, lng, radius, keyword, num_results):
    result = []
    query_params = {
        "location": f"{lat},{lng}",
        "radius": radius * 1000,
        "keyword": keyword,
        "type": "establishment",
    }
    
    response = client.places_nearby(**query_params)
    
    for place in response["results"]:
        result.append(place)
        if len(result) >= num_results:
            break
    
    while "next_page_token" in response and len(result) < num_results:
        time.sleep(2) # debug
        query_params["page_token"] = response["next_page_token"]
        response = client.places_nearby(**query_params)
        for place in response["results"]:
            result.append(place)
            if len(result) >= num_results:
                break
    
    return result[:num_results]


def get_place_details(client, place_id):
    fields = ["name", "formatted_address", "formatted_phone_number", "website", "reviews", "rating"]
    response = client.place(place_id, fields=fields)
    return response["result"]


def find_keyword_in_reviews(reviews, keyword):
    count = 0
    if reviews is not None:
        for review in reviews:
            if keyword.lower() in review["text"].lower() or keyword.lower() in review["author_name"].lower():
                count += 1
    return count


def download_satellite_image(client, lat, lng, zoom_level, folder_name, file_name):
    scale = 2
    size = "640x640"
    map_type = "satellite"
    url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lng}&zoom={zoom_level}&scale={scale}&size={size}&maptype={map_type}&key={client.key}"
    download_image(url, folder_name, file_name)


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # raggio della terra in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) * math.sin(dlon / 2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def destination_point(lat, lon, distance, angle):
    R = 6371  # raggio della terra in km
    d = distance / R
    
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(math.radians(angle)))
    lon2 = lon1 + math.atan2(math.sin(math.radians(angle)) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2))
    
    return math.degrees(lat2), math.degrees(lon2)

def calculate_circle_centers(outer_radius, small_radius, center_latitude, center_longitude):
    circle_centers = []
    angle = 60
    
    # da metri a km
    outer_radius /= 1000
    small_radius /= 1000
    
    # calcola il raggio del cerchio circoscritto all'esagono
    circumscribed_radius = small_radius / math.cos(math.radians(angle / 2))
    
    y_offset = math.sqrt(3) * circumscribed_radius
    x_offset = 2 * circumscribed_radius * math.cos(math.radians(angle))
    
    max_grid_width = int(2 * math.ceil(outer_radius / x_offset))
    max_grid_height = int(2 * math.ceil(outer_radius / y_offset))
    
    for i in range(-max_grid_height, max_grid_height + 1):
        for j in range(-max_grid_width, max_grid_width + 1):
            lat_shift = (i * y_offset) + (y_offset / 2 * (j % 2))
            lon_shift = j * x_offset
            
            lat_new, lon_new = destination_point(center_latitude, center_longitude, lat_shift, 0)
            lat_new, lon_new = destination_point(lat_new, lon_new, lon_shift, 90)
            
            # distanze su una sfera
            if haversine_distance(center_latitude, center_longitude, lat_new, lon_new) <= outer_radius:
                circle_centers.append((lat_new, lon_new))
    
    return circle_centers


def remove_duplicates(places):
    seen_ids = set()
    unique_places = []
    
    for place in places:
        place_id = place["place_id"]
        if place_id not in seen_ids:
            seen_ids.add(place_id)
            unique_places.append(place)
    
    return unique_places

# debug
def clean_folder_name(folder_name):
    # sostituisci i caratteri non validi su winzozz con un trattino '-'
    cleaned_name = re.sub(r'[\\/:*?"<>|]', "-", folder_name)
    return cleaned_name

# template
def generate_html_report(places_data, output_file):
    html_template = Template("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Report</title>
        <style>
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 15px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            th {
                background-color: #f2f2f2;
            }
            tr:hover {background-color: #f5f5f5;}
            .select-place {
                display: none;
            }
            .image-label {
                cursor: pointer;
            }
            .image-label img {
                border: 3px solid transparent;
            }
            .select-place:checked + .image-label img {
                border-color: #007bff;
            }
        </style>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.17.0/xlsx.full.min.js"></script>
    </head>
    <body>
        <h1>Report</h1>
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Address</th>
                    <th>Phone</th>
                    <th>Rating</th>
                    <th>Green Percentage</th>
                    <th>Website</th>
                    <th>Annotations</th>
                    <th>Select Image</th>
                </tr>
            </thead>
            <tbody>
                {% for place_data in places_data %}
                <tr>
                    <td>{{ place_data["name"] }}</td>
                    <td>{{ place_data["address"] }}</td>
                    <td>{{ place_data["phone"] }}</td>
                    <td>{{ place_data["rating"] }}</td>
                    <td>{{ place_data["green_percentage"] }}%</td>
                    <td><a href="{{ place_data["website"] }}" target="_blank">link</a></td>
                    <td><input type="text" class="annotations" data-index="{{ loop.index0 }}" value="{{ place_data["annotations"] | default('') }}"></td>
                    <td>
                        <input type="checkbox" class="select-place" data-index="{{ loop.index0 }}" id="select-place-{{ loop.index0 }}">
                        <label class="image-label" for="select-place-{{ loop.index0 }}"><img src="{{ place_data["image_path"] }}" width="300"></label>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <button id="save-to-excel">Save to Excel</button>
        <script>
            const placesData = {{ places_data|tojson }};
            
            function s2ab(s) {
                const buf = new ArrayBuffer(s.length);
                const view = new Uint8Array(buf);
                for (let i = 0; i < s.length; i++) view[i] = s.charCodeAt(i) & 0xFF;
                return buf;
            }
            
            document.getElementById("save-to-excel").addEventListener("click", function() {
                const selectedIndices = Array.from(document.querySelectorAll(".select-place:checked")).map(input => parseInt(input.dataset.index));
                const selectedData = selectedIndices.map(index => {
                    const annotations = document.querySelector(`.annotations[data-index="${index}"]`).value;
                    return { ...placesData[index], annotations };
                });
                
                const wb = XLSX.utils.book_new();
                const ws = XLSX.utils.json_to_sheet(selectedData);
                XLSX.utils.book_append_sheet(wb, ws, "Rapporto");
                const wbout = XLSX.write(wb, { bookType: 'xlsx', bookSST: true, type: 'binary' });
                const blob = new Blob([s2ab(wbout)], { type: 'application/octet-stream' });

                // Create a download link and click it to download the Excel file
                const downloadLink = document.createElement('a');
                downloadLink.href = window.URL.createObjectURL(blob);
                downloadLink.download = 'rapporto.xlsx';
                downloadLink.click();
            });
        </script>
    </body>
    </html>
    """)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_template.render(places_data=places_data))


##############
#    MAIN    #
##############

# autenticazione
client = googlemaps.Client(key=API_KEY)

# input
num_results = 5000 # nuovo limite per il traffico giornaliero
center_latitude, center_longitude = input("Lat, Lng: ").split(", ")
center_latitude = float(center_latitude)
center_longitude = float(center_longitude)
outer_radius = float(input("Raggio complessivo di ricerca (km): ")) * 1000
small_radius = float(input("Raggio dei cerchi piccoli (km): ")) * 1000
keyword = input("Tipo attività: ")
review_keyword = input("Keyword recensioni: ")
meters_per_centimeter = float(input("Metri corrispondenti a 1 cm sulla foto satellitare: ")) 

# calcolo del zoom_level in base alla necessitù
print("\nCalcolo del livello di zoom...")
zoom_level = int(np.log2(156543.03392 * np.cos(center_latitude * pi / 180) / (meters_per_centimeter / 100)))

# calcola i centri dei cerchi
circle_centers_lat_lng = calculate_circle_centers(outer_radius, small_radius, center_latitude, center_longitude)

# ricerca dei luoghi
print("\nRicerca luoghi...")
all_places = []
i = 1
for lat, lng in circle_centers_lat_lng:
    analysis_done = False
    while not analysis_done:
        try:
            # printo la progressione dell'analisi
            messaggio = (f"  {i} lotti")
            sys.stdout.write("\r" + messaggio)
            sys.stdout.flush()
            
            places = search_places(client, lat, lng, small_radius / 1000, keyword, num_results)
            all_places.extend(places)
            i = i + 1
            analysis_done = True
        except Exception as e:
            print(f"\nErrore durante l'analisi del lotto {i}.\n{e}\nRiprovo...")
            time.sleep(5)  # attendi 5 secondi prima di riprovare

# rimuovi i duplicati
n = len(all_places)
print(f"\n\nControllo duplicati su {n} attività trovate...")
all_places = remove_duplicates(all_places)

# analizza i luoghi trovati
print("\nAnalisi attività...")
places_data = []
i = 1
n = len(all_places) # numero di attività senza duplicati
for place in all_places:
    analysis_done = False
    while not analysis_done:
        try:
            # printo la progressione dell'analisi
            messaggio = (f"  {i} di {n}")
            sys.stdout.write("\r" + messaggio)
            sys.stdout.flush()
            
            time.sleep(2)  # debug
            
            place_data = {}
            place_id = place["place_id"]
            place_details = get_place_details(client, place_id)
            
            place_data["name"] = place_details["name"]
            place_data["address"] = place_details["formatted_address"]
            place_data["phone"] = place_details.get("formatted_phone_number", "")
            place_data["rating"] = place_details.get("rating", "N/A")
            place_data["website"] = place_details.get("website", "N/A")
            
            lat = place["geometry"]["location"]["lat"]
            lng = place["geometry"]["location"]["lng"]
            #folder_name = f"{place_data['name'].replace(' ', '_')}_{place_id}" # WinError123
            cleaned_place_name = clean_folder_name(place_data['name']) # debug
            folder_name = f"{cleaned_place_name.replace(' ', '_')}_{place_id}" # debug
            image_path = os.path.join(folder_name, "satellite_image.png")
            
            download_satellite_image(client, lat, lng, zoom_level, folder_name, "satellite_image.png")
            place_data["green_percentage"] = round(calculate_green_percentage(image_path), 2)
            place_data["keyword_count"] = find_keyword_in_reviews(place_details.get("reviews"), review_keyword)
            place_data["image_path"] = image_path
            
            places_data.append(place_data)
            i = i + 1
            analysis_done = True
        except Exception as e:
            print(f"\nErrore durante l'analisi del luogo {i}.\n{e}\nRiprovo...")
            time.sleep(5)  # attendi 5 secondi prima di riprovare

# ordinamento dei risultati per percentuale di verde e recensioni trovate
def compare(a, b):
    if a["green_percentage"] > b["green_percentage"]:
        return -1
    elif a["green_percentage"] < b["green_percentage"]:
        return 1
    else:
        return b["keyword_count"] - a["keyword_count"]

places_data.sort(key=cmp_to_key(compare))

# rapporto sui risultati
print("\n\nCreazione report...")
output_file = "report.html"
generate_html_report(places_data, output_file)

print("\nFine. Consultare il file:", output_file)

