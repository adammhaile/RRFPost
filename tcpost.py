import sys
import os
import re
import argparse

MOVE_RE = '([XYZEF] *-?\d+.?\d*)'

class GCodeLine():
    def __init__(self, num, line):
        self.num = num
        self.line = line
        self.pre = None
        self.post = None
        
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
    def __init__(self, warmup_time=30.0):
        self.warmup_time = warmup_time
        self.mf = re.compile(MOVE_RE)
        self.loc = [0, 0, 0]
        self.feedrate = 3000.0 / 60.0  # RRF default is 3000mm/min but we want mm/s
        self.lines = []
        self.tools = {}
    
    def parse_lines(self, lines):
        count = 0
        for l in lines:
            l = l.rstrip('\n\r')
            count += 1
            ul = l.rstrip().upper()
            
            if(ul.startswith('G0 ') or ul.startswith('G1 ')):
                move = Move(count, l)
                for m in self.mf.findall(ul):
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
                except:
                    print(f'Invalid T command: {l}')
                    
                tc = ToolChange(count, l, tool_num)
                self.lines.append(tc)
            else:
                gcl = GCodeLine(count, l)
                self.lines.append(gcl)
                
        return self.lines
        
    def calc_times(self):
        for l in self.lines:
            if isinstance(l, Move):
                m = l
                if m.t is not None:
                    continue
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
                
    def gen_warmups(self):
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
                        if td.temp is not None:
                            rl.post = f'G10 R{td.temp} P{l.t} ;  Warmup T{l.t}'
                        if lastTool >= 0:
                            if lastTool not in self.tools:
                                raise Exception(f'No temperature parameters defined for T{lastTool}')
                            td = self.tools[lastTool]
                            if td.standby is not None:
                                l.pre = f'G10 R{td.standby} P{lastTool} ;  Restore T{lastTool}'
                        break
                    if isinstance(rl, Move):
                        curTotal += rl.time
                        if curTotal >= self.warmup_time:
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
                

def load_file(path):
    with open(path, 'r') as f:
        return f.readlines()
        
def main():
    parser = argparse.ArgumentParser(
        description='TCPost: ToolChanger gcode post-processor'
    )
    
    parser.add_argument('--preheat', action='store', 
                        dest='preheat_seconds', type=int,
                        help='Inject automatic tool preheats')
    parser.add_argument('gcode', action='store',
                        help='gcode file to process')
                        
    args = parser.parse_args()
    if args.preheat_seconds is None:
        parser.print_help()
        sys.exit(1)

    warmup_time = args.preheat_seconds
    try:
        warmup_time = float(warmup_time)
    except:
        print('Error: warmup time value must be a number')
        sys.exit(1)

    infile = args.gcode
    infile = os.path.abspath(infile)
    lines = load_file(infile)
    ms = MoveSim(warmup_time)
    ms.parse_lines(lines)
    ms.calc_times()
    ms.gen_warmups()
    
    with open(infile, 'w') as f:
        for l in ms.lines:
            f.write(l.get_lines(True))

if __name__ == '__main__':
    main()