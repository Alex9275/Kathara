try: 
    import configparser as ConfigParser
except:
    import ConfigParser
config = ConfigParser.ConfigParser()
import ipaddress
import mmap
import os
import re
import sys
from collections import OrderedDict
from io import StringIO
from sys import platform as _platform

import depgen as dpg
import utils as u

DEBUG = True
PRINT = False
IMAGE_NAME = 'netkit_base'
DOCKER_HUB_PREFIX = "kathara/"
LINUX_TERMINAL_TYPE = 'xterm'

MAC_OS = "darwin"
WINDOWS = "win32"
LINUX = "linux"
LINUX2 = "linux2"

PLATFORM = LINUX

if _platform == MAC_OS:
    PLATFORM = MAC_OS
elif _platform == WINDOWS:
    PLATFORM = WINDOWS


def read_config():
    tmp_config = ConfigParser.ConfigParser()

    with open(os.path.join(os.environ['NETKIT_HOME'], '..', 'config'), 'r') as config_file:
        ini = u'[dummysection]\n' + config_file.read()

    ini_string = StringIO(ini)
    tmp_config.readfp(ini_string)
    conf = dict(tmp_config.items('dummysection'))   # Convert the tuple array into a dict

    return conf

kat_config = read_config()

try: 
    DOCKER_BIN = kat_config['win_bin']
except:
    DOCKER_BIN = 'docker'

if PLATFORM != WINDOWS:
    try: 
        DOCKER_BIN = kat_config['unix_bin']
    except:
        DOCKER_BIN = os.environ['NETKIT_HOME'] + '/wrapper/bin/netkit_dw'

SEPARATOR_WINDOWS = ' & '
BASH_SEPARATOR = ' ; '

if PLATFORM == WINDOWS:
    BASH_SEPARATOR = SEPARATOR_WINDOWS


def dep_sort(item, dependency_list):
    try:
        return dependency_list.index(item) + 1
    except:
        return 0


def reorder_by_lab_dep(path, machines):
    if not os.path.exists(os.path.join(path, 'lab.dep')): 
        return machines
    # getting dependencies inside a data structure
    dependencies = {}
    with open(os.path.join(path, 'lab.dep'), 'r') as conf:
        for line in conf:
            if line.strip() and line.strip() not in ['\n', '\r\n']:
                app = line.split(":")
                app[1] = re.sub('\s+', ' ', app[1]).strip()
                dependencies[app[0].strip()] = app[1].split(' ')    # dependencies[machine3] = [machine1, machine2]

    # building dependency set
    if dpg.has_loop(dependencies):
        sys.stderr.write("WARNING: loop in lab.dep, it will be ignored. \n")
        return machines

    dependency_list = dpg.flatten(dependencies)
    # reordering machines
    ordered_machines = OrderedDict(sorted(machines.items(), key=lambda t: dep_sort(t[0], dependency_list)))
    return ordered_machines


def lab_parse(path, force=False):
    if (not force) and (not os.path.exists(os.path.join(path, 'lab.conf'))):
        sys.stderr.write("No lab.conf in given directory: %s\n" % path)
        sys.exit(1)

    if force and (not os.path.exists(os.path.join(path, 'lab.conf'))):
        return {}, [], {}, {}   # has to get names from last positional args

    # Reads lab.conf in memory so it is faster.
    with open(os.path.join(path, 'lab.conf'), 'r') as lab_file:
        lab_mem_file = mmap.mmap(lab_file.fileno(), 0, prot=mmap.PROT_READ)

    machines = {}               # We get a dictionary of machines ignoring interfaces that have missing positions
                                # (eg: 1,3,6 instead of 0,1,2)
    links = set()               # We only need unique links
    options = {}                # Machine options

    line = lab_mem_file.readline()
    while line:
        if DEBUG:
            sys.stderr.write(line + "\n")

        matches = re.search(r"^(?P<key>[a-zA-Z0-9_]+)\[(?P<arg>\w+)\]=(?P<value>\"\w+\"|\'\w+\'|\w+)$",
                            line.strip()
                            )

        if matches:
            key = unicode(matches.group("key").strip(), "utf-8")
            arg = unicode(matches.group("arg").strip(), "utf-8")
            value = unicode(matches.group("value").replace('"', '').replace("'", ''), "utf-8")

            try:
                # It's an interface, handle it.
                interface_number = int(arg)

                links.add(value)

                if not machines.get(key):
                    machines[key] = []

                # Append everything, the interface number check will be done later.
                machines[key].append((value, interface_number))
            except ValueError:
                # Not an interface, add it to the machine options.
                if not options.get(key):
                    options[key] = []

                options[key].append((arg, value))

        line = lab_mem_file.readline()

    # Here we ignore interfaces that have missing positions (eg: 1,3,6 instead of 0,1,2)
    for machine_name in machines:
        # Sort the array before doing interface check.
        machines[machine_name].sort(key=lambda x: x[1])
        current_machine = machines[machine_name]

        for i in range(1, len(current_machine)):
            if current_machine[i - 1][1] != current_machine[i][1] - 1:
                # If a number is non sequential, the rest of the list is garbage.
                # Throw it away.
                machines[machine_name] = current_machine[:i]
                break

    machines = reorder_by_lab_dep(path, machines)
    
    if DEBUG:
        print (machines, options, {})

    return machines, links, options, {}


#parsing external.conf file
def external_parse(path):
    collision_domains = []
    interfaces = []
    with open(os.path.join(path, 'external.conf'),'r') as external_file:
        for line in external_file:
            if line.strip() and (line.strip() not in ['\n', '\r\n', '\n\r']) and (not line.startswith('#')):
                #insert collision domain in collisions_domains list
                collision_domains.append(line.split(" ")[0])
                #insert interface in interfaces list
                interfaces.append((line.split()[1]))
    return collision_domains, interfaces

#create external_commands
def external_commands(path, collision_domains, interfaces, execbash=False):
    lab_external_links_text = ''
    commands = []
    prefix = 'netkit_' + str(os.getuid()) + '_'

    for (collision_domain, interface) in zip(collision_domains, interfaces):                                       
        #check if paramater's interface have a vlan syntax 
        if interface.__contains__("."):
            prefix_interface = interface.split(".")[0]
            vlan_id = interface.split(".")[1]
            if (len(interface) > 15):
                prefix_truncate_interface = prefix_interface[-9:]
                interface = prefix_truncate_interface + '.' + vlan_id

            lab_external_links_text += interface + '\n'

            commands.append(os.path.join(os.environ['NETKIT_HOME'],'brctl_config_external ' + prefix + collision_domain + ' ' + interface + ' ' + prefix_interface  + ' ' + vlan_id))
        else:
            commands.append(os.path.join(os.environ['NETKIT_HOME'],'brctl_config_external ' + prefix + collision_domain + ' ' + interface))        

    if not execbash:
        if not PRINT: u.write_temp(lab_external_links_text, str(u.generate_urlsafe_hash(path)) + '_external_links', PLATFORM, file_mode="w+")

    return commands    


def create_commands(machines, links, options, metadata, path, execbash=False, no_machines_tmp=False, network_counter=0):
    docker = DOCKER_BIN

    # deciding machine and network prefix in order to avoid conflicts with other users and containers
    if PLATFORM != WINDOWS:
        prefix = 'netkit_' + str(os.getuid()) + '_'
    else:
        prefix = 'netkit_nt_'

    # generating network create command and network names separated by spaces for the temp file
    lab_links_text = ''
    lab_machines_text = ''
        
    create_network_template = docker + ' network create '
    create_network_commands = []

    base_path = os.path.join(os.environ['NETKIT_HOME'], 'temp')
    if PLATFORM != WINDOWS:
        base_path = os.path.join(os.environ['HOME'], 'netkit_temp')

    if not os.path.exists(os.path.join(base_path,'last_network_counter.txt')):
        last_network_counter = open(os.path.join(base_path,'last_network_counter.txt'), 'w')
        last_network_counter.close()

    with open(os.path.join(base_path,'last_network_counter.txt'), 'r') as last_network_counter:
        base_ip = u'172.19.0.0'
        max_ip = u'254.255.0.0'
        multiplier = 256 * 256
        max_counter = ( int(ipaddress.ip_address(max_ip)) - int(ipaddress.ip_address(base_ip)) ) // multiplier
        if network_counter == 0: # means it was not set by user
            try:
                network_counter = int(last_network_counter.readline()) % max_counter
            except:
                network_counter = 0
        for link in links:
            subnet = ipaddress.ip_address(base_ip) + (network_counter * multiplier)
            gateway = ipaddress.ip_address(base_ip) + (network_counter * multiplier) + 1
            create_network_commands.append(create_network_template + prefix + link + " --subnet=" + str(subnet) + "/16 --gateway=" + str(gateway))
            lab_links_text += prefix + link + ' '
            network_counter += 1
            create_network_commands.append(os.path.join(os.environ['NETKIT_HOME'], 'brctl_config ' + prefix + link))
    with open(os.path.join(base_path,'last_network_counter.txt'), 'w') as last_network_counter:
        last_network_counter.write(str(network_counter))
    
    # writing the network list in the temp file
    if not execbash:
        if not PRINT: u.write_temp(lab_links_text, str(u.generate_urlsafe_hash(path)) + '_links', PLATFORM, file_mode="w+")
    
    # generating commands for running the containers, copying the config folder and executing the terminals connected to the containers
    if PLATFORM != WINDOWS:
        create_machine_template = docker + ' run -tid --privileged=true --name ' + prefix + '{machine_name} --hostname={machine_name} --network=' + prefix + '{first_link} {machine_options} {image_name}'
    else: 
        create_machine_template = docker + ' run --volume="' + os.path.expanduser('~') +'":/hosthome -tid --privileged=true --name ' + prefix + '{machine_name} --hostname={machine_name} --network=' + prefix + '{first_link} {machine_options} {image_name}'
    # we could use -ti -a stdin -a stdout and then /bin/bash -c "commands;bash", 
    # but that woult execute commands like ifconfig BEFORE all the networks are linked
    create_machine_commands = []

    create_connection_template = docker + ' network connect ' + prefix + '{link} ' + prefix + '{machine_name}'
    create_bridge_connection_template = docker + ' network connect {link} ' + prefix + '{machine_name}'
    create_connection_commands = []
    create_bridge_connection_commands = []

    copy_folder_template = docker + ' cp "' + path + '{machine_name}/{folder_or_file}" ' + prefix + '{machine_name}:/{dest}'
    copy_folder_commands = []

    exec_template = docker + ' exec {params} -i --privileged=true ' + prefix + '{machine_name} {command}'
    exec_commands = []
    startup_commands = []

    count = 0

    for machine_name, interfaces in machines.items():
        this_image = DOCKER_HUB_PREFIX + IMAGE_NAME
        this_shell = 'bash'

        # copying the hostlab directory
        if not execbash:
            copy_folder_commands.append(docker + ' cp "' + path + '" ' + prefix + machine_name + ':/hostlab')

        #get the shell we run inside docker
        if options.get(machine_name):
            matching = [s for s in options[machine_name] if "shell" in s]
            if len(matching) > 0:
                this_shell = matching[0][1]

        # applying docker patch for /proc and icmp
        repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "sysctl net.ipv4.conf.all.rp_filter=0"'), ('{params}', '')
        startup_commands.insert(0, u.replace_multiple_items(repls, exec_template))
        repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "sysctl net.ipv4.conf.default.rp_filter=0"'), ('{params}', '')
        startup_commands.insert(1, u.replace_multiple_items(repls, exec_template))
        repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "sysctl net.ipv4.conf.lo.rp_filter=0"'), ('{params}', '')
        startup_commands.insert(2, u.replace_multiple_items(repls, exec_template))
        repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "sysctl net.ipv4.conf.eth0.rp_filter=0"'), ('{params}', '')
        startup_commands.insert(2, u.replace_multiple_items(repls, exec_template))

        # Parsing options from lab.conf
        machine_option_string = " "
        if options.get(machine_name):
            for opt, val in options[machine_name]:
                if opt=='mem' or opt=='M': 
                    machine_option_string+='--memory='+ val.upper() +' '
                if opt=='image' or opt=='i' or opt=='model-fs' or opt=='m' or opt=='f' or opt=='filesystem': 
                    this_image = DOCKER_HUB_PREFIX + val
                if opt=='eth': 
                    app = val.split(":")
                    create_network_commands.append(create_network_template + prefix + app[1])
                    repls = ('{link}', app[1]), ('{machine_name}', machine_name)
                    create_connection_commands.append(u.replace_multiple_items(repls, create_connection_template))
                    if not PRINT: u.write_temp(" " + prefix + app[1], u.generate_urlsafe_hash(path) + '_links', PLATFORM)
                    repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "sysctl net.ipv4.conf.eth'+str(app[0])+'.rp_filter=0"'), ('{params}', '')
                    startup_commands.insert(4, u.replace_multiple_items(repls, exec_template))
                if opt=='bridged': 
                    repls = ('{link}', "bridge"), ('{machine_name}', machine_name)
                    create_bridge_connection_commands.append(u.replace_multiple_items(repls, create_bridge_connection_template))
                if opt=='e' or opt=='exec':
                    repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "' + val.strip().replace('\\', r'\\').replace('"', r'\\"').replace("'", r"\\'") + '"'), ('{params}', '-d')
                    startup_commands.append(u.replace_multiple_items(repls, exec_template))
                if opt=='port': 
                    machine_option_string+='-p='+ val.upper() +':3000' + ' '
        repls = ('{machine_name}', machine_name), ('{number}', str(count)), ('{first_link}', interfaces[0][0]), ('{image_name}', this_image), ('{machine_options}', machine_option_string)
        create_machine_commands.append(u.replace_multiple_items(repls, create_machine_template))
        count += 1
        eth_cnt=1
        for link,_ in interfaces[1:]:
            repls = ('{link}', link), ('{machine_name}', machine_name)
            create_connection_commands.append(u.replace_multiple_items(repls, create_connection_template))
            repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "sysctl net.ipv4.conf.eth'+str(eth_cnt)+'.rp_filter=0"'), ('{params}', '')
            startup_commands.insert(4, u.replace_multiple_items(repls, exec_template))
            eth_cnt+=1
        # convoluted method to copy MACHINE_NAME/etc folder to the etc of the container
        if os.path.exists(os.path.join(path, machine_name)) and not execbash:
            for folder_or_file in os.listdir(os.path.join(path, machine_name)):
                if folder_or_file == 'etc': 
                    repls = ('{machine_name}', machine_name), ('{machine_name}', machine_name), ('{folder_or_file}', folder_or_file), ('{dest}', 'temp_etc')
                    repls2 = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "chmod -R 777 /temp_etc/*; cp -rfp /temp_etc/* /etc/; rm -rf /temp_etc; mkdir /var/log/zebra; chmod -R 777 /var/log/quagga; chmod -R 777 /var/log/zebra; chmod -R 777 /var/www/*"'), ('{params}', '')
                    startup_commands.insert(0, u.replace_multiple_items(repls2, exec_template))
                else:
                    repls = ('{machine_name}', machine_name), ('{machine_name}', machine_name), ('{folder_or_file}', folder_or_file), ('{dest}', '')
                copy_folder_commands.append(u.replace_multiple_items(repls, copy_folder_template))
        if PLATFORM == WINDOWS:
            repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "echo -ne \'\033]0;' + machine_name + '\007\'; bash"'), ('{params}', '-t -e TERM=vt100')
        else:
            repls = ('{machine_name}', machine_name), ('{command}', this_shell), ('{params}', '-t -e TERM=vt100')
        exec_commands.append(u.replace_multiple_items(repls, exec_template))
        lab_machines_text += prefix + machine_name + ' '

    # writing the container list in the temp file
    if not no_machines_tmp:
        if not execbash:
            if not PRINT: u.write_temp(lab_machines_text, str(u.generate_urlsafe_hash(path)) + '_machines', PLATFORM)


    # for each machine we have to get the machine.startup file and insert every non empty line as a string inside an array of exec commands. We also replace escapes and quotes
    for machine_name, _ in machines.items():
        startup_file = os.path.join(path, machine_name + '.startup')
        if os.path.exists(startup_file):
            f = open(startup_file, 'r')
            full_startup_command = ''
            for line in f:
                if line.strip() and (line.strip() not in ['\n', '\r\n', '\n\r']) and (not line.startswith('#')):
                    full_startup_command += line.strip().replace('\\', r'\\').replace('"', r'\"').replace("'", r"\'") + ';'
            f.close()
            repls = ('{machine_name}', machine_name), ('{command}', this_shell + ' -c "' + full_startup_command + '"'), ('{params}', '-d')
            startup_commands.append(u.replace_multiple_items(repls, exec_template))
    
    commands = create_network_commands + create_machine_commands + create_connection_commands + create_bridge_connection_commands + copy_folder_commands

    return commands, startup_commands, exec_commands
