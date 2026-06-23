"""ODB 调试脚本 — 在 Abaqus Python 环境中运行"""
from odbAccess import openOdb

odb_path = r'D:/MyAgent/output/abaqus_simulation_20260623_211159/SimJob.odb'
odb = openOdb(odb_path)
print(f'Steps: {list(odb.steps.keys())}')
step = list(odb.steps.values())[-1]
print(f'Last step: {step.name}')
print(f'Frames: {len(step.frames)}')
frame = step.frames[-1]
print(f'Last frame: {frame.frameValue}')
print(f'Field outputs: {list(frame.fieldOutputs.keys())}')

if 'S' in frame.fieldOutputs:
    sf = frame.fieldOutputs['S']
    print(f'Stress values count: {len(sf.values)}')
    mises_vals = []
    for v in sf.values:
        try:
            mises_vals.append(v.mises)
        except Exception as e:
            pass
    if mises_vals:
        print(f'mises range: {min(mises_vals):.2f} ~ {max(mises_vals):.2f}')
        print(f'First 5 mises: {mises_vals[:5]}')
    else:
        print(f'No mises values found. Checking first value...')
        v0 = sf.values[0]
        print(f'v0.data type: {type(v0.data)}')
        print(f'v0.data: {v0.data}')
        print(f'v0 attrs: {[a for a in dir(v0) if not a.startswith("_")]}')

if 'U' in frame.fieldOutputs:
    uf = frame.fieldOutputs['U']
    print(f'Displacement values count: {len(uf.values)}')
    mag_vals = []
    for v in uf.values:
        try:
            mag_vals.append(v.magnitude)
        except:
            pass
    if mag_vals:
        print(f'magnitude range: {min(mag_vals):.4f} ~ {max(mag_vals):.4f}')

odb.close()
print('Done.')
