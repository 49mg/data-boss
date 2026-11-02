"""Download the UCI Bank Marketing data used in this case study (CC BY 4.0).

Run it from this folder:  python download.py   ->  bank-full.csv
Source: Moro, S., Rita, P. and Cortez, P. (2014). Bank Marketing. UCI Machine Learning Repository.
https://doi.org/10.24432/C5K306
"""

import io
import urllib.request
import zipfile

URL = "https://archive.ics.uci.edu/static/public/222/bank+marketing.zip"

with urllib.request.urlopen(URL, timeout=60) as response:
    outer = zipfile.ZipFile(io.BytesIO(response.read()))
inner = zipfile.ZipFile(io.BytesIO(outer.read("bank.zip")))
with open("bank-full.csv", "wb") as f:
    f.write(inner.read("bank-full.csv"))
print("Saved bank-full.csv")
