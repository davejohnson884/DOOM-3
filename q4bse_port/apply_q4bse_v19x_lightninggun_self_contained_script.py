#!/usr/bin/env python3
'''V19X: compile the standalone Lightning Gun script directly from the game DLL.

This removes the final packaging dependency on script/weapon_chainsaw.script.
The stock Doom 3 doom_main.script remains untouched and the stock chainsaw script
continues to load normally. The additional script/weapon_lightninggun.script is
compiled during idProgram::Startup before FinishCompilation().
'''
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
program_cpp = root / 'neo' / 'game' / 'script' / 'Script_Program.cpp'
if not program_cpp.exists():
    raise SystemExit(f'V19X prerequisite missing: {program_cpp}')

text = program_cpp.read_text(encoding='utf-8-sig')

old = '''\t// load the default script\n\tif ( defaultScript && *defaultScript ) {\n\t\tCompileFile( defaultScript );\n\t}\n\n\tFinishCompilation();\n'''
new = '''\t// load the default script\n\tif ( defaultScript && *defaultScript ) {\n\t\tCompileFile( defaultScript );\n\t}\n\n\t// V19X: the Quake 4 Lightning Gun is a true additional weapon. Compile its\n\t// script as a separate unit so the PK4 does not need to replace or piggyback\n\t// on Doom 3's weapon_chainsaw.script or doom_main.script.\n\tCompileFile( "script/weapon_lightninggun.script" );\n\n\tFinishCompilation();\n'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f'V19X: expected one script Startup compile block, found {hits}')
text = text.replace(old, new, 1)

for needle in (
    'CompileFile( "script/weapon_lightninggun.script" );',
    'true additional weapon',
):
    if needle not in text:
        raise SystemExit(f'V19X verification missing: {needle}')

program_cpp.write_text(text, encoding='utf-8')
print('V19X standalone Lightning Gun script loader applied')
print(' - stock doom_main.script remains untouched')
print(' - stock weapon_chainsaw.script remains untouched')
print(' - script/weapon_lightninggun.script compiles independently before FinishCompilation')
