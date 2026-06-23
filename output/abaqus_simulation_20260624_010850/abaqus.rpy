# -*- coding: mbcs -*-
#
# Abaqus/CAE Release 2024 replay file
# Internal Version: 2023_09_21-20.55.25 RELr426 190762
# Run by tbh on Wed Jun 24 01:08:50 2026
#

# from driverUtils import executeOnCaeGraphicsStartup
# executeOnCaeGraphicsStartup()
#: Executing "onCaeGraphicsStartup()" in the site directory ...
from abaqus import *
from abaqusConstants import *
session.Viewport(name='Viewport: 1', origin=(1.00762, 1.0075), width=148.321, 
    height=99.9438)
session.viewports['Viewport: 1'].makeCurrent()
from driverUtils import executeOnCaeStartup
executeOnCaeStartup()
execfile('abaqus_simulation.py', __main__.__dict__)
#: 模型 "Model-1" 已创建.
#: 模型: D:/MyAgent/output/abaqus_simulation_20260624_010850/SimJob.odb
#: 装配件个数:         1
#: 装配件实例个数: 0
#: 部件实例的个数:     1
#: 网格数:             1
#: 单元集合数:       1
#: 结点集合数:          1
#: 分析步的个数:              1
#: [MyAgent] 已打开 ODB: D:\MyAgent\output\abaqus_simulation_20260624_010850\SimJob.odb
#: [MyAgent] 提取数值结果: {'max_stress_mises': 1352.2, 'min_stress_mises': 6.37, 'max_displacement': 10.7409, 'max_principal_stress': 1400.09, 'min_principal_stress': -1400.09}
#: [MyAgent] 已保存: stress_contour.png
#: [MyAgent] 已保存: displacement_contour.png
#: [MyAgent] 已保存 paths.json (0 采样点, 1 条曲线)
#: [MyAgent] 已保存: results.json
print('RT script done')
#: RT script done
