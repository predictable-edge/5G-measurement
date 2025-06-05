sudo apt-get -y update
sudo apt install -y make g++ ffmpeg pkg-config python3-pip libzmq5-dev
sudo apt install -y libavcodec-dev libavformat-dev libavutil-dev libavfilter-dev libswscale-dev libavdevice-dev
sudo apt install -y stress-ng
pip install numpy opencv-python ultralytics posix_ipc zmq
pip install psutil
pip3 install psutil

# Use whole GPU but not Grid GPU
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
sudo add-apt-repository ppa:graphics-drivers/ppa -y
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt update

sudo apt install -y nvidia-driver-560
sudo apt install -y cuda-toolkit-12-6

echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# For ali root user
# sudo mkdir -p /root/.config/Ultralytics
# sudo chown -R root:root /root/.config/Ultralytics
# sudo chmod -R 755 /root/.config/Ultralytics

# Ubuntu remote desktop
# sudo apt install ubuntu-desktop-minimal
# sudo apt install xrdp
# sudo systemctl enable xrdp
# sudo systemctl start xrdp
# sudo passwd ubuntu | sudo passwd root

# Install steam or alvr, for alvr, use 20.12.1 version
# Check details of how to deploy alvr
# https://cloud.wikis.utexas.edu/wiki/spaces/utns/pages/333192201/VR+application+ALVR+SteamVR+PhoneVR
# Sunshine and moonlight, open the statistics on the moonlight
