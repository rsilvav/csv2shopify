import requests
from io import StringIO

def download_csv(url):
    csv_data = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    io = StringIO(csv_data.text)
    return io
