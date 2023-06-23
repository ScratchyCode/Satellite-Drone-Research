# Coded by Pietro Squilla

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

#############
#    KEY    #
#############
API_KEY = "XXX" # <---------------------------------------------------------------------

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
            </style>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.17.0/xlsx.full.min.js"></script>
        </head>
        <body>
            <h1>Report</h1>
            <table>
                <thead>
                    <tr>
                        <th>Select</th>
                        <th>Name</th>
                        <th>Address</th>
                        <th>Phone</th>
                        <th>Rating</th>
                        <th>Green Percentage</th>
                        <th>Keyword Count</th>
                        <th>Image</th>
                    </tr>
                </thead>
                <tbody>
                    {% for place_data in places_data %}
                    <tr>
                        <td><input type="checkbox" class="select-place" data-index="{{ loop.index0 }}"></td>
                        <td>{{ place_data["name"] }}</td>
                        <td>{{ place_data["address"] }}</td>
                        <td>{{ place_data["phone"] }}</td>
                        <td>{{ place_data["rating"] }}</td>
                        <td>{{ place_data["green_percentage"] }}%</td>
                        <td>{{ place_data["keyword_count"] }}</td>
                        <td><img src="{{ place_data["image_path"] }}" width="300"></td>
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
                    const selectedData = selectedIndices.map(index => placesData[index]);
                    
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

# input (parametri di esempio)
num_results = 1000
latitude, longitude = input("Lat, Lng: ").split(", ")
latitude = float(latitude)
longitude = float(longitude)
radius = float(input("Raggio ricerca (km): "))
keyword = input("Tipo attività: ")
review_keyword = input("Keyword recensioni: ")
meters_per_centimeter = float(input("Metri corrispondenti a 1 cm sulla foto satellitare: ")) 

# calcolo del zoom_level in base alla necessitù
print("Calcolo del livello di zoom...")
zoom_level = int(np.log2(156543.03392 * np.cos(latitude * pi / 180) / (meters_per_centimeter / 100)))

# ricerca dei luoghi
print("Ricerca luoghi...")
places = search_places(client, latitude, longitude, radius, keyword, num_results)

# analizza i luoghi trovati
print("Analisi luoghi...")
places_data = []
i = 1
n = len(places)
for place in places:
    # printo la progressione dell'analisi
    messaggio = (f"  {i} di {n}")
    sys.stdout.write("\r" + messaggio)
    sys.stdout.flush()
    i = i + 1
    
    time.sleep(2) # debug
    
    place_data = {}
    place_id = place["place_id"]
    place_details = get_place_details(client, place_id)
    
    place_data["name"] = place_details["name"]
    place_data["address"] = place_details["formatted_address"]
    place_data["phone"] = place_details.get("formatted_phone_number", "")
    place_data["rating"] = place_details.get("rating", "N/A")
    
    lat = place["geometry"]["location"]["lat"]
    lng = place["geometry"]["location"]["lng"]
    folder_name = f"{place_data['name'].replace(' ', '_')}_{place_id}"
    image_path = os.path.join(folder_name, "satellite_image.png")
    
    download_satellite_image(client, lat, lng, zoom_level, folder_name, "satellite_image.png")
    place_data["green_percentage"] = round(calculate_green_percentage(image_path), 2)
    place_data["keyword_count"] = find_keyword_in_reviews(place_details.get("reviews"), review_keyword)
    place_data["image_path"] = image_path
    
    places_data.append(place_data)

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
print("\nCreazione report...")
output_file = "report.html"
generate_html_report(places_data, output_file)

print("\nFine\nConsultare il file:", output_file)
