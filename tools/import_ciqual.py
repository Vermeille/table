"""Extract the four macros and French food labels from the official Ciqual 2025 XLSX."""
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NAMESPACE = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
PUBLISHED_MD5 = '0d9758ce23f3f13dd63a005bc1bb4f2c'
COLUMNS = {'K': 'kcal', 'P': 'protein_g', 'Q': 'carbs_g', 'R': 'fat_g'}


def workbook(path):
    with zipfile.ZipFile(path) as archive:
        strings = [''.join(node.itertext()) for node in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        with archive.open('xl/worksheets/sheet1.xml') as sheet:
            for _, row in ET.iterparse(sheet, events=('end',)):
                if row.tag != NAMESPACE + 'row':
                    continue
                cells = {}
                for cell in row:
                    value = cell.find(NAMESPACE + 'v')
                    if value is not None:
                        column = re.match(r'[A-Z]+', cell.attrib['r']).group()
                        cells[column] = strings[int(value.text)] if cell.get('t') == 's' else value.text
                yield cells
                row.clear()


def number(value):
    value = value.strip().replace(',', '.')
    if value.casefold() == 'traces':
        return 'trace'
    try:
        return [0, float(value[1:].strip())] if value.startswith('<') else float(value)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if hashlib.md5(args.input.read_bytes(), usedforsecurity=False).hexdigest() != PUBLISHED_MD5:
        raise SystemExit('Input does not match the published Ciqual 2025 workbook.')
    rows = workbook(args.input)
    header = next(rows)
    assert header['G'] == 'alim_code' and header['H'] == 'alim_nom_fr'
    assert '1169' in header['K'] and 'kcal' in header['K']
    assert '6.25' in header['P'] and 'Glucides' in header['Q'] and 'Lipides' in header['R']
    foods = []
    for row in rows:
        if not row.get('G', '').isdigit():
            continue
        foods.append([row['G'], ' '.join(row['H'].split()), ' '.join(row.get('E', '').split())] +
                     [number(row.get(column, '')) for column in COLUMNS])
    assert len(foods) == len({food[0] for food in foods}) == 3484
    foods.sort(key=lambda food: int(food[0]))
    args.output.write_text('[\n' + ',\n'.join(json.dumps(food, ensure_ascii=False, separators=(',', ':'))
                                               for food in foods) + '\n]\n', encoding='utf-8')


if __name__ == '__main__':
    main()
