from contextlib import suppress
import sys
import os
import re
import argparse
import math

from numpy import isin
from . version import VERSION

MOVE_RE = '([XYZEF] *-?\d*.?\d*)'

class GCodeLine():
    def __init__(self, num, line):
        self.num = num
        self.line = line
        self.pre = None
        self.post = None
        
    def IsRetract(self):
        if self.line.startswith('G10 ; retract'):
            return True
            
        return False
            
    def IsUnretract(self):
        if self.line.startswith('G11 ; unretract'):
            return True
            
        return False
        
    def get_lines(self, comments=True):
        res = ''
  
        if(self.pre is not None): res += (self.pre + '\n')
        if comments or ((not comments) and (not self.line.lstrip().startswith(';'))):
            res += (self.line + '\n')
        if(self.post is not None): res += (self.post + '\n')
        return res
        
    def __str__(self):
        return f'{self.num}: {self.line}'

class Move(GCodeLine):
    def __init__(self, num, line, x=None, y=None, z=None, e=None, f=None, t=None):
        super().__init__(num, line)
        self.x = x
        self.y = y
        self.z = z
        self.e = e
        self.f = f
        self.t = t
        self.time = 0.0
        
    def IsRetract(self):
        if self.x is None and self.y is None and self.z is None:
            if (self.e is not None and self.e < 0.0):
                return True
                
        return False
            
    def IsUnretract(self):
        if self.x is None and self.y is None and self.z is None:
            if (self.e is not None and self.e > 0.0):
                return True
                
        return False
        
    def RemoveMove(self):
        if self.line.startswith('G1 '):
            if self.f is not None:
                self.line = f'G1 F{int(self.f)*60}'
            else:
                self.line = ''

    def gen_relative_xyz(self, x, y, z):
        rx = 0.0
        if(self.x is not None):
            if(self.x <= x): rx = x - self.x
            else: rx = self.x - x
        ry = 0.0
        if(self.y is not None):
            if(self.y <= y): ry = y - self.y
            else: ry = self.y - y
        rz = 0.0
        if(self.z is not None):
            if(self.z <= z): rz = z - self.z
            else: rz = self.z - z
        
        return (rx, ry, rz)
        
    def __str__(self):
        return f'{self.num} - X: {self.x}, Y: {self.y}, Z: {self.z}, E: {self.e}, F: {self.f}, T: {self.t}, Time: {self.time}'
        
class ToolChange(GCodeLine):
    def __init__(self, num, line, t):
        super().__init__(num, line)
        self.t = t
        
    def __str__(self):
        return f'{self.num}: T{self.t}'
        
class ToolTemp(GCodeLine):
    def __init__(self, num, line, tool, temp=None, standby=None):
        super().__init__(num, line)
        self.tool = tool
        self.temp = temp
        self.standby = standby

class ToolDef():
    def __init__(self, tool=None, temp=None, standby=None):
        self.tool = tool
        self.temp = temp
        self.standby = standby
        
    def __str__(self):
        return f'G10 P{self.tool} S{self.temp} R{self.standby}'
        
class MoveSim:
    def __init__(self):
        self.mf = re.compile(MOVE_RE)
        self.loc = [0, 0, 0]
        self.feedrate = 3000.0 / 60.0  # RRF default is 3000mm/min but we want mm/s
        self.lines = []
        self.tools = {}
        self.used_tools = set()
        self.auto_density = []
        self.auto_diameter = []
    
    def parse_lines(self, lines):
        count = 0
        lastTool = None
        for l in lines:
            l = l.rstrip('\n\r')
            count += 1
            ul = l.rstrip().upper()
            
            if(ul.startswith('G0 ') or ul.startswith('G1 ')):
                move = Move(count, l, t=lastTool)
                for m in self.mf.findall(ul):
                    try:
                        if(m.startswith('X')):
                            move.x = float(m[1:])
                        elif(m.startswith('Y')):
                            move.y = float(m[1:])
                        elif(m.startswith('Z')):
                            move.z = float(m[1:])
                        elif(m.startswith('E')):
                            move.e = float(m[1:])
                        elif(m.startswith('F')):
                            move.f = float(m[1:]) / 60.0  # always convert to mm/s
                    except ValueError:
                        pass # got non-numeric
                        
                self.lines.append(move)
            elif(ul.startswith('G10 ')):
                sub = ul.split(' ')
                tool = None
                temp = None
                standby = None
                for s in sub:
                    if ';' in s:
                        break
                    elif s.startswith("P"):
                        tool = int(s[1:])
                    elif s.startswith("S"):
                        temp = int(s[1:])
                    elif s.startswith("R"):
                        standby = int(s[1:])
                        
                if tool is not None and (temp is not None or standby is not None):
                    tt = ToolTemp(count, l, tool, temp, standby)
                    self.lines.append(tt)
                else:
                    gcl = GCodeLine(count, l)
                    self.lines.append(gcl)
            elif(ul.startswith('T')):
                tn_str = ''
                for c in ul[1:]:
                    if( c == '-' or c.isnumeric()):
                        tn_str += c
                    else:
                        break  # end of tool num, bail out
                try:
                    tool_num = int(tn_str)
                    tc = ToolChange(count, l, tool_num)
                    lastTool = tool_num
                    self.used_tools.add(tool_num)
                    self.lines.append(tc)
                except:
                    print(f'Invalid T command: {l}')
            else:
                gcl = GCodeLine(count, l)
                self.lines.append(gcl)
                
                if(l.startswith('; filament_density = ')):
                    vals = l.replace('; filament_density = ', '').strip()
                    for v in vals.split(','):
                        try:
                            self.auto_density.append(float(v))
                        except ValueError:
                            raise
                            
                if(l.startswith('; filament_diameter = ')):
                    vals = l.replace('; filament_diameter = ', '').strip()
                    for v in vals.split(','):
                        try:
                            self.auto_diameter.append(float(v))
                        except ValueError:
                            pass
                    
                
        return self.lines
        
    def calc_times(self):
        for l in self.lines:
            if isinstance(l, Move):
                m = l
                if m.f is not None:
                    self.feedrate = m.f
                
                m.f = self.feedrate
                xyz = m.gen_relative_xyz(*self.loc)
                mx = max(xyz)
                if(mx > 0.0):
                    m.time = mx / self.feedrate
                    
                if(m.x is not None): self.loc[0] = m.x
                if(m.y is not None): self.loc[1] = m.y
                if(m.z is not None): self.loc[2] = m.z
                
    def gen_warmups(self, warmup_time=30.0):
        lastTool = -1
        for l in self.lines:
            if isinstance(l, ToolChange):
                if l.t < 0: 
                    lastTool = l.t
                    continue  # tool return. No warmup
                if l.t not in self.tools:
                    raise Exception(f'No temperature parameters defined for T{l.t}')
                curTotal = 0.0
                for ri in reversed(range(l.num-2)):
                    if ri < 0: break
                    rl = self.lines[ri]
                    td = self.tools[l.t]
                    if isinstance(rl, ToolChange):
                        # print(f'Found T{l.t} before time expired: {ri}')
                        if td.temp is not None:
                            rl.post = f'G10 P{l.t} R{td.temp} ;  Warmup T{l.t}'
                        if lastTool >= 0:
                            if lastTool not in self.tools:
                                raise Exception(f'No temperature parameters defined for T{lastTool}')
                            td = self.tools[lastTool]
                            if td.standby is not None:
                                l.pre = f'G10 R{td.standby} P{lastTool} ;  Restore T{lastTool}'
                        break
                    if isinstance(rl, Move):
                        curTotal += rl.time
                        #print(curTotal)
                        if curTotal >= warmup_time:
                            if td.temp is not None:
                                rl.pre = f'G10 R{td.temp} P{l.t} ;  Warmup T{l.t}'
                            if lastTool >= 0:
                                if lastTool not in self.tools:
                                    raise Exception(f'No temperature parameters defined for T{lastTool}')
                                td = self.tools[lastTool]
                                if td.standby is not None:
                                    l.pre = f'G10 R{td.standby} P{lastTool} ;  Restore T{lastTool}'
                            break
                lastTool = l.t
            elif isinstance(l, ToolTemp):
                if not (l.tool in self.tools):
                    td = ToolDef(l.tool, l.temp, l.standby)
                    self.tools[l.tool] = td
                else:
                    if l.temp is not None:
                        self.tools[l.tool].temp = l.temp
                    if l.standby is not None:
                        self.tools[l.tool].standby = l.standby
                        
    def gen_pause(self, tool, mass, length, pausecode, diameter, density, **kwargs):
        total_len = {}
        total_mass = {}
        
        print("Inserting automatic pauses...")
        
        if tool == -1:
            if len(self.used_tools) >= 1:
                tool = list(self.used_tools)[0]
            else:
                self.used_tools = [0]
                tool = 0
        
        if len(self.used_tools) == 0:
            self.used_tools = [tool]
                
        mass_targets = []
        for m in mass.strip().split(','):
            if m:
                try:
                    mass_targets.append(int(m))
                except ValueError:
                    print(f'ERROR: {m} is not a valid mass value!')
                
        mass_target_count = len(mass_targets)
        mass_target_cur = 0
        
        len_targets = []
        for l in length.strip().split(','):
            if l:
                try:
                    len_targets.append(int(l))
                except ValueError:
                    print(f'ERROR: {m} is not a valid length value!')
                
        len_target_count = len(len_targets)
        len_target_cur = 0
            
        
        mass_target = None
        if len(mass_targets):
            mass_target = mass_targets[mass_target_cur]
        
        len_target = None
        if len(len_targets):
            len_target = len_targets[len_target_cur]
        
        g_per_mm3 = {}
        radius_squared = {}

        if mass_target:
            if density is None:
                if len(self.auto_density) >= len(self.used_tools):
                    for i in range(len(self.used_tools)):
                        print(f'Auto-detected {self.auto_density[i]} g/mm^3 density filament for T{self.used_tools[i]}')
                        g_per_mm3[self.used_tools[i]] = self.auto_density[i] * 0.001
                else:
                    for t in self.used_tools:
                        print(f'Using default 1.24 g/mm^3 density for T{t}')
                        g_per_mm3[t] = 1.24 * 0.001 #default to PLA density
            else:
                for t in self.used_tools:
                    print(f'Using default {density} g/mm^3 density for T{t}')
                    g_per_mm3[t] = density * 0.001 #use provided density
                        
            if diameter is None:
                if len(self.auto_diameter) >= len(self.used_tools):
                    for i in range(len(self.used_tools)):
                        print(f'Auto-detected {self.auto_diameter[i]} mm diameter filament for T{self.used_tools[i]}')
                        radius_squared[self.used_tools[i]] = math.pow(self.auto_diameter[i]/2.0, 2)
                else:
                    for t in self.used_tools:
                        print(f'Using default 1.75 mm diameter for T{t}')
                        radius_squared[t] = math.pow(1.75/2.0, 2) #default to diameter
            else:
                for t in self.used_tools:
                    print(f'Using {diameter} mm diameter for T{t}')
                    radius_squared[t] = math.pow(diameter/2.0, 2) #use provided diameter
                    
                    

        for l in self.lines:
            if isinstance(l, Move):
                if l.e is not None:
                    if l.t is None:
                        l.t = 0 #normalize tool index

                    if l.t not in total_len:
                        total_len[l.t] = 0.0
                    if l.t not in total_mass:
                        total_mass[l.t] = 0.0
                        
                    total_len[l.t] += l.e
                    
                    mass = math.pi * radius_squared[l.t] * l.e * g_per_mm3[l.t]
                    total_mass[l.t] += mass
                    
                    if l.t == None or tool == l.t:
                        if mass_target and total_mass[l.t] >= mass_target:
                            print(f"Inserted T{l.t} pause after line {l.num}")
                            l.post = f";RRFPost auto-pause for T{l.t} at {int(total_mass[l.t])} g\n"
                            l.post += pausecode
                            if mass_target_cur < (mass_target_count - 1):
                                mass_target_cur += 1
                                mass_target = mass_targets[mass_target_cur]
                                total_mass[l.t] = 0.0
                            else:
                                mass_target = None
                        if len_target and total_len[l.t] >= len_target:
                            print(f"Inserted T{l.t} pause after line {l.num}")
                            l.post = f";RRFPost auto-pause for T{l.t} at {round(total_len[l.t], 2)} mm\n"
                            l.post += pausecode
                            if len_target_cur < (len_target_count - 1):
                                len_target_cur += 1
                                len_target = len_targets[len_target_cur]
                                total_len[l.t] = 0.0
                            else:
                                len_target = None
                            
        print("Length totals:")
        all_total = 0.0
        for tool, total in total_len.items():
            if tool is None:
                tool = 0
            print(f'  Tool {tool}: {round(total, 1)} mm')
            all_total += total
            
        print(f'  Total:  {round(all_total, 1)} mm')
        
        print("Mass totals:")
        all_total = 0.0
        for tool, total in total_mass.items():
            if tool is None:
                tool = 0
            print(f'  Tool {tool}: {round(total, 2)} g')
            all_total += total
            
        print(f'  Total:  {round(all_total, 2)} g')
        
    def wipe_tower_fix(self):
        out_lines = []
        
        last_retract = (-1, None)
        last_unretract = (-1, None)
        unretract_insert = None
        suppress_moves = False
        for i in range(len(self.lines)):
            l = self.lines[i]
            if unretract_insert is not None:
                if l.line.startswith('; CP TOOLCHANGE WIPE'):
                    # print(unretract_insert.pre)
                    # print(unretract_insert.line)
                    out_lines.append(unretract_insert)
                    unretract_insert = None
                    suppress_moves = False
                elif isinstance(l, Move) and suppress_moves and (l.x or l.y):
                    #while waiting for Tool Change command, suppress moves, but leave feed
                    l.RemoveMove()
            
            out_lines.append(l)
            if l.IsRetract():
                if self.lines[i+1].line.startswith('G1 Z'):
                    l.post = self.lines[i+1].line
                    self.lines[i+1].line = ''
                last_retract = (len(out_lines)-1, l)
                
            if l.IsUnretract():
                if self.lines[i-1].line.startswith('G1 Z'):
                    l.pre = self.lines[i-1].line
                    self.lines[i-1].line = ''
                last_unretract = (len(out_lines)-1, l)

            if suppress_moves and isinstance(l, ToolChange):
                suppress_moves = False
                
            if l.line.startswith('; CP TOOLCHANGE START'):
                ri, rl = last_retract
                ui, ul = last_unretract

                if ui >= ri+2:
                    for j in range(ri+1, ui):
                        if out_lines[j].line and isinstance(out_lines[j], Move):
                            out_lines[j].RemoveMove()
                    unretract_insert = GCodeLine(ul.num, ul.line)
                    unretract_insert.pre = ul.pre
                    out_lines[ui].pre = None
                    out_lines[ui].line = ''
                    
                    suppress_moves = True
                    
                last_retract = (-1, None)
                last_unretract = (-1, None)
                
        self.lines = out_lines
                    
                
            
                

def load_file(path):
    with open(path, 'r') as f:
        return f.readlines()
        
def main():
    parser = argparse.ArgumentParser(
        description=f'RRFPost v{VERSION}: RRF/Duet gcode post-processor'
    )
    
    subs = parser.add_subparsers(dest='cmd')
    
    # parser for preheat
    parser_preheat = subs.add_parser('preheat', help='Inject automatic tool preheats')
    parser_preheat.add_argument('--sec', type=int, default=30.0, help='Aproximate seconds to allow for preheat')
    
    # parser for pause
    parser_pause = subs.add_parser('pause', help='Inject automatic pause based on mass or length')
    parser_pause.add_argument('--tool', type=int, default=-1, help='Tool to apply pause to')
    parser_pause.add_argument('--diameter', type=float, default=None, help='Filament diameter. Defaults to 1.75mm')
    parser_pause.add_argument('--density', type=float, default=None, help='Filament density in g/cm^3. Defaults to 1.24 for PLA')
    group = parser_pause.add_mutually_exclusive_group(required=True)
    group.add_argument('--mass', type=str, default='', help='Pause at this many grams')
    group.add_argument('--length', type=str, default='', help='Pause at this length in mm')
    parser_pause.add_argument('--pausecode', type=str, default='M226', help='GCode text to inject at pause')
    
    parser.add_argument('gcode', action='store',
                        help='gcode file to process')
                        
    # parser for wipe tower fix
    parser_wipe = subs.add_parser('wtrf', help='Wipe Tower Retract Fix')
                        
    args = parser.parse_args()
    
    infile = args.gcode
    infile = os.path.abspath(infile)
    lines = load_file(infile)
    ms = MoveSim()
    ms.parse_lines(lines)
    
    if(args.cmd == 'preheat'):
        ms.calc_times()
        ms.gen_warmups(args.sec)
    elif(args.cmd == 'pause'):
        ms.gen_pause(**vars(args))
    elif(args.cmd == 'wtrf'):
        ms.wipe_tower_fix()
    
    with open(infile, 'w') as f:
        for l in ms.lines:
            f.write(l.get_lines(True))
