# SPDX-License-Identifier: GPL-3.0-only
# MuseScore-Studio-CLA-applies
#
# MuseScore Studio
# Music Composition & Notation
#
# Copyright (C) 2022 MuseScore Limited and others
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

include(GetPlatformInfo)

if (OS_IS_MAC)
    # See also SetupIconComposerIcon.cmake

    install(FILES DbIcon/DbIcon.icns RENAME DbIcon.icns DESTINATION ${MUSE_APP_INSTALL_RESOURCES_LOCATION})

elseif(OS_IS_WIN)
    # See also windows_icons.rc

    if (WIN_PORTABLE)
        install(FILES DbIcon/DbIcon.ico RENAME appicon.ico DESTINATION ${CMAKE_INSTALL_PREFIX}/../AppInfo)
        install(FILES DbIcon/DbIcon_16x16.png RENAME appicon_16.png DESTINATION ${CMAKE_INSTALL_PREFIX}/../AppInfo)
        install(FILES DbIcon/DbIcon_32x32.png RENAME appicon_32.png DESTINATION ${CMAKE_INSTALL_PREFIX}/../AppInfo)
        install(FILES DbIcon/DbIcon_128x128.png RENAME appicon_128.png DESTINATION ${CMAKE_INSTALL_PREFIX}/../AppInfo)
        install(FILES DbIcon/DbIcon.ico RENAME db.ico DESTINATION ${CMAKE_INSTALL_PREFIX}/../AppInfo/FileTypeIcons)
        install(FILES DbIcon/DbIcon_512x512.png RENAME db.png DESTINATION ${CMAKE_INSTALL_PREFIX}/../AppInfo/FileTypeIcons)
    endif()

elseif(OS_IS_LIN)
    foreach(SIZE 16 24 32 48 64 96 128 512)
        install(FILES DbIcon/DbIcon_${SIZE}x${SIZE}.png
                RENAME dbscore${MUSE_APP_INSTALL_SUFFIX}.png
                DESTINATION share/icons/hicolor/${SIZE}x${SIZE}/apps)
    endforeach()

    install(FILES DbIcon/DbIcon_512x512.png
            RENAME application-x-dbscore${MUSE_APP_INSTALL_SUFFIX}.png
            DESTINATION share/icons/hicolor/512x512/mimetypes)
    install(FILES DbIcon/DbIcon_512x512.png
            RENAME application-x-dbscore${MUSE_APP_INSTALL_SUFFIX}+xml.png
            DESTINATION share/icons/hicolor/512x512/mimetypes)
    install(FILES DbIcon/DbIcon.svg
            RENAME application-x-dbscore${MUSE_APP_INSTALL_SUFFIX}.svg
            DESTINATION share/icons/hicolor/scalable/mimetypes)
    install(FILES DbIcon/DbIcon.svg
            RENAME application-x-dbscore${MUSE_APP_INSTALL_SUFFIX}+xml.svg
            DESTINATION share/icons/hicolor/scalable/mimetypes)

    # Note: Must now run "gtk-update-icon-cache" to set the new icons.
endif()
