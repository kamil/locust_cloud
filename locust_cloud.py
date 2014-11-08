#!/usr/bin/env python

import threading, logging, uuid, time, os
import paramiko as ssh
from boto.ec2 import connect_to_region
from string import Template

import constants
from instance import Instance 

# logging.basicConfig(format='%(asctime)s %(levelname)-6s %(message)s', level=logging.DEBUG)

key_name = "locust_cloud_key-%s"
group_name = 'locust_cloud_sg'


def get_region_connection(region_name):
    return connect_to_region(region_name, aws_access_key_id = os.environ.get('AWS_KEY'),
    aws_secret_access_key = os.environ.get('AWS_SECRET'))

def prepare_region(region_name):
    
    conn = get_region_connection(region_name)

    print '*** creating key'
    key = conn.create_key_pair(key_name % region_name)
    key.save("./")


    print '*** creating security group'
    group = conn.create_security_group(group_name, 'Group for locust_cloud')

    for port in constants.INSTANCE_PORTS:
        group.authorize('tcp', port, port, '0.0.0.0/0')
    

def cleanup_region(region_name):

    conn = get_region_connection(region_name)
    
    print '*** deleting key'
    conn.delete_key_pair(key_name % region_name)
    
    print '*** deleting security group'
    conn.delete_security_group(group_name)

def spawn_instance(region_name):

    conn = get_region_connection(region_name)

    print '*** spawning instance'
    reservation = conn.run_instances(constants.AMI[region_name], key_name=key_name % region_name, security_groups=[group_name], instance_type='m3.medium' )

    instance = reservation.instances[0]

    while instance.state != 'running':
        time.sleep(3)
        instance.update()
    
    instance.add_tag('host_destiny','locust_cloud');

    print "*** instance ready (%s)" % instance.public_dns_name



def connect_to_instance(region_name,instance_ip):
    
    print '*** connecting %s' % instance_ip

    sclient = ssh.SSHClient()
    sclient.set_missing_host_key_policy(ssh.AutoAddPolicy())
    sclient.connect(instance_ip, username='ubuntu', key_filename="./%s.pem" % (key_name % region_name))

    return sclient

def run_command(region_name,instance_ip,commands):

    sclient = connect_to_instance(region_name,instance_ip)
    
    if not isinstance(commands, (list, tuple)):
        commands = [commands]

    for command in commands:

        print '*** run "%s"' % command


        stdin, stdout, stderr = sclient.exec_command(command)
        
        stdout = stdout.readlines()
        if stdout:
            for line in stdout:
                print line
            
        stderr = stderr.readlines()
        if stderr:
            print 'stderr:'
            for line in stderr:
                print line

    sclient.close()


def prepare_instance(region_name,instance):

    run_command(region_name,instance.public_dns_name, constants.INSTANCE_PREPARE)
    instance.add_tag('lc_status','prepared');




def terminate_instance(region_name,instance):

    print '*** terminating instance'

    conn = get_region_connection(region_name)
    conn.terminate_instances(instance_ids=[instance.id])


def find_all_instances(region_name):

    print "*** searching for instances"
    conn = get_region_connection(region_name)

    reservations = conn.get_all_reservations()

    instances = []

    for reservation in reservations:
        # if reservation.instances[0].state == 'terminated'
        for instance in reservation.instances:
            if instance.tags["host_destiny"] == 'locust_cloud' and instance.state == 'running':
                instances.append(instance)
                # print instance.state

    return instances

def terminate_region(region_name):

    instances = find_all_instances(region_name)

    for instance in instances:
        terminate_instance(region_name,instance)


def all_run_command(region_name,command):

    instances = find_all_instances(region_name)

    for instance in instances:
        run_command(region_name,instance.public_dns_name,command)

def display_instances(instances):

    if not instances:
        print 'NO INSTANCES'

    for instance in instances:
        print "%(ip_address)s\t%(state)s\t%(tags)s\n" % {
            "tags" : instance.tags, 
            "ip_address" : instance.ip_address,
            "state" : instance.state
        }

def put_file(region_name,instance,from_file,to_file):

    sclient = connect_to_instance(region_name,instance.public_dns_name)

    print '*** coping file %s to %s' % (from_file,to_file)
    sftp = sclient.open_sftp()
    sftp.put(from_file, to_file)

def prepare_config(domain,url = "/"):

    file_name = "/tmp/%s" % uuid.uuid4()
    output = open( file_name, "wb")
    output.write(

        Template(
            open('./template.py', 'r').read()
        ).safe_substitute({
            "url": url,
            "host": domain
        })

    )
    output.close()

    return file_name

def update_config_on_all_instances(region_name,config_file):

    instances = find_all_instances(region_name)

    for instance in instances:
        put_file(region_name,instance,config_file,'/tmp/locust_config.py')


def run_master(region_name,instance):
    
    commands = ["screen -X -S locust_master quit",
               "screen -S locust_master -d -m locust -f /tmp/locust_config.py --master"]

    run_command(region_name,instance.public_dns_name,commands)

    print "*** Runing master at http://%s:8089" % instance.public_dns_name

def run_slave(region_name,instance,master_ip):
    
    commands = ["screen -X -S locust_slave quit",
               "screen -S locust_slave -d -m locust -f /tmp/locust_config.py --slave --master-host=%s" % master_ip]

    run_command(region_name,instance.public_dns_name,commands)

    print "*** Running slave on %s" % instance.public_dns_name


def spawn(region,num_instances):
    
    threads = []
    
    for x in xrange(num_instances):
        thread = threading.Thread(target=spawn_instance, args=(region,))
        thread.start()
        threads.append(thread)
     
    for thread in threads:
        thread.join()
     
    print "*** All instances spawned"

def prepare(region):

    instances = find_all_instances(region)
    threads = []
    
    for instance in instances:
        if instance.tags.get('lc_status') != 'prepared':
            thread = threading.Thread(target=prepare_instance, args=(region,instance,))
            thread.start()
            threads.append(thread)

    for thread in threads:
        thread.join()
     
    print "*** All instances prepared" 


def find_or_elect_master(region):

    instances = find_all_instances(region)

    for instance in instances:
        if instance.tags.get('lc_type') == 'master':
            return instance

    for instance in instances:
        if instance.tags.get('lc_status') == 'prepared' and instance.tags.get('lc_type') != 'master':
            instance.add_tag('lc_type','master')
            return instance

    print 'NO INSTANCES OR NO PREPARED INSTANCES'
            

def do_region(region_name):

    master_instance = find_or_elect_master(region_name)
    instances = find_all_instances(region)

    run_master(region_name,master_instance)

    time.sleep(5) # czekanie na jebanego mastera az wstanie

    for instance in instances:
        if instance.tags.get('lc_status') == 'prepared':
            run_slave(region_name,instance,master_instance.public_dns_name)


def add_slaves(region_name,master,config_file,number):
    
    spawn(region_name,number)

    print "*** Waitin 10 sec"
    
    time.sleep(10)
    
    prepare(region_name)

    update_config_on_all_instances(region_name,config_file)

    for instance in instances:
        if instance.tags.get('lc_status') == 'prepared':
            run_slave(region_name,instance,master_instance.public_dns_name)


def config(region_name,config_file):

    instances = find_all_instances(region)
    threads = []
    
    for instance in instances:
        # put_file(region_name,instance,config_file,'/tmp/locust_config.py')
        thread = threading.Thread(target=put_file, args=(region_name,instance,config_file,'/tmp/locust_config.py',))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()
     
    print "*** Config done" 


def run(region,commands):

    instances = find_all_instances(region)
    threads = []
    
    for instance in instances:
        thread = threading.Thread(target=run_command, args=(region,instance.public_dns_name,commands,))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()
     
    print "*** All instances done" 






