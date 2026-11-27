################################################################################
# SwanStation (libretro PS1); pinned source, ARM64 cross-build.
################################################################################

LIBRETRO_SWANSTATION_VERSION = 631f0fb31b809e0f889d7c551fe695788e39c1d3
LIBRETRO_SWANSTATION_SITE = $(call github,libretro,swanstation,$(LIBRETRO_SWANSTATION_VERSION))
LIBRETRO_SWANSTATION_LICENSE = GPL-3.0
LIBRETRO_SWANSTATION_LICENSE_FILES = LICENSE
LIBRETRO_SWANSTATION_DEPENDENCIES = zlib
LIBRETRO_SWANSTATION_CONF_OPTS = -DCMAKE_BUILD_TYPE=Release -DGIT_VERSION=631f0fb -DGIT_HASH=631f0fb
LIBRETRO_SWANSTATION_INSTALL_STAGING = NO

define LIBRETRO_SWANSTATION_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0644 $(@D)/swanstation_libretro.so $(TARGET_DIR)/usr/lib/libretro/swanstation_libretro.so
	$(INSTALL) -D -m 0644 $(@D)/LICENSE $(TARGET_DIR)/usr/share/licenses/swanstation/LICENSE
endef

$(eval $(cmake-package))
