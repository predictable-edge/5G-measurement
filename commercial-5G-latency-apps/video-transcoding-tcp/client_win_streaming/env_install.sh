# install MSYS2 in https://www.msys2.org/ and use mingw64 cmd line
pacman -Syu 
pacman -S base-devel mingw-w64-x86_64-toolchain mingw-w64-x86_64-ffmpeg mingw-w64-x86_64-SDL2 mingw-w64-x86_64-zlib
pacman -S git
pacman -S mingw-w64-x86_64-gcc

