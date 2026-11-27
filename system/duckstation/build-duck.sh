#!/bin/bash
set -euo pipefail
o=/mnt/e/BananaOS-Korean-0.5.3.6.27
w=/var/tmp/banana-v26-duck
s="$w/duckstation"
host=/home/banana-builder/banana/output/rgds/host
sysroot="$host/aarch64-buildroot-linux-gnu/sysroot"
root=/var/tmp/banana-rpg-v20-rgds/root
test -e "$root/usr/lib/libgbm.so" || root=/var/tmp/banana-rpg-v19-rgds/root
deps="$w/deps"
mkdir -p "$deps/include" "$deps/lib" "$deps/cmake-sdl" "$deps/empty" "$o/binaries" "$o/logs"
if [ "${1:-}" = patch ]; then
    test -z "$(git -C "$s" diff --name-only)"
    python3 "$o/patch-duck.py" "$s"
    git -C "$s" diff --check
    git -C "$s" diff > "$o/duckstation-banana.patch"
fi
for h in libdrm GLES GLES2 GLES3 EGL KHR; do ln -sfn "/usr/include/$h" "$deps/include/$h"; done
for h in xf86drm.h xf86drmMode.h gbm.h; do ln -sfn "/usr/include/$h" "$deps/include/$h"; done
ln -sfn /usr/include/aarch64-linux-gnu/curl "$deps/include/curl"
mkdir -p "$deps/include/SDL2"
cp -aL /usr/include/SDL2/. "$deps/include/SDL2/"
cp -L /usr/include/aarch64-linux-gnu/SDL2/_real_SDL_config.h "$deps/include/SDL2/"
sed -i -E '/^#define SDL_VIDEO_DRIVER_(X11|WAYLAND|MIR)([[:space:]_]|$)/d' "$deps/include/SDL2/_real_SDL_config.h"
for lib in SDL2-2.0.so.0 drm.so curl.so EGL.so GLESv2.so gbm.so; do
 ln -sfn "$root/usr/lib/lib$lib" "$deps/lib/lib$lib"
 test -e "$deps/lib/lib$lib"
done
ln -sfn "$deps/lib/libSDL2-2.0.so.0" "$deps/lib/libSDL2.so"
cat > "$deps/cmake-sdl/SDL2Config.cmake" <<EOF
set(SDL2_FOUND TRUE)
set(SDL2_VERSION 2.32.10)
set(SDL2_INCLUDE_DIRS "$deps/include/SDL2")
set(SDL2_LIBRARIES SDL2::SDL2)
if(NOT TARGET SDL2::SDL2)
 add_library(SDL2::SDL2 SHARED IMPORTED)
 set_target_properties(SDL2::SDL2 PROPERTIES IMPORTED_LOCATION "$deps/lib/libSDL2.so" INTERFACE_INCLUDE_DIRECTORIES "$deps/include/SDL2")
endif()
EOF
export PATH="$host/bin:$PATH"
export PKG_CONFIG_LIBDIR="$deps/empty"
flags="-O2 -mcpu=cortex-a55 -I$deps/include -I$deps/include/libdrm -I$deps/include/SDL2 -I$sysroot/usr/include/drm"
cmake -S "$s" -B "$w/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
  -DCMAKE_C_COMPILER="$host/bin/aarch64-linux-gcc" -DCMAKE_CXX_COMPILER="$host/bin/aarch64-linux-g++" \
  -DCMAKE_C_FLAGS="$flags" -DCMAKE_CXX_FLAGS="$flags" -DCMAKE_C_FLAGS_RELEASE="-O3 -DNDEBUG" -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$deps/lib -Wl,-rpath-link,$root/usr/lib -Wl,-rpath-link,$root/lib -Wl,--allow-shlib-undefined" \
  -DCMAKE_SKIP_RPATH=ON -DCMAKE_FIND_PACKAGE_PREFER_CONFIG=ON -DSDL2_DIR="$deps/cmake-sdl" \
  -DCURL_INCLUDE_DIR="$deps/include" -DCURL_LIBRARY="$deps/lib/libcurl.so" \
  -DEGL_INCLUDE_DIR="$deps/include" -DEGL_LIBRARY="$deps/lib/libEGL.so" \
  -DGBM_INCLUDE_DIR="$deps/include" -DGBM_LIBRARY="$deps/lib/libgbm.so" \
  -DLibdrm_INCLUDE_DIR="$deps/include" -DLibdrm_LIBRARY="$deps/lib/libdrm.so" \
  -DBUILD_NOGUI_FRONTEND=ON -DBUILD_QT_FRONTEND=OFF -DBUILD_REGTEST=OFF -DENABLE_CUBEB=OFF \
  -DENABLE_OPENGL=ON -DENABLE_VULKAN=ON -DENABLE_DISCORD_PRESENCE=OFF -DENABLE_CHEEVOS=OFF \
  -DUSE_X11=OFF -DUSE_WAYLAND=OFF -DUSE_EGL=ON -DUSE_DRMKMS=ON -DUSE_FBDEV=OFF -DUSE_EVDEV=OFF -DUSE_DBUS=OFF -DUSE_SDL2=ON
echo DUCK_CONFIGURE_PASS
cmake --build "$w/build" --target duckstation-nogui -j6
install -m755 "$w/build/bin/duckstation-nogui" "$o/binaries/duckstation-nogui"
"$host/bin/aarch64-linux-strip" --strip-unneeded "$o/binaries/duckstation-nogui"
file "$o/binaries/duckstation-nogui"
"$host/bin/aarch64-linux-readelf" -d "$o/binaries/duckstation-nogui" | grep -E 'NEEDED|RPATH|RUNPATH'
sha256sum "$o/binaries/duckstation-nogui"
echo DUCK_ARM64_BUILD_PASS
