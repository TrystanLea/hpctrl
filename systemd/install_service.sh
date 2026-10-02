#!/bin/bash
# Install (or reinstall) a systemd unit for one of the scripts in service/
# Usage: ./systemd/install_service.sh hpctrl|hpctrl_io|hpctrl_mqtt

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
REPO="$( dirname "$DIR" )"

service=$1

if [ -z "$service" ]; then
    echo "Service name required, e.g: $0 hpctrl"
    exit 1
fi

script="$REPO/service/$service.py"
if [ ! -f "$script" ]; then
    echo "No such script: $script"
    exit 1
fi

unit="/lib/systemd/system/$service.service"
echo "Service name: $service"

# -L also catches old units symlinked into the repo, which may now be dangling
if [ -e "$unit" ] || [ -L "$unit" ]; then
    echo "- reinstalling $service.service"
    sudo systemctl stop $service.service
    sudo systemctl disable $service.service
    sudo rm "$unit"
else
    echo "- installing $service.service"
fi

sed -e "s|SCRIPT_NAME|$service|g" -e "s|SCRIPT_PATH|$script|g" "$DIR/template.service" | sudo tee "$unit" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable $service.service
sudo systemctl restart $service.service

state=$(systemctl show $service | grep ActiveState)
echo "- Service $state"
