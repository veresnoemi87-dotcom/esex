import sys
import struct
import re
import ast

def parse_color(color_str):
    color_str = str(color_str).strip()
    if color_str.startswith('#'):
        hex_val = color_str.lstrip('#')
        if len(hex_val) == 6:
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            return (b << 16) | (g << 8) | r
    elif color_str.startswith('0x') or color_str.startswith('0X'):
        val = int(color_str, 16)
        r = (val >> 16) & 0xFF
        g = (val >> 8) & 0xFF
        b = val & 0xFF
        return (b << 16) | (g << 8) | r
    
    lower = color_str.lower()
    if lower == 'red': return 0x000000FF
    if lower == 'green': return 0x0000FF00
    if lower == 'blue': return 0x00FF0000
    if lower == 'black': return 0x00000000
    if lower == 'white': return 0x00FFFFFF
    return 0x000000FF

class DSLParser:
    """Advanced ES (Executable Script) DSL Parser supporting custom loops, all-key inputs, hex colors, and multiple shapes."""
    def __init__(self, source_code):
        self.source_code = source_code
        self.window_config = {
            'title': 'ES Engine',
            'width': 800,
            'height': 600,
            'resizable': False
        }
        self.variables = {'x': 400, 'y': 300, 'r': 30}
        self.texts = []
        self.circles = []
        self.rectangles = []
        self.input_actions = []

    def preprocess(self):
        code = re.sub(r'//.*', '', self.source_code)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code = re.sub(r'\blet\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=', r'\1 =', code)
        
        def convert_colons(match):
            func_name = match.group(1)
            args_str = match.group(2)
            fixed_args = re.sub(r'(?:["\']([a-zA-Z_][a-zA-Z0-9_]*?)["\']|([a-zA-Z_][a-zA-Z0-9_]*?))\s*:', r'\1\2=', args_str)
            return f"{func_name}({fixed_args})"

        code = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\((.*?)\)', convert_colons, code, flags=re.DOTALL)
        return code

    def parse(self):
        clean_code = self.preprocess()
        try:
            tree = ast.parse(clean_code)
        except SyntaxError as e:
            print(f"ES Syntax Error: {e}")
            sys.exit(1)

        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                        self.variables[target.id] = int(node.value.value)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                self._parse_call(node.value)
            elif isinstance(node, ast.While):
                self._parse_while(node)

    def _parse_call(self, node):
        func_name = self._get_func_name(node.func)
        if func_name in ('window', 'new.window'):
            for kw in node.keywords:
                if kw.arg == 'title' and isinstance(kw.value, ast.Constant):
                    self.window_config['title'] = str(kw.value.value)
                elif kw.arg == 'width' and isinstance(kw.value, ast.Constant):
                    self.window_config['width'] = int(kw.value.value)
                elif kw.arg == 'height' and isinstance(kw.value, ast.Constant):
                    self.window_config['height'] = int(kw.value.value)
        elif func_name == 'resizable.enable':
            self.window_config['resizable'] = True
        elif func_name == 'add.text':
            for kw in node.keywords:
                if kw.arg == 'text' and isinstance(kw.value, ast.Constant):
                    self.texts.append(str(kw.value.value))
        elif func_name == 'draw.circle':
            c_data = {'x_var': 'x', 'y_var': 'y', 'r': 30, 'color': '#ff0000'}
            for kw in node.keywords:
                if kw.arg == 'x' and isinstance(kw.value, ast.Name):
                    c_data['x_var'] = kw.value.id
                elif kw.arg == 'y' and isinstance(kw.value, ast.Name):
                    c_data['y_var'] = kw.value.id
                elif kw.arg == 'r' and isinstance(kw.value, ast.Constant):
                    c_data['r'] = int(kw.value.value)
                elif kw.arg == 'color' and isinstance(kw.value, ast.Constant):
                    c_data['color'] = str(kw.value.value)
            self.circles.append(c_data)
        elif func_name in ('draw.rect', 'draw.rectangle'):
            r_data = {'x_var': 'x', 'y_var': 'y', 'w': 60, 'h': 60, 'color': '#00ff00'}
            for kw in node.keywords:
                if kw.arg == 'x' and isinstance(kw.value, ast.Name):
                    r_data['x_var'] = kw.value.id
                elif kw.arg == 'y' and isinstance(kw.value, ast.Name):
                    r_data['y_var'] = kw.value.id
                elif kw.arg == 'w' and isinstance(kw.value, ast.Constant):
                    r_data['w'] = int(kw.value.value)
                elif kw.arg == 'h' and isinstance(kw.value, ast.Constant):
                    r_data['h'] = int(kw.value.value)
                elif kw.arg == 'color' and isinstance(kw.value, ast.Constant):
                    r_data['color'] = str(kw.value.value)
            self.rectangles.append(r_data)

    def _parse_while(self, node):
        for stmt in node.body:
            if isinstance(stmt, ast.If):
                test_call = stmt.test
                if isinstance(test_call, ast.Call) and self._get_func_name(test_call.func) == 'key.pressed':
                    key_arg = test_call.args[0] if test_call.args else ast.Constant(value='W')
                    key_char = str(key_arg.value) if isinstance(key_arg, ast.Constant) else 'W'
                    vk_code = ord(key_char.upper())
                    
                    for action_stmt in stmt.body:
                        if isinstance(action_stmt, ast.Assign):
                            var_name = action_stmt.targets[0].id
                            val_node = action_stmt.value
                            if isinstance(val_node, ast.BinOp):
                                op = type(val_node.op)
                                left = val_node.left.id if isinstance(val_node.left, ast.Name) else None
                                right = val_node.right.value if isinstance(val_node.right, ast.Constant) else 5
                                if left == var_name:
                                    self.input_actions.append({
                                        'vk': vk_code,
                                        'var': var_name,
                                        'op': op,
                                        'val': right
                                    })
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                self._parse_call(stmt.value)

    def _get_func_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_func_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return ""


class ImportBuilder:
    """PE Import Directory & IAT builder."""
    def __init__(self, base_rva):
        self.base_rva = base_rva
        self.data = bytearray()
        self.imports = {
            'USER32.dll': [
                'RegisterClassExA', 'CreateWindowExA', 'ShowWindow', 
                'GetMessageA', 'PeekMessageA', 'TranslateMessage', 'DispatchMessageA', 
                'DefWindowProcA', 'PostQuitMessage', 'BeginPaint', 'EndPaint', 
                'InvalidateRect', 'GetAsyncKeyState'
            ],
            'GDI32.dll': [
                'TextOutA', 'Ellipse', 'Rectangle', 'CreateSolidBrush', 'SelectObject', 'DeleteObject'
            ],
            'KERNEL32.dll': [
                'GetModuleHandleA', 'ExitProcess', 'Sleep'
            ]
        }
        self.iat_addrs = {}
        self.idt_size = 0
        self._build()

    def add_data(self, b):
        rva = self.base_rva + len(self.data)
        self.data.extend(b)
        return rva

    def _align(self, align_to=2):
        while len(self.data) % align_to != 0:
            self.data.append(0)

    def _build(self):
        self.idt_size = 20 * (len(self.imports) + 1)
        idt_offset = 0
        self.data.extend(b'\x00' * self.idt_size)

        iat_rvas, ilt_rvas, dll_name_rvas, func_name_rvas = {}, {}, {}, {}

        for dll, funcs in self.imports.items():
            iat_rvas[dll] = self.base_rva + len(self.data)
            for f in funcs:
                self.iat_addrs[(dll, f)] = self.base_rva + len(self.data)
                self.data.extend(b'\x00' * 8)
            self.data.extend(b'\x00' * 8)

        for dll, funcs in self.imports.items():
            ilt_rvas[dll] = self.base_rva + len(self.data)
            for f in funcs:
                self.data.extend(b'\x00' * 8)
            self.data.extend(b'\x00' * 8)

        for dll, funcs in self.imports.items():
            dll_name_rvas[dll] = self.add_data(dll.encode('ascii') + b'\x00')
            for f in funcs:
                self._align(2)
                func_name_rvas[(dll, f)] = self.add_data(struct.pack('<H', 0) + f.encode('ascii') + b'\x00')

        for dll, funcs in self.imports.items():
            iat_off = iat_rvas[dll] - self.base_rva
            ilt_off = ilt_rvas[dll] - self.base_rva
            for i, f in enumerate(funcs):
                entry = struct.pack('<Q', func_name_rvas[(dll, f)])
                self.data[iat_off + i*8 : iat_off + i*8 + 8] = entry
                self.data[ilt_off + i*8 : ilt_off + i*8 + 8] = entry

        for dll in self.imports.keys():
            entry = struct.pack('<IIIII', ilt_rvas[dll], 0, 0, dll_name_rvas[dll], iat_rvas[dll])
            self.data[idt_offset : idt_offset + 20] = entry
            idt_offset += 20


class Assembler:
    """x86-64 Machine Code Assembler with Structured Helpers."""
    def __init__(self, base_rva):
        self.code = bytearray()
        self.base_rva = base_rva
        self.labels = {}
        self.relocs = []

    def get_rva(self): 
        return self.base_rva + len(self.code)

    def add_label(self, name): 
        self.labels[name] = self.get_rva()

    def emit(self, b): 
        self.code.extend(b)

    def emit_call_rva(self, target_rva):
        disp = target_rva - (self.get_rva() + 6)
        self.emit(b'\xff\x15' + struct.pack('<i', disp))

    def emit_lea_rax_rva(self, target_rva):
        disp = target_rva - (self.get_rva() + 7)
        self.emit(b'\x48\x8d\x05' + struct.pack('<i', disp))

    def emit_lea_rcx_rva(self, target_rva):
        disp = target_rva - (self.get_rva() + 7)
        self.emit(b'\x48\x8d\x0d' + struct.pack('<i', disp))

    def emit_lea_rdx_rva(self, target_rva):
        disp = target_rva - (self.get_rva() + 7)
        self.emit(b'\x48\x8d\x15' + struct.pack('<i', disp))

    def emit_lea_r8_rva(self, target_rva):
        disp = target_rva - (self.get_rva() + 7)
        self.emit(b'\x4c\x8d\x05' + struct.pack('<i', disp))

    def emit_lea_r9_rva(self, target_rva):
        disp = target_rva - (self.get_rva() + 7)
        self.emit(b'\x4c\x8d\x0d' + struct.pack('<i', disp))

    def emit_lea_rdi_rva(self, target_rva):
        disp = target_rva - (self.get_rva() + 7)
        self.emit(b'\x48\x8d\x3d' + struct.pack('<i', disp))

    def emit_lea_rax_lva(self, label_name):
        self.relocs.append((len(self.code), label_name, 'lea_rax'))
        self.emit(b'\x48\x8d\x05\x00\x00\x00\x00')

    def emit_jmp_label(self, label_name):
        self.relocs.append((len(self.code), label_name, 'jmp'))
        self.emit(b'\xe9\x00\x00\x00\x00')

    def emit_je_label(self, label_name):
        self.relocs.append((len(self.code), label_name, 'je'))
        self.emit(b'\x0f\x84\x00\x00\x00\x00')

    def emit_jns_label(self, label_name):
        self.relocs.append((len(self.code), label_name, 'jns'))
        self.emit(b'\x0f\x89\x00\x00\x00\x00')

    def resolve_labels(self):
        for offset, label, r_type in self.relocs:
            target_rva = self.labels[label]
            if r_type == 'lea_rax':
                disp = target_rva - (self.base_rva + offset + 7)
                self.code[offset+3 : offset+7] = struct.pack('<i', disp)
            elif r_type in ('jmp', 'je', 'jns'):
                if r_type in ('je', 'jns'):
                    disp = target_rva - (self.base_rva + offset + 6)
                    self.code[offset+2 : offset+6] = struct.pack('<i', disp)
                else:
                    disp = target_rva - (self.base_rva + offset + 5)
                    self.code[offset+1 : offset+5] = struct.pack('<i', disp)


class TrueNativePECompiler:
    """Compiles the dynamic ES DSL script into a clean x64 binary."""
    def __init__(self, source_code):
        self.parser = DSLParser(source_code)
        self.parser.parse()
        self.window_config = self.parser.window_config

    def compile(self) -> bytes:
        text_rva  = 0x1000
        rdata_rva = 0x2000
        data_rva  = 0x3000

        ib = ImportBuilder(rdata_rva)

        data_section = bytearray()
        class_name_rva = data_rva
        data_section.extend(b'NativeWindowClass\x00')
        
        win_name_rva = data_rva + len(data_section)
        data_section.extend(self.window_config['title'].encode('mbcs') + b'\x00')

        var_rvas = {}
        for var_name, val in self.parser.variables.items():
            while len(data_section) % 8 != 0: 
                data_section.append(0)
            var_rvas[var_name] = data_rva + len(data_section)
            data_section.extend(struct.pack('<q', val))

        text_rvas = []
        for txt in self.parser.texts:
            while len(data_section) % 8 != 0: 
                data_section.append(0)
            text_rvas.append((data_rva + len(data_section), txt))
            data_section.extend(txt.encode('mbcs') + b'\x00')
        
        while len(data_section) % 8 != 0: 
            data_section.append(0)
        
        wndclass_rva = data_rva + len(data_section)
        data_section.extend(b'\x00' * 80)
        
        msg_rva = data_rva + len(data_section)
        data_section.extend(b'\x00' * 48)

        ps_rva = data_rva + len(data_section)
        data_section.extend(b'\x00' * 72)

        hwnd_holder_rva = data_rva + len(data_section)
        data_section.extend(b'\x00' * 8)

        asm = Assembler(text_rva)
        
        asm.add_label("EntryPoint")
        asm.emit(b'\x48\x83\xec\x68')
        asm.emit(b'\x48\x31\xc9')
        asm.emit_call_rva(ib.iat_addrs[('KERNEL32.dll', 'GetModuleHandleA')])
        asm.emit(b'\x48\x89\xc3')

        # Register Window Class
        asm.emit_lea_rdi_rva(wndclass_rva)
        asm.emit(b'\xc7\x07\x50\x00\x00\x00')          # cbSize = 80
        asm.emit(b'\xc7\x47\x04\x03\x00\x00\x00')       # style = CS_HREDRAW | CS_VREDRAW
        asm.emit_lea_rax_lva("WndProc")                 # lpfnWndProc
        asm.emit(b'\x48\x89\x47\x08')                   
        asm.emit(b'\x48\x89\x5f\x18')                   
        asm.emit(b'\x48\xc7\x47\x30\x06\x00\x00\x00')    # hbrBackground
        asm.emit_lea_rax_rva(class_name_rva)
        asm.emit(b'\x48\x89\x47\x40')                   # lpszClassName
        
        asm.emit(b'\x48\x89\xf9')
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'RegisterClassExA')])

        # Create Window
        asm.emit(b'\x48\x31\xc9')
        asm.emit_lea_rdx_rva(class_name_rva)
        asm.emit_lea_r8_rva(win_name_rva)
        asm.emit(b'\x41\xb9\x00\x00\xcf\x00')          # WS_OVERLAPPEDWINDOW
        
        asm.emit(b'\xc7\x44\x24\x20\x00\x00\x00\x80')  # CW_USEDEFAULT
        asm.emit(b'\xc7\x44\x24\x28\x00\x00\x00\x80')  # CW_USEDEFAULT
        asm.emit(b'\xc7\x44\x24\x30' + struct.pack('<i', self.window_config['width']))
        asm.emit(b'\xc7\x44\x24\x38' + struct.pack('<i', self.window_config['height']))
        asm.emit(b'\x48\xc7\x44\x24\x40\x00\x00\x00\x00')
        asm.emit(b'\x48\xc7\x44\x24\x48\x00\x00\x00\x00')
        asm.emit(b'\x48\x89\x5c\x24\x50')
        asm.emit(b'\x48\xc7\x44\x24\x58\x00\x00\x00\x00')
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'CreateWindowExA')])

        asm.emit(b'\x48\x89\xc6') 
        asm.emit_lea_rax_rva(hwnd_holder_rva)
        asm.emit(b'\x48\x89\x30')

        asm.emit(b'\x48\x89\xf1')
        asm.emit(b'\x48\xc7\xc2\x05\x00\x00\x00')       # SW_SHOW
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'ShowWindow')])

        # Message & Input Loop
        asm.add_label("MessageLoop")
        
        asm.emit_lea_rcx_rva(msg_rva)
        asm.emit(b'\x48\x31\xd2')                       # rdx = NULL
        asm.emit(b'\x4d\x31\xc0')                       # r8 = 0
        asm.emit(b'\x4d\x31\xc9')                       # r9 = 0
        asm.emit(b'\xc7\x44\x24\x20\x01\x00\x00\x00')    # PM_REMOVE
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'PeekMessageA')])
        asm.emit(b'\x85\xc0')
        asm.emit_je_label("GameUpdate")

        asm.emit_lea_rax_rva(msg_rva)
        asm.emit(b'\x48\x8b\x40\x08')
        asm.emit(b'\x3d\x12\x00\x00\x00')               # WM_QUIT
        asm.emit_je_label("Exit")

        asm.emit_lea_rcx_rva(msg_rva)
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'TranslateMessage')])
        asm.emit_lea_rcx_rva(msg_rva)
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'DispatchMessageA')])
        asm.emit_jmp_label("MessageLoop")

        # Key Input Handling
        asm.add_label("GameUpdate")
        
        for idx, action in enumerate(self.parser.input_actions):
            next_label = f"SkipAction_{idx}"
            vk = action['vk']
            var_rva = var_rvas[action['var']]
            val = action['val']
            is_add = action['op'] == ast.Add

            asm.emit(b'\x48\xc7\xc1' + struct.pack('<I', vk))
            asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'GetAsyncKeyState')])
            asm.emit(b'\x66\x85\xc0')
            asm.emit_jns_label(next_label)
            
            asm.emit_lea_rax_rva(var_rva)
            asm.emit(b'\x48\x8b\x00')
            if is_add:
                asm.emit(b'\x48\x83\xc0' + bytes([val]))
            else:
                asm.emit(b'\x48\x83\xe8' + bytes([val]))
            asm.emit_lea_rcx_rva(var_rva)
            asm.emit(b'\x48\x89\x01')

            asm.add_label(next_label)

        # Trigger Redraw
        asm.emit_lea_rax_rva(hwnd_holder_rva)
        asm.emit(b'\x48\x8b\x00')
        asm.emit(b'\x48\x89\xc1')
        asm.emit(b'\x48\x31\xd2')
        asm.emit(b'\x41\xb8\x01\x00\x00\x00')
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'InvalidateRect')])

        # Sleep(16) ~60 FPS
        asm.emit(b'\x48\xc7\xc1\x10\x00\x00\x00')
        asm.emit_call_rva(ib.iat_addrs[('KERNEL32.dll', 'Sleep')])

        asm.emit_jmp_label("MessageLoop")

        asm.add_label("Exit")
        asm.emit(b'\x48\x31\xc9')
        asm.emit_call_rva(ib.iat_addrs[('KERNEL32.dll', 'ExitProcess')])

        # WndProc: 16-byte aligned Win64 stack frame & valid machine code
        asm.add_label("WndProc")
        asm.emit(b'\x55')                              # push rbp
        asm.emit(b'\x48\x89\xe5')                      # mov rbp, rsp
        asm.emit(b'\x48\x83\xec\x50')                  # sub rsp, 0x50 (16-byte aligned)
        
        asm.emit(b'\x48\x89\x5d\xf8')                  # [rbp-0x08] = RBX
        asm.emit(b'\x48\x89\x75\xf0')                  # [rbp-0x10] = RSI (PRESERVED!)
        asm.emit(b'\x48\x89\x4d\xe8')                  # [rbp-0x18] = RCX (HWND)

        asm.emit(b'\x83\xfa\x0f')                      # cmp edx, WM_PAINT (0x0F)
        asm.emit_je_label("Paint")
        asm.emit(b'\x83\xfa\x02')                      # cmp edx, WM_DESTROY (0x02)
        asm.emit_je_label("Destroy")

        # Default WndProc (automatically clears background on WM_ERASEBKGND via DefWindowProcA)
        asm.emit(b'\x48\x8b\x4d\xe8')                  
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'DefWindowProcA')])
        asm.emit_jmp_label("WndProc_End")

        # Handle WM_PAINT
        asm.add_label("Paint")
        asm.emit(b'\x48\x8b\x4d\xe8')                  
        asm.emit_lea_rdx_rva(ps_rva)
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'BeginPaint')])
        asm.emit(b'\x48\x89\xc6')                      # rsi = HDC

        # Render Texts
        for rva_val, txt in text_rvas:
            asm.emit(b'\x48\x89\xf1')                  # hdc -> rcx
            asm.emit(b'\xba\x14\x00\x00\x00')          # mov edx, 20 (X)
            asm.emit(b'\x41\xb8\x14\x00\x00\x00')      # mov r8d, 20 (Y)
            asm.emit_lea_r9_rva(rva_val)               # lpString -> r9
            asm.emit(b'\xc7\x44\x24\x20' + struct.pack('<I', len(txt))) # [rsp+20] = cch
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'TextOutA')])

        # Render Rectangles
        for r in self.parser.rectangles:
            color_ref = parse_color(r.get('color', '#00ff00'))
            asm.emit(b'\x48\xc7\xc1' + struct.pack('<I', color_ref))
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'CreateSolidBrush')])
            asm.emit(b'\x48\x89\x45\xe0')

            asm.emit(b'\x48\x8b\x55\xe0')
            asm.emit(b'\x48\x89\xf1')
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'SelectObject')])
            asm.emit(b'\x48\x89\x45\xd8')

            rx_rva = var_rvas[r.get('x_var', 'x')]
            ry_rva = var_rvas[r.get('y_var', 'y')]
            rw = r['w']
            rh = r['h']

            asm.emit_lea_rax_rva(rx_rva)
            asm.emit(b'\x8b\x00')
            asm.emit(b'\x89\x45\xd0')

            asm.emit_lea_rax_rva(ry_rva)
            asm.emit(b'\x8b\x00')
            asm.emit(b'\x89\x45\xc8')

            asm.emit(b'\x8b\x45\xd0')
            asm.emit(b'\x89\xc2')

            asm.emit(b'\x8b\x45\xc8')
            asm.emit(b'\x41\x89\xc0')

            asm.emit(b'\x8b\x45\xd0')
            asm.emit(b'\x05' + struct.pack('<i', rw))
            asm.emit(b'\x41\x89\xc1')

            asm.emit(b'\x8b\x45\xc8')
            asm.emit(b'\x05' + struct.pack('<i', rh))
            asm.emit(b'\x89\x44\x24\x20')

            asm.emit(b'\x48\x89\xf1')
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'Rectangle')])

            asm.emit(b'\x48\x8b\x55\xd8')
            asm.emit(b'\x48\x89\xf1')
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'SelectObject')])

            asm.emit(b'\x48\x8b\x4d\xe0')
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'DeleteObject')])

        # Render Circles
        for c in self.parser.circles:
            color_ref = parse_color(c.get('color', '#ff0000'))
            asm.emit(b'\x48\xc7\xc1' + struct.pack('<I', color_ref))
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'CreateSolidBrush')])
            asm.emit(b'\x48\x89\x45\xe0')

            asm.emit(b'\x48\x8b\x55\xe0')
            asm.emit(b'\x48\x89\xf1')
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'SelectObject')])
            asm.emit(b'\x48\x89\x45\xd8')

            cx_rva = var_rvas[c.get('x_var', 'x')]
            cy_rva = var_rvas[c.get('y_var', 'y')]
            radius = c['r']

            asm.emit_lea_rax_rva(cx_rva)
            asm.emit(b'\x8b\x00')
            asm.emit(b'\x89\x45\xd0')

            asm.emit_lea_rax_rva(cy_rva)
            asm.emit(b'\x8b\x00')
            asm.emit(b'\x89\x45\xc8')

            asm.emit(b'\x8b\x45\xd0')
            asm.emit(b'\x2d' + struct.pack('<i', radius))
            asm.emit(b'\x89\xc2')

            asm.emit(b'\x8b\x45\xc8')
            asm.emit(b'\x2d' + struct.pack('<i', radius))
            asm.emit(b'\x41\x89\xc0')

            asm.emit(b'\x8b\x45\xd0')
            asm.emit(b'\x05' + struct.pack('<i', radius))
            asm.emit(b'\x41\x89\xc1')

            asm.emit(b'\x8b\x45\xc8')
            asm.emit(b'\x05' + struct.pack('<i', radius))
            asm.emit(b'\x89\x44\x24\x20')

            asm.emit(b'\x48\x89\xf1')
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'Ellipse')])

            asm.emit(b'\x48\x8b\x55\xd8')
            asm.emit(b'\x48\x89\xf1')
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'SelectObject')])

            asm.emit(b'\x48\x8b\x4d\xe0')
            asm.emit_call_rva(ib.iat_addrs[('GDI32.dll', 'DeleteObject')])

        asm.add_label("Paint_End")
        asm.emit(b'\x48\x8b\x4d\xe8')                  
        asm.emit_lea_rdx_rva(ps_rva)
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'EndPaint')])
        asm.emit(b'\x48\x31\xc0')                      
        asm.emit_jmp_label("WndProc_End")

        asm.add_label("Destroy")
        asm.emit(b'\x48\x31\xc9')
        asm.emit_call_rva(ib.iat_addrs[('USER32.dll', 'PostQuitMessage')])
        asm.emit(b'\x48\x31\xc0')

        # Epilogue restoring nonvolatile registers cleanly
        asm.add_label("WndProc_End")
        asm.emit(b'\x48\x8b\x75\xf0')                  # restore RSI
        asm.emit(b'\x48\x8b\x5d\xf8')                  # restore RBX
        asm.emit(b'\x48\x83\xc4\x50')                  # add rsp, 0x50
        asm.emit(b'\x5d\xc3')                          # pop rbp, ret
        
        asm.resolve_labels()

        def align(val, alignment):
            rem = val % alignment
            return val + (alignment - rem) if rem != 0 else val

        text_raw_size = align(len(asm.code), 0x200)
        rdata_raw_size = align(len(ib.data), 0x200)
        data_raw_size = align(len(data_section), 0x200)

        image_base = 0x0000000140000000
        size_of_image = align(data_rva + align(len(data_section), 0x1000), 0x1000)

        dos_header = bytearray(64)
        dos_header[0:2] = b'MZ'
        dos_header[0x3C:0x40] = struct.pack('<I', 0x80)
        dos_stub = b'\x0e\x1f\xba\x0e\x00\xb4\x09\xcd\x21\xb8\x01\x4c\xcd\x21This program cannot be run in DOS mode.\r\r\n$\x00\x00\x00'.ljust(0x40, b'\x00')
        pe_sig = b'PE\x00\x00'
        coff = struct.pack('<HHIIIHH', 0x8664, 3, 0, 0, 0, 0xF0, 0x0022)

        data_dirs = bytearray(128)
        data_dirs[8:16] = struct.pack('<II', rdata_rva, ib.idt_size)

        def build_headers(sz_headers):
            opt_header = struct.pack(
                '<HBBIIIIIQIIHHHHHHIIIIHHQQQQII',
                0x020B, 14, 0,
                text_raw_size, rdata_raw_size + data_raw_size, 0,
                text_rva, text_rva, image_base,
                0x1000, 0x200, 6, 0, 0, 0, 6, 0, 0,
                size_of_image, sz_headers, 0, 2, 0x8120,
                0x100000, 0x1000, 0x100000, 0x1000, 0, 16
            ) + bytes(data_dirs)

            sec_text = struct.pack('<8sIIIIIIHHI', b'.text\x00\x00\x00', len(asm.code), text_rva, text_raw_size, sz_headers, 0, 0, 0, 0, 0x60000020)
            sec_rdata = struct.pack('<8sIIIIIIHHI', b'.rdata\x00\x00', len(ib.data), rdata_rva, rdata_raw_size, sz_headers + text_raw_size, 0, 0, 0, 0, 0x40000040)
            sec_data = struct.pack('<8sIIIIIIHHI', b'.data\x00\x00\x00', len(data_section), data_rva, data_raw_size, sz_headers + text_raw_size + rdata_raw_size, 0, 0, 0, 0, 0xC0000040)
            return dos_header + dos_stub + pe_sig + coff + opt_header + sec_text + sec_rdata + sec_data

        raw_headers_len = len(build_headers(0x400))
        size_of_headers = align(raw_headers_len, 0x200)
        
        final_headers = build_headers(size_of_headers).ljust(size_of_headers, b'\x00')
        aligned_code = bytes(asm.code).ljust(text_raw_size, b'\x00')
        aligned_rdata = bytes(ib.data).ljust(rdata_raw_size, b'\x00')
        aligned_data = bytes(data_section).ljust(data_raw_size, b'\x00')

        return final_headers + aligned_code + aligned_rdata + aligned_data


def print_help():
    print("ES (Executable Script) Compiler v3.0.0")
    print("Usage: esex <input.es> [-o output.exe]")
    print("Options:")
    print("  -h, --help       Show this help message")
    print("  -hc, --help-code Output a demo ES script template")
    print("  -o <file>        Specify output executable name")

def print_demo():
    print("""// ES (Executable Script) Demo Script v3.0.0
window(title: "ES Engine Demo", width: 800, height: 600)
resizable.enable()

let x = 400
let y = 300

add.text(text: "ES Engine v3.0.0 - Controlled via loops and all-key bindings!")

draw.circle(x: x, y: y, r: 35, color: "#ff3366")
draw.rectangle(x: 150, y: 150, w: 100, h: 50, color: "#33ccff")

while true {
    if key.pressed("W") {
        y = y - 5
    }
    if key.pressed("S") {
        y = y + 5
    }
    if key.pressed("A") {
        x = x - 5
    }
    if key.pressed("D") {
        x = x + 5
    }
}""")

def main():
    if "-h" in sys.argv or "--help" in sys.argv or len(sys.argv) < 2:
        print_help()
        return

    if "-hc" in sys.argv or "--help-code" in sys.argv:
        print_demo()
        return

    input_file = sys.argv[1]
    output_file = "output.exe"

    if "-o" in sys.argv and sys.argv.index("-o") + 1 < len(sys.argv):
        output_file = sys.argv[sys.argv.index("-o") + 1]

    with open(input_file, "r", encoding="utf-8") as f:
        source_code = f.read()

    compiler = TrueNativePECompiler(source_code)
    pe_bytes = compiler.compile()
    
    with open(output_file, "wb") as f:
        f.write(pe_bytes)
    print(f"Successfully compiled ES script into '{output_file}'!")

if __name__ == "__main__":
    main()