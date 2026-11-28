# Private, opt-in ALSA. Never overwrite the firmware's system libasound.
BANANA_PORT_ALSA_VERSION = 1.2.15.3
BANANA_PORT_ALSA_SOURCE = alsa-lib-$(BANANA_PORT_ALSA_VERSION).tar.bz2
BANANA_PORT_ALSA_SITE = https://www.alsa-project.org/files/pub/lib
BANANA_PORT_ALSA_LICENSE = LGPL-2.1+
BANANA_PORT_ALSA_LICENSE_FILES = COPYING
BANANA_PORT_ALSA_DEPENDENCIES = host-pkgconf
BANANA_PORT_ALSA_INSTALL_STAGING = NO
BANANA_PORT_ALSA_CONF_OPTS = --disable-python --disable-aload --disable-dependency-tracking

define BANANA_PORT_ALSA_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/src/.libs/libasound.so.2.0.0 $(TARGET_DIR)/usr/lib/banana/ports/alsa/libasound.so.2
	$(INSTALL) -D -m 0644 $(@D)/COPYING $(TARGET_DIR)/usr/share/licenses/banana-port-alsa/COPYING
endef

$(eval $(autotools-package))
