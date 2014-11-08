# Ubuntu 14.04LTS amd64 instance-store AMIs http://cloud-images.ubuntu.com/locator/ec2/ 

AMI = {
    "eu-west-1"         : "ami-7aa8080d",
    "eu-central-1"      : "ami-ce3f09d3",
    "us-east-1"         : "ami-d0ba0cb8",
    "us-west-1"         : "ami-6d6b6028",
    "us-west-2"         : "ami-a94e0c99",
    "ap-northeast-1"    : "ami-83705b82",
    "ap-southeast-1"    : "ami-2e1a3d7c",
    "ap-southeast-2"    : "ami-29137113",
    "cn-north-1"        : "ami-5a42d063"
}

INSTANCE_PREPARE = [
	"sudo sh -c 'echo \"* soft nofile 100000\n* hard nofile 100000\" >> /etc/security/limits.conf'",
    "sudo apt-get -y update",
    "sudo apt-get install python-dev libevent-dev libzmq-dev python-pip siege apache2-utils -y",
    "sudo pip install pyzmq",
    "sudo pip install locustio"
]

INSTANCE_PORTS = [
    22,     # ssh
    5557,   # locust slave
    5558,   # locust slave
    8089    # locust web
]