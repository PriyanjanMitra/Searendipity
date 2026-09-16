import os
import gzip
import requests
import sqlite3
import xml.etree.ElementTree as ET
from .filters import normalizeNationName

def download_nation_data_dump(nation: str, target_xml: str = "nations.xml") -> None:
    url = 'https://www.nationstates.net/pages/nations.xml.gz'
    headers = {
        'Accept': 'application/gzip',
        'User-Agent': f"Searendipity (report generator) used by {nation}"
    }

    gz_path = "nations.xml.gz"
    print(f"[DataDump] Downloading daily data dump from {url}...")

    with requests.get(url, headers=headers, stream=True) as r:
        r.raise_for_status()
        with open(gz_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)

    print(f"[DataDump] Extracting {gz_path} to {target_xml}...")
    with gzip.open(gz_path, 'rb') as f_in:
        with open(target_xml, 'wb') as f_out:
            while chunk := f_in.read(65536):
                f_out.write(chunk)

    if os.path.exists(gz_path):
        os.remove(gz_path)
    print(f"[DataDump] Decompression complete.")

def parse_and_insert_nation_data(xml_file: str, cursor: sqlite3.Cursor, batch_size: int = 10000) -> int:
    """Stream-parse nations.xml using iterparse to keep memory footprint minimal."""
    print(f"[DataDump] Stream-parsing nation XML dump...")
    count = 0
    batch = []

    # iterparse yields (event, elem)
    context = ET.iterparse(xml_file, events=("end",))

    for event, elem in context:
        if elem.tag == "NATION":
            name_el = elem.find("NAME")
            region_el = elem.find("REGION")
            unstatus_el = elem.find("UNSTATUS")
            lastlogin_el = elem.find("LASTLOGIN")

            canon_name = name_el.text if name_el is not None and name_el.text else ""
            api_name = normalizeNationName(canon_name)
            region = normalizeNationName(region_el.text) if region_el is not None and region_el.text else ""
            wa = 1 if unstatus_el is not None and unstatus_el.text == "WA Member" else 0
            lastlogin = int(lastlogin_el.text) if lastlogin_el is not None and lastlogin_el.text and lastlogin_el.text.isdigit() else 0

            batch.append((canon_name, api_name, region, wa, lastlogin))
            count += 1

            if len(batch) >= batch_size:
                cursor.executemany("INSERT INTO nations VALUES(?, ?, ?, ?, ?)", batch)
                batch.clear()

            # Clear element from memory
            elem.clear()

    if batch:
        cursor.executemany("INSERT INTO nations VALUES(?, ?, ?, ?, ?)", batch)
        batch.clear()

    print(f"[DataDump] Processed and indexed {count:,} nations.")
    return count

def generate_database(ua: str, regenerate: bool = False, db_path: str = "nations.db") -> sqlite3.Connection:
    """Generate or open the nations SQLite database, populating it if needed."""
    db_exists = os.path.exists(db_path)

    if regenerate and db_exists:
        os.remove(db_path)
        db_exists = False

    con = sqlite3.connect(db_path)
    cursor = con.cursor()

    if not db_exists:
        cursor.execute("DROP TABLE IF EXISTS nations;")
        cursor.execute("""
            CREATE TABLE nations (
                canon_name TEXT,
                api_name TEXT,
                region TEXT,
                wa INTEGER,
                lastlogin INTEGER
            )
        """)
        # Crucial: indexes turn 10-minute linear table scans into sub-second lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nations_api ON nations(api_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nations_region ON nations(region);")
        con.commit()

        xml_file = "nations.xml"
        if not os.path.exists(xml_file) or regenerate:
            download_nation_data_dump(ua, xml_file)

        parse_and_insert_nation_data(xml_file, cursor)
        con.commit()

    cursor.close()
    return con
