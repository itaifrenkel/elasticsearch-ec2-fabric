elasticsearch-ec2-fabric
========================

Python script for quickly running a single elasticsearch machine instance on Amazon EC2.

Usage
-----
```
$ fab -l
Available commands:

    start_es   Starts the elasticsearch machine instance
    stop_es    Stops the elasticsearch machine instance
    find_es    Prints elasticsearch machine instance ip adress
    ssh_es     ssh the elasticsearch machine instance
    backup_es  Snapshots the elasticsearch EBS drive to S3
```

Installation
------------
* Install fabric (requires python)
  ```
    pip install fabric
  ```
* Save fabfile.py into a python folder
  ```
    mkdir scripts
    cd scripts
    echo > __init__.py
    wget https://raw.github.com/itaifrenkel/elasticsearch-ec2-fabric/master/fabfile.py
  ```
* Create a new file ~/.fabricrc with ec2 configuration
  Make sure to modify the configuration based on your EC2 keypair and security credentials
```
aws_access_key_id=AKIAJUMCDAZTUBL6XKWA
aws_secret_access_key=DqmsPX8FspyEf367nU4Yr9J0uuNJ05qjoA1tjGnG

user=ubuntu
key_filename=/home/itai/itaif.pem

ec2_region=us-east-1
ec2_ami=ami-cdc072a4
ec2_keypair_name=itaif

elasticsearch_instance_type=t1.micro
elasticsearch_instance_name=elasticsearch
```
