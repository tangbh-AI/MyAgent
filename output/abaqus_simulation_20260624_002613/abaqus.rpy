# -*- coding: mbcs -*-
#
# Abaqus/CAE Release 2024 replay file
# Internal Version: 2023_09_21-20.55.25 RELr426 190762
# Run by tbh on Wed Jun 24 00:26:14 2026
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
#* TypeError:  关键字错误: acousticRange
#* File "abaqus_simulation.py", line 69, in <module>
#*     model.FrequencyStep(
