"""Create unsliced, millimeter-unit 3MF models from the original binary STLs."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
import struct
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
MODIFIED = ROOT / '\u8235\u76d8\u69fd\u8c03\u6574'
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('', NS)


def xml_bytes(root):
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def bounds(points):
    return [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)]


def volume(vertices, triangles):
    total = 0
    for triangle in triangles:
        a, b, c = [vertices[i] for i in triangle]
        total += (a[0]*(b[1]*c[2]-b[2]*c[1]) + a[1]*(b[2]*c[0]-b[0]*c[2]) + a[2]*(b[0]*c[1]-b[1]*c[0]))/6
    return total


def read_stl(path, rotate_side_pocket=False):
    raw = path.read_bytes()
    count = struct.unpack_from('<I', raw, 80)[0]
    assert len(raw) == 84+50*count, 'Expected binary STL'
    vertices, triangles, index = [], [], {}
    for i in range(count):
        record = struct.unpack_from('<12fH', raw, 84+50*i)
        triangle = []
        for j in range(3):
            point = tuple(record[3+3*j:6+3*j])
            assert all(math.isfinite(x) for x in point)
            if rotate_side_pocket:
                x, y, z = point
                point = (6-z, y, x+27.5)
            if point not in index:
                index[point] = len(vertices)
                vertices.append(point)
            triangle.append(index[point])
        assert len(set(triangle)) == 3
        triangles.append(tuple(triangle))
    edges = Counter()
    oriented = Counter()
    for a,b,c in triangles:
        for edge in [(a,b), (b,c), (c,a)]:
            edges[tuple(sorted(edge))] += 1
            oriented[edge] += 1
    assert all(n == 2 for n in edges.values()), path
    assert all(oriented[b,a] == n for (a,b),n in oriented.items()), path
    limits = bounds(vertices)
    vertices = [tuple(p[i]-limits[i][0] for i in range(3)) for p in vertices]
    return {
        'name': path.stem, 'source': str(path.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(raw).hexdigest(),
        'vertices': vertices, 'triangles': triangles,
        'size_mm': [hi-lo for lo,hi in limits],
        'volume_mm3': volume(vertices, triangles),
        'rotation': 'Side pocket rotated upward' if rotate_side_pocket else 'Original orientation preserved',
    }


def write_3mf(filename, objects):
    root = ET.Element(f'{{{NS}}}model', {'unit': 'millimeter', '{http://www.w3.org/XML/1998/namespace}lang': 'en-US'})
    ET.SubElement(root, f'{{{NS}}}metadata', {'name': 'Title'}).text = Path(filename).stem
    ET.SubElement(root, f'{{{NS}}}metadata', {'name': 'Description'}).text = 'Unsliced geometry only. Select your printer, nozzle, filament and process in Bambu Studio before slicing.'
    resources = ET.SubElement(root, f'{{{NS}}}resources')
    build = ET.SubElement(root, f'{{{NS}}}build')
    offset_x = 10.0
    for oid,obj in enumerate(objects, 1):
        item = ET.SubElement(resources, f'{{{NS}}}object', {'id': str(oid), 'type': 'model', 'name': obj['name']})
        mesh = ET.SubElement(item, f'{{{NS}}}mesh')
        verts = ET.SubElement(mesh, f'{{{NS}}}vertices')
        for point in obj['vertices']:
            ET.SubElement(verts, f'{{{NS}}}vertex', dict(zip(('x','y','z'), (format(x, '.12g') for x in point))))
        triangles = ET.SubElement(mesh, f'{{{NS}}}triangles')
        for triangle in obj['triangles']:
            ET.SubElement(triangles, f'{{{NS}}}triangle', dict(zip(('v1','v2','v3'), map(str, triangle))))
        ET.SubElement(build, f'{{{NS}}}item', {'objectid': str(oid), 'transform': f'1 0 0 0 1 0 0 0 1 {offset_x:.6f} 10 0'})
        offset_x += obj['size_mm'][0] + 15
    content_types = ET.Element('Types', {'xmlns': CT})
    ET.SubElement(content_types, 'Default', {'Extension': 'rels', 'ContentType': 'application/vnd.openxmlformats-package.relationships+xml'})
    ET.SubElement(content_types, 'Default', {'Extension': 'model', 'ContentType': 'application/vnd.ms-package.3dmanufacturing-3dmodel+xml'})
    relations = ET.Element('Relationships', {'xmlns': REL})
    ET.SubElement(relations, 'Relationship', {'Target': '/3D/3dmodel.model', 'Id': 'rel0', 'Type': 'http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel'})
    destination = OUT / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', xml_bytes(content_types))
        archive.writestr('_rels/.rels', xml_bytes(relations))
        archive.writestr('3D/3dmodel.model', xml_bytes(root))
    # Reopen the packaged XML and compare geometry after decimal serialization.
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        model = ET.fromstring(archive.read('3D/3dmodel.model'))
        assert model.attrib['unit'] == 'millimeter'
        packed = model.findall(f'{{{NS}}}resources/{{{NS}}}object')
        assert len(packed) == len(objects)
        for item,original in zip(packed, objects):
            points = [tuple(float(v.attrib[k]) for k in ('x','y','z')) for v in item.findall(f'{{{NS}}}mesh/{{{NS}}}vertices/{{{NS}}}vertex')]
            faces = [tuple(int(t.attrib[k]) for k in ('v1','v2','v3')) for t in item.findall(f'{{{NS}}}mesh/{{{NS}}}triangles/{{{NS}}}triangle')]
            assert faces == original['triangles']
            assert len(points) == len(original['vertices'])
            assert max(abs(a-b) for p,q in zip(points,original['vertices']) for a,b in zip(p,q)) < 1e-7
            assert abs(volume(points,faces)-original['volume_mm3']) < 1e-5
    return {'file': filename, 'sliced': False, 'unit': 'millimeter', 'objects': [
        {k:v for k,v in obj.items() if k not in {'vertices','triangles'}} | {'vertex_count': len(obj['vertices']), 'triangle_count': len(obj['triangles'])}
        for obj in objects
    ]}


def main():
    original1 = read_stl(ROOT / 'arm-1.stl')
    original2 = read_stl(ROOT / 'arm-2.stl')
    arm1 = read_stl(MODIFIED / 'arm-1_slot-plus-0.4mm.stl')
    arm2 = read_stl(MODIFIED / 'arm-2_slot-plus-0.4mm.stl')
    test1 = read_stl(MODIFIED / 'arm-1_fit-test.stl')
    test2 = read_stl(MODIFIED / 'arm-2_fit-test.stl', rotate_side_pocket=True)
    jobs = [
        ('original-reference/arm-1_original.3mf', [original1]),
        ('original-reference/arm-2_original.3mf', [original2]),
        ('arm-1_modified.3mf', [arm1]),
        ('arm-2_modified.3mf', [arm2]),
        ('arm-1_fit-test.3mf', [test1]),
        ('arm-2_fit-test.3mf', [test2]),
        ('modified-arms_pair.3mf', [arm1, arm2]),
        ('fit-tests_pair.3mf', [test1, test2]),
    ]
    report = [write_3mf(filename, objects) for filename,objects in jobs]
    (OUT / 'conversion-validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps([{'file': r['file'], 'objects': len(r['objects']), 'size_mm': [o['size_mm'] for o in r['objects']]} for r in report], indent=2))


if __name__ == '__main__':
    main()
