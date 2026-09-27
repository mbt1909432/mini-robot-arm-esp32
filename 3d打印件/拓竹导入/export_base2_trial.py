from pathlib import Path
import json
import export_3mf as converter

SOURCE_DIR = converter.ROOT / '\u5706\u76d8\u9002\u914d\u68c0\u67e5'
results = []
for stem in ['base-2_MG90S-clearance-D22-depth6.5_trial', 'base-2_MG90S-clearance_fit-test']:
    obj = converter.read_stl(SOURCE_DIR / (stem + '.stl'))
    if stem.endswith('fit-test'):
        # Flip the coupon so its flat upper cut face rests on the bed, recess up.
        points = [(x,-y,-z) for x,y,z in obj['vertices']]
        limits = converter.bounds(points)
        obj['vertices'] = [tuple(p[i]-limits[i][0] for i in range(3)) for p in points]
        obj['rotation'] = 'Fit test only: underside recess faces upward'
        assert abs(converter.volume(obj['vertices'],obj['triangles'])-obj['volume_mm3']) < 1e-5
    results.append(converter.write_3mf(stem+'.3mf', [obj]))
(converter.OUT / 'base-2_trial-3mf-validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'file':r['file'],'size_mm':r['objects'][0]['size_mm']} for r in results],indent=2))
