from datetime import datetime
import re
import urllib2
from fabric.api import *
from fabric.colors import green, yellow, red
from fabric.contrib.files import append
import boto
import boto.ec2
import time
from fabric.exceptions import NetworkError
from boto.exception import EC2ResponseError
from boto.ec2.blockdevicemapping import BlockDeviceMapping
from boto.ec2.blockdevicemapping import BlockDeviceType

@task
def start_es():
    """Starts the elasticsearch machine instance"""    
    myIpAddress = what_is_my_ip_address()
    esIpAddress = start_machine(
        myIpAddress = myIpAddress,
        ec2InstanceName=env.elasticsearch_instance_name,
        ec2InstanceType=env.elasticsearch_instance_type)

    open_external_port(
        ec2SecurityGroup=env.elasticsearch_instance_name, 
        ipAddress=myIpAddress, 
        port=9200)

    with (settings(host_string=esIpAddress)):
        install_elasticsearch_service()
        install_elasticsearch_aws_plugin()
        start_elasticsearch_service()
        wait_for_elasticsearch_service()

@task
def stop_es():
    """Stops the elasticsearch machine instance"""
    stop_machine(ec2InstanceName=env.elasticsearch_instance_name)    

@task
def find_es():
    """Prints elasticsearch machine instance ip address"""
    return find_running_machine(env.elasticsearch_instance_name)

@task
def ssh_es():
    """ ssh the elasticsearch machine instance """
    conn = aws_connect()
    instance = find_server(conn, env.elasticsearch_instance_name)
    local("ssh %s@%s -i %s" % (env.user, instance.ip_address,env.key_filename))

@task
def backup_es():
    """ Snapshots the elasticsearch EBS drive to S3"""
    instance = find_running_machine(env.elasticsearch_instance_name)
    if not instance:
        print(red("Cannot find running instance %s" % env.elasticsearch_instance_name))

    print(green("Flushing elasticsearch indices"))
    local("curl -XPOST 'http://"+instance.ip_address+":9200/_flush?pretty=true'")
    backup_instance(env.elasticsearch_instance_name)

    print("Waiting for elasticsearch to start again")
    with (settings(host_string=instance.ip_address)):
        wait_for_elasticsearch_service()

def find_running_machine(ec2InstanceName):
    conn = aws_connect()
    instance = find_server(conn, ec2InstanceName)
    if not instance:
        print(red("cannot find %s machine instance instance" % ec2InstanceName))
    elif instance.state != u'running':
        print(red("%s machine instance state is %s" % (ec2InstanceName, instance.state)))
    else:
        print green("Found running instance %s" %instance.ip_address)
    return instance
    
def stop_machine(ec2InstanceName):
    conn = aws_connect()
    instance = find_server(conn, ec2InstanceName)
    if not instance:
        print(red("cannot find %s machine instance instance" % ec2InstanceName))
    elif instance.state == u'terminated':
        print(red("cannot stop machine instance %s already terminated" % ec2InstanceName))
    elif instance.state == u'stopping':
        wait_for_instance_state(instance, u'stopped')
    else:
        conn.stop_instances(instance_ids=[instance.id])
        wait_for_instance_state(instance, u'stopped')
    
    print(green("instance state: %s" % instance.state))    

def install_elasticsearch_service():
    print(green("installing java"))
    sudo('apt-get -qq --yes update')
    sudo('apt-get --quiet --yes install openjdk-7-jre-headless')
    run('java -version')

    print(green("installing elasticsearch"))

    run('[ ! -f elasticsearch-0.20.4.deb ] && curl -OL -k http://download.elasticsearch.org/elasticsearch/elasticsearch/elasticsearch-0.20.4.deb || echo "elasticsearch-0.20.4.deb already exists"')
    sudo('dpkg -i elasticsearch-0.20.4.deb')

    sudo('service elasticsearch stop')

    #sudo('mkdir -p /var/data/elasticsearch')

    #append('/etc/elasticsearch/elasticsearch.yml', [    
    #    'path.data: /var/data/elasticsearch'  
    #], use_sudo=True)

    print(green("installing elasticsearch aws plugin"))
    
def install_elasticsearch_aws_plugin():

    sudo('[ -d /usr/share/elasticsearch/plugins/cloud-aws ] && echo aws-plugin already installed || /usr/share/elasticsearch/bin/plugin -install elasticsearch/elasticsearch-cloud-aws/1.10.0')
    #Check installed succesfully. plugin command has no error codes
    run('ls /usr/share/elasticsearch/plugins/cloud-aws > /dev/null')

    #see https://github.com/elasticsearch/elasticsearch-cloud-aws
    with (hide('everything')):
        append('/etc/elasticsearch/elasticsearch.yml', [
            'cloud.aws.access_key: ' + env.aws_access_key_id,
            'cloud.aws.secret_key: ' + env.aws_secret_access_key
        ], use_sudo=True)

    append('/etc/elasticsearch/elasticsearch.yml', [
     'discovery.type: ec2',
     'disocvery.ec2.groups: ' + env.elasticsearch_instance_name,
#     'discovery.ec2.tag.Name: elasticsearch',
     'cloud.node.auto_attributes: true',
    ], use_sudo=True)

def start_elasticsearch_service():
    print(green("starting elasticsearch"))
    sudo('service elasticsearch start')

def wait_for_elasticsearch_service():
    #local('curl http://'+env.host_string+':9200 --retry 12 --retry-delay 10 --silent --show-error')
    local('wget http://'+env.host_string+':9200/?pretty=true -O - --tries=10 --retry-connrefused --waitretry=10 --no-verbose')

def find_server(conn, ec2InstanceName):
    newinstance = None

    reservations = conn.get_all_instances()
    instances = [i for r in reservations for i in r.instances]
    for instance in instances:
        tags = instance.__dict__['tags']
        if ec2InstanceName == tags['Name'] and instance.state != u'terminated' and instance.state != u'shutting-down':
            newinstance = instance
            break
    
    return newinstance

def start_machine(ec2InstanceName,ec2InstanceType,myIpAddress):

    conn = aws_connect()
    
    instance = find_server(conn, ec2InstanceName)
    open_external_port(ec2InstanceName, myIpAddress, 22)

    if not instance:

        """
        Creates EC2 Instance
        """
    
        image = conn.get_image(env.ec2_ami)
        
        bdm = BlockDeviceMapping()
        bdm['/dev/sda1'] = BlockDeviceType(
            delete_on_termination=False,
            size=8 #GB
        )
        
        newreservation = image.run(1, 1, 
            key_name=env.ec2_keypair_name, 
            security_groups=[ec2InstanceName],
            instance_type=ec2InstanceType, 
            block_device_map = bdm)

        instance = newreservation.instances[0]
        conn.create_tags([instance.id], {"Name":ec2InstanceName})
    else:
        """
        Start instance if stopped
        """
        if instance.state == u'stopping':
            wait_for_instance_state(instance, u'stopped')
        if instance.state == u'stopped':
            instance.start()

    wait_for_instance_state(instance, u'running')    

    print(green("instance state: %s" % instance.state))
    print(green("instance public ip: %s" % instance.ip_address))
    
    with (settings(host_string=instance.ip_address)):
        wait_for_ssh_connection()
    
    return instance.ip_address

def wait_for_instance_state(instance, desiredState):
    while instance.state != desiredState:
        print(yellow("instance state: %s" % instance.state))
        time.sleep(10)
        instance.update()

def wait_for_ssh_connection():

    """
      Test SSH connection
    """
    maxSshAttempts=6
    for attempt in range(maxSshAttempts):
        try:
            run("echo ping")
            break
        except NetworkError as exc:
            if (attempt < maxSshAttempts-1):
                time.sleep(10)
                print(yellow("Attempting ssh connection"))                
            else:
                raise

def open_external_port(ec2SecurityGroup, ipAddress, port):
    conn = aws_connect()

    try:
        groups = conn.get_all_security_groups(groupnames=[ec2SecurityGroup])
        group = groups[0]
    except EC2ResponseError as exc:
        if (exc.error_code == u'InvalidGroup.NotFound'):
            print(green("Creating security group " + ec2SecurityGroup))
            group = conn.create_security_group(ec2SecurityGroup, "auto-generated")
        else:
            raise
    try: 
        opened = group.authorize(
            ip_protocol='tcp', from_port=port, 
            to_port=port, cidr_ip=ipAddress+'/32')
        print(green("Opened port %s for ip %s" % (port , ipAddress)))
    except EC2ResponseError as exc:
        if (exc.error_code != u'InvalidPermission.Duplicate'):
            raise

def what_is_my_ip_address():
    print "detecting what is my ip address"
    myIpAddress = urllib2.urlopen('http://ifconfig.me/ip').read().strip()
    print (green("my ip address:"+myIpAddress))
    return myIpAddress

def backup_instance(ec2InstanceName):
    conn = aws_connect()
    instance = find_server(conn, ec2InstanceName)
    print(green("Creating machine image from " + instance.id))
    if not instance:
        print(red("Cannot find " + ec2InstanceName))

    print("Backing up instance " + instance.id)
    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    imageId = conn.create_image(
        instance.id,
        ec2InstanceName + timestamp,
        no_reboot=False)
    
    image = None

    while image == None:
        try:
            image = conn.get_image(imageId)
        except EC2ResponseError as exc:
            if (exc.error_code != u'InvalidAMIID.NotFound'):
                raise
            time.sleep(10)

    while image.state != u'available':
        print(yellow("image state: %s" % image.state))
        time.sleep(10)
        image.update()

    print(green("image state: %s" % image.state))
    print("Created machine image " + imageId)

def aws_connect():
    return boto.ec2.connect_to_region(
              env.ec2_region, 
              aws_access_key_id=env.aws_access_key_id,
              aws_secret_access_key=env.aws_secret_access_key)
    
