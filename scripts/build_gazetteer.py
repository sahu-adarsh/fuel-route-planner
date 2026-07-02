"""
Builds data/us_cities_gazetteer.csv from a GeoNames per-country export.

This is the offline city+state -> coordinates reference table used to
geocode fuel stations that only have City/State (decisions ADR-003). It
is a one-time, reproducible transform of third-party data, not something
the ingestion command re-downloads on every run.

The "cities500" export (population > 500 only) was tried first and left
~9% of stations unresolved - mostly small unincorporated places below
that population floor. Switching to the full per-country US export (all
populated places, no population floor) dropped that to ~1%.

Source: https://download.geonames.org/export/dump/US.zip
License: GeoNames data is CC BY 4.0 (https://www.geonames.org/export/)

Usage:
    curl -o /tmp/US.zip http://download.geonames.org/export/dump/US.zip
    unzip /tmp/US.zip -d /tmp
    python3 scripts/build_gazetteer.py /tmp/US.txt data/us_cities_gazetteer.csv
"""
import csv
import sys

GEONAMES_COLUMNS = [
    "geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude",
    "feature_class", "feature_code", "country_code", "cc2", "admin1_code",
    "admin2_code", "admin3_code", "admin4_code", "population", "elevation",
    "dem", "timezone", "modification_date",
]


def build(input_path, output_path):
    best = {}  # (name_upper, state) -> (lat, lng, population)
    with open(input_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            record = dict(zip(GEONAMES_COLUMNS, row))
            if record["country_code"] != "US" or record["feature_class"] != "P":
                continue

            state = record["admin1_code"].strip().upper()
            name = record["asciiname"].strip().upper()
            if not state or not name:
                continue

            population = int(record["population"] or 0)
            key = (name, state)
            existing = best.get(key)
            if existing is None or population > existing[2]:
                best[key] = (float(record["latitude"]), float(record["longitude"]), population)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["city", "state", "latitude", "longitude", "population"])
        for (name, state), (lat, lng, population) in sorted(best.items()):
            writer.writerow([name, state, lat, lng, population])

    print(f"Wrote {len(best)} US city/state entries to {output_path}")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
