import requests
from dotenv import load_dotenv
import os
from time import perf_counter

load_dotenv()
API_KEY = os.getenv("OCR_KEY")

def ocr_space_file(filename, language='eng'):
    payload = {
        'apikey': API_KEY,
        'language': language,
        'isOverlayRequired': False
    }
    with open(filename, 'rb') as f:
        r = requests.post(
            'https://api.ocr.space/parse/image',
            files={filename: f},
            data=payload
        )
    result = r.json()
    return result['ParsedResults'][0]['ParsedText']

# 'helloworld' works for quick testing; register on ocr.space for a free personal key
s = perf_counter()
text = ocr_space_file('test.png')
e = perf_counter()
print(text)
print(f"Time Took: {e-s}")