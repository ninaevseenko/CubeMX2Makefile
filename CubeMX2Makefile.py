#!/usr/bin/env python

import sys
import re
import shutil
import os
import os.path
import string
import xml.etree.ElementTree

# Return codes
C2M_ERR_SUCCESS             =  0
C2M_ERR_INVALID_COMMANDLINE = -1
C2M_ERR_LOAD_TEMPLATE       = -2
C2M_ERR_NO_PROJECT          = -3
C2M_ERR_PROJECT_FILE        = -4
C2M_ERR_IO                  = -5
C2M_ERR_NEED_UPDATE         = -6

# Configuration

# STM32 MCU to compiler flags.
mcu_regex_to_cflags_dict = {
    'STM32(F|L)0': '-mthumb -mcpu=cortex-m0',
    'STM32(F|L)1': '-mthumb -mcpu=cortex-m3',
    'STM32(F|L)2': '-mthumb -mcpu=cortex-m3',
    'STM32(F|L)3': '-mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard',
    'STM32(F|L)4': '-mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard',
    'STM32(F|L)7': '-mthumb -mcpu=cortex-m7 -mfpu=fpv4-sp-d16 -mfloat-abi=hard',
}


def make_path(path):
    parent_path = re.findall('PARENT-(\d+)-PROJECT_LOC.+', path)
    if not parent_path or len(parent_path) != 1:
        return path
    parent_dir = "../" * (int(parent_path[0]) + 1)
    path = re.sub('PARENT-(\d+)-PROJECT_LOC', parent_dir, path)
    return path


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("\nSTM32CubeMX project to Makefile V2.0\n")
        sys.stderr.write("-==================================-\n")
        sys.stderr.write("Initially written by Baoshi <mail\x40ba0sh1.com> on 2015-02-22\n")
        sys.stderr.write("Updated 2017-04-27 for STM32CubeMX 4.20.1 http://www.st.com/stm32cube\n")
        sys.stderr.write("Refer to history.txt for contributors, thanks!\n")
        sys.stderr.write("Apache License 2.0 <http://www.apachstme3w2e.org/licenses/LICENSE-2.0>\n")
        sys.stderr.write("\nUsage:\n")
        sys.stderr.write("  CubeMX2Makefile.py <SW4STM32 project folder>\n")
        sys.exit(C2M_ERR_INVALID_COMMANDLINE)

    # Load template files
    app_folder_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    template_file_path = os.path.join(app_folder_path, 'CubeMX2Makefile.tpl')
    try:
        with open(template_file_path, 'r') as f:
            makefile_template = string.Template(f.read())
    except EnvironmentError as e:
        sys.stderr.write("Unable to read template file: {}. Error: {}".format(template_file_path, str(e)))
        sys.exit(C2M_ERR_LOAD_TEMPLATE)

    proj_folder_path = os.path.abspath(sys.argv[1])
    if not os.path.isdir(proj_folder_path):
        sys.stderr.write("STM32CubeMX \"Toolchain Folder Location\" not found: {}\n".format(proj_folder_path))
        sys.exit(C2M_ERR_INVALID_COMMANDLINE)

    proj_name = os.path.splitext(os.path.basename(proj_folder_path))[0]
    ac6_project_path = os.path.join(proj_folder_path,'.project')
    ac6_cproject_path = os.path.join(proj_folder_path,'.cproject')
    if not (os.path.isfile(ac6_project_path) and os.path.isfile(ac6_cproject_path)):
        sys.stderr.write("SW4STM32 project not found, use STM32CubeMX to generate a SW4STM32 project first\n")
        sys.exit(C2M_ERR_NO_PROJECT)

    c_includes = []
    c_sources = []
    asm_sources = []
    asm_includes = []

    # parse .project
    try:
        tree = xml.etree.ElementTree.parse(ac6_project_path)
    except Exception as e:
        sys.stderr.write("Unable to parse SW4STM32 .project file: {}. Error: {}\n".format(ac6_project_path, str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    root = tree.getroot()
    linked_resources = root.findall('.//linkedResources/link/location')
    for node in linked_resources:
        path = make_path(node.text)
        if path.endswith('.c'):
            c_sources.append(path)
        elif path.endswith('.s'):
            asm_sources.append(path)

    # .cproject file
    try:
        tree = xml.etree.ElementTree.parse(ac6_cproject_path)
    except Exception as e:
        sys.stderr.write("Unable to parse SW4STM32 .cproject file: {}. Error: {}\n".format(ac6_cproject_path, str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    conf = tree.find('.//configuration[@name="Debug"]')

    # MCU
    try:
        mcu_node = conf.find('.//option[@name="Mcu"]')
        mcu_str = mcu_node.attrib.get('value')
        #sys.stdout.write("For MCU: {}\n".format(mcu_str))
    except Exception as e:
        sys.stderr.write("Unable to find target MCU node. Error: {}\n".format(str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    for mcu_regex_pattern, cflags in mcu_regex_to_cflags_dict.items():
        if re.match(mcu_regex_pattern, mcu_str):
            cflags_subst = cflags
            ld_subst = cflags
            break
    else:
        sys.stderr.write("Unknown MCU: {}\n".format(mcu_str))
        sys.stderr.write("Please contact author for an update of this utility.\n")
        sys.stderr.exit(C2M_ERR_NEED_UPDATE)

    # AS symbols
    as_defs_subst = 'AS_DEFS ='

    nodes = conf.findall('.//tool[@name="MCU GCC Compiler"]/option[@valueType="includePath"]/listOptionValue')
    for node in nodes:
        value = node.attrib.get('value')
        if value:
            c_includes.append(value)

    # C symbols
    c_defs_subst = 'C_DEFS ='
    c_def_node_list = conf.findall('.//tool[@name="MCU GCC Compiler"]/option[@valueType="definedSymbols"]/listOptionValue')
    for c_def_node in c_def_node_list:
        c_def_str = c_def_node.attrib.get('value')
        if c_def_str:
            c_defs_subst += ' -D{}'.format(re.sub(r'([()])', r'\\\1', c_def_str))

    # Link script
    ld_script_node = conf.find('.//tool[@name="MCU GCC Linker"]/option[@superClass="fr.ac6.managedbuild.tool.gnu.cross.c.linker.script"]')
    try:
        ld_script_path = ld_script_node.attrib.get('value')
    except Exception as e:
        sys.stderr.write("Unable to find link script. Error: {}\n".format(str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    #ld_script_name = os.path.basename(ld_script_path)
    ld_script_subst = 'LDSCRIPT = {}'.format(ld_script_path)

    # Specs
    specs_node = conf.find('.//tool[@name="MCU GCC Linker"]/option[@superClass="gnu.c.link.option.ldflags"]')
    try:
        specs = specs_node.attrib.get('value')
    except Exception as e:
        sys.stderr.write("Unable to find link specs. Error: {}\n".format(str(e)))
        sys.exit(C2M_ERR_PROJECT_FILE)
    specs_subst = specs
    
    makefile_str = makefile_template.substitute(
        TARGET = proj_name,
        MCU = cflags_subst,
        LDMCU = ld_subst,
        C_SOURCES = "C_SOURCES = \\\n" + "\\\n".join(c_sources),
        ASM_SOURCES = "ASM_SOURCES = \\\n" + "\\\n".join(asm_sources),
        AS_DEFS = as_defs_subst,
        AS_INCLUDES = "ASM_INCLUDES = -I" + " -I".join(asm_includes),
        C_DEFS = c_defs_subst,
        C_INCLUDES = "C_INCLUDES = -I" + " -I".join(c_includes),
        LDSCRIPT = ld_script_subst,
        SPECS = specs_subst)

    makefile_dir = proj_folder_path + '/cubemx2makefile_generated/'
    os.mkdir(makefile_dir)
    makefile_path = os.path.join(makefile_dir, 'Makefile')
    try:
        with open(makefile_path, 'wb') as f:
            f.write(makefile_str)
    except EnvironmentError as e:
        sys.stderr.write("Unable to write Makefile: {}. Error: {}\n".format(makefile_path, str(e)))
        sys.exit(C2M_ERR_IO)

    sys.stdout.write("Makefile created: {}\n".format(makefile_path))
    
    sys.exit(C2M_ERR_SUCCESS)



if __name__ == '__main__':
    main()
