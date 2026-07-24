import os
import re

ui_dir = 'app/ui'

files_to_check = [
    'host_discovery.py',
    'camera_scan.py', 
    'traceroute.py',
    'traffic_monitor.py',
    'tools.py',
    'network_health.py',
    'link_monitor.py',
    'ip_info.py',
    'firewall.py',
    'dashboard.py',
    'remote_desktop.py',
    'local_settings.py',
    'speed_internal.py',
]

for filename in files_to_check:
    filepath = os.path.join(ui_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    new_lines = []
    modified = False
    
    for i, line in enumerate(lines):
        if 'subprocess.run(' in line or 'subprocess.Popen(' in line:
            if 'CREATE_NO_WINDOW' not in line:
                open_paren = line.find('(')
                close_paren = line.rfind(')')
                
                if open_paren != -1 and close_paren != -1:
                    params = line[open_paren+1:close_paren].strip()
                    
                    if params:
                        if params.endswith(','):
                            new_params = params + ' creationflags=subprocess.CREATE_NO_WINDOW'
                        else:
                            new_params = params + ', creationflags=subprocess.CREATE_NO_WINDOW'
                        new_line = line[:open_paren+1] + new_params + line[close_paren:]
                    else:
                        new_line = line[:close_paren] + 'creationflags=subprocess.CREATE_NO_WINDOW)'
                    
                    new_lines.append(new_line)
                    modified = True
                    print(f'Fixed: {filename}:{i+1}')
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        print(f'Updated: {filename}')

print('Done!')
