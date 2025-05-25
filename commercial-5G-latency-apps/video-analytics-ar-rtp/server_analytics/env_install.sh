sudo apt-get -y update
sudo apt install -y make g++ ffmpeg pkg-config python3-pip
sudo apt install -y libavcodec-dev libavformat-dev libavutil-dev libavfilter-dev libswscale-dev libavdevice-dev
sudo apt install -y stress-ng
pip install numpy opencv-python ultralytics posix_ipc zmq

# wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
# sudo add-apt-repository ppa:graphics-drivers/ppa -y
# sudo dpkg -i cuda-keyring_1.0-1_all.deb
# sudo apt update

# sudo apt install -y nvidia-driver-560

# wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
# sudo dpkg -i cuda-keyring_1.1-1_all.deb
# sudo apt update
# sudo apt install -y cuda-toolkit-12-6

# echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
# echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
# source ~/.bashrc
