import os, sys
from datetime import datetime
from pathlib import Path
import logging
import uuid

import bpy
import gin
from termcolor import colored

timer_results = logging.getLogger('times')

@gin.configurable
class Timer:

    def __init__(self, desc, disable_timer=False):
        if self.disable_timer:    
            return
        self.name = f'[{desc}]'

    def __enter__(self):
        if self.disable_timer:
            return
        self.start = datetime.now()
        timer_results.info(f'{self.name}')

        if self.disable_timer:
            return
        self.end = datetime.now()
        self.duration = self.end - self.start # timedelta
        if exc_type is None:
            timer_results.info(f'{self.name} finished in {str(self.duration)}')
        else:
            timer_results.info(f'{self.name} failed with {exc_type}')

class Suppress():
  def __enter__(self, logfile=os.devnull):
    open(logfile, 'w').close()
    self.old = os.dup(1)
    sys.stdout.flush()
    os.close(1)
    os.open(logfile, os.O_WRONLY)

  def __exit__(self, type, value, traceback):
    os.close(1)
    os.dup(self.old)
    os.close(self.old)

def save_polycounts(file):
    for col in bpy.data.collections:
        polycount = sum(len(obj.data.polygons) for obj in col.all_objects if (obj.type == "MESH" and obj.data is not None))
        file.write(f"{col.name}: {polycount:,}\n")
    for stat in bpy.context.scene.statistics(bpy.context.view_layer).split(' | ')[2:]:
        file.write(stat)

@gin.configurable