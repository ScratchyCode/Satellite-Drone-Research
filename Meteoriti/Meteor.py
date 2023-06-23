# Coded by Pietro Squilla
# Creazione di un report sui meteoriti presenti in sequenze di foto aeree geolocalizzate
import cv2
import numpy as np
import exifread
import os
import time
from jinja2 import Environment, FileSystemLoader, BaseLoader

SOGLIA_NERO = 40 # tra 0 e 255, test con 30
MIN_AREA = 400 # pixel contigui, test con 500

def get_exif_data(image_path):
    with open(image_path, 'rb') as f:
        exif_tags = exifread.process_file(f)
    return exif_tags

def get_gps_info(exif_data):
    try:
        gps_latitude = exif_data['GPS GPSLatitude']
        gps_longitude = exif_data['GPS GPSLongitude']
    except KeyError:
        print(f"No GPS data for image {image_path}")
        gps_latitude, gps_longitude = None, None
    return str(gps_latitude.values), str(gps_longitude.values)

def detect_and_crop_black(image_path, threshold=SOGLIA_NERO, min_area=MIN_AREA):
    # carica immagine
    image = cv2.imread(image_path)

    # converti in scala di grigi
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # applicazione della soglia
    _, thresholded = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

    # contorni
    contours, _ = cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # filtra i contorni con l'area minima
    filtered_contours = [cnt for cnt in contours if cv2.contourArea(cnt) > min_area]

    # percentuale di nero
    black_percentage = np.sum(thresholded == 255) / float(thresholded.size)

    # crop
    crop_paths = []
    for i, cnt in enumerate(filtered_contours):
        x, y, w, h = cv2.boundingRect(cnt)
        crop = image[y:y+h, x:x+w]
        filename = os.path.basename(image_path)
        crop_path = os.path.join("crop", f"{os.path.splitext(filename)[0]}_crop{i}.jpg")
        cv2.imwrite(crop_path, crop)
        crop_paths.append(crop_path)
    
    return black_percentage, crop_paths

# template del report
template_string = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
</head>
<body>
    <h1>{{ title }}</h1>
    {% for image_file, info in info_dict.items() %}
        <h2>Immagine: {{ image_file }}</h2>
        <h3>Coordinate GPS: {{ info['gps'] }}</h3>
        <h3>Percentuale di nero: {{ info['black_percentage']|round(1) }}%</h3>
        <img src="{{ os.path.join(image_dir, image_file) }}" style="max-width: 800px"><br>
        <h3>Crop delle aree nere:</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px;">
        {% for crop_path in info['crop_paths'] %}
            <img src="{{ crop_path }}" style="width: 100%">
        {% endfor %}
        </div>
    {% endfor %}
</body>
</html>
"""

########
# MAIN #
########
image_dir = input("Directory immagini: ")

env = Environment(loader=BaseLoader)

# creazione template dalla stringa
template = env.from_string(template_string)

info_dict = {}
os.makedirs("crop", exist_ok=True)
env = Environment(loader=FileSystemLoader('.'))
#template = env.get_template('template.html') # commentato per fare a meno del file template
template = env.from_string(template_string)

# carica tutte le immagini dalla dir
for image_file in os.listdir(image_dir):
    image_path = os.path.join(image_dir, image_file)
    black_percentage, crop_paths = detect_and_crop_black(image_path)
    if black_percentage > 0:
        try:
            exif_data = get_exif_data(image_path)
            gps_info = get_gps_info(exif_data)
        except Exception as e:
            print(f"Failed to get exif data for image {image_path}: {e}")
            gps_info = ("N/A", "N/A")
        info_dict[image_file] = {"gps": gps_info, "black_percentage": black_percentage, "crop_paths": crop_paths}

# report
template_vars = {"title": "Report corpi scuri", "info_dict": info_dict, "image_dir": image_dir, "os": os}
html_out = template.render(template_vars)

with open("report.html", "w") as f:
    f.write(html_out)
