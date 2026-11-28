################################################################################
# FBNeo: aleksei74/FBNeo feature/cv1000-arm64-low-spec, pinned for reproducibility.
################################################################################

LIBRETRO_FBNEO_VERSION = 36a8fe5c865f6e1e89fcb0820035b872269b83cd
LIBRETRO_FBNEO_SITE = $(call github,aleksei74,FBNeo,$(LIBRETRO_FBNEO_VERSION))
LIBRETRO_FBNEO_LICENSE = LicenseRef-FBNeo-NonCommercial
LIBRETRO_FBNEO_LICENSE_FILES = src/license.txt LICENSE.md
LIBRETRO_FBNEO_DEPENDENCIES = zlib libegl libgles

define LIBRETRO_FBNEO_BUILD_CMDS
	# Match the ROCKNIXK package's dynamic C++ runtime change.
	sed -i 's/LDFLAGS += -static-libgcc -static-libstdc++/LDFLAGS += -static-libgcc/' $(@D)/src/burner/libretro/Makefile
	# AArch64 has Advanced SIMD; HAVE_NEON=1 adds an ARM32-only GCC flag.
	$(TARGET_MAKE_ENV) CFLAGS="$(TARGET_CFLAGS)" CXXFLAGS="$(TARGET_CXXFLAGS)" \
		$(MAKE) -C $(@D)/src/burner/libretro platform=unix CC="$(TARGET_CC)" CXX="$(TARGET_CXX)" \
		AR="$(TARGET_AR)" USE_CYCLONE=0 HAVE_NEON=0 REGEN_HEADERS=1 GIT_VERSION=36a8fe5
endef

define LIBRETRO_FBNEO_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0644 $(@D)/src/burner/libretro/fbneo_libretro.so $(TARGET_DIR)/usr/lib/libretro/fbneo_libretro.so
	$(INSTALL) -D -m 0644 $(@D)/src/license.txt $(TARGET_DIR)/usr/share/licenses/fbneo/license.txt
	$(INSTALL) -D -m 0644 $(@D)/LICENSE.md $(TARGET_DIR)/usr/share/licenses/fbneo/LICENSE.md
	$(INSTALL) -D -m 0644 $(@D)/metadata/hiscore.dat $(TARGET_DIR)/usr/share/banana/fbneo/hiscore.dat
endef

$(eval $(generic-package))
